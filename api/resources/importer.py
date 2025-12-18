import os
from os import getenv

from app import policy_factory
from elody.util import send_cloudevent
from flask import g, jsonify, request
from flask_restful import Resource, abort
from inuits_policy_based_auth import RequestContext
from models.job_data import JobData
from rabbit import get_rabbit
from resources.utils import init_job_wrapper, start_job_wrapper, fail_job_wrapper
from services.collection_api_service import CollectionApiService, ValidationError

routing_key_prefix = getenv("ROUTING_KEY_PREFIX", "dams")


class ImporterBase(Resource):
    @staticmethod
    def get_upload_source():
        return os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

    def __init__(self):
        super().__init__()
        self.upload_source = self.get_upload_source()


class Importer(ImporterBase):
    def __get_request_body(self):
        if request_body := request.get_json(silent=True):
            return request_body
        abort(405, message="Invalid input")

    @policy_factory.authenticate(RequestContext(request))
    def post(self):
        path = self.upload_source
        request_body = self.__get_request_body()
        if "selected-folder" not in request_body:
            abort(400, message="Missing 'selected-folder' in request body")

        selected_folder = request_body["selected-folder"]
        folder_path = os.path.join(
            self.upload_source, selected_folder.removeprefix("/")
        )
        csv_files = [file for file in os.listdir(folder_path) if file.endswith(".csv")]

        if len(csv_files) != 1:
            abort(400, status=400, message_id="error-csv-count", count=len(csv_files))

        selected_file = csv_files[0]
        request_path = os.path.join(selected_folder, selected_file)
        path = os.path.join(self.upload_source, request_path.removeprefix("/"))

        if not os.path.exists(path):
            abort(400, message=f"{path} not found")

        with open(path, "rb") as f:
            data = f.read()
        collection_api_service = CollectionApiService()

        header_email = request.headers.get("X-User-Email", None)
        user_email = header_email if header_email else g.get("user_context").email

        parent_job_data = JobData.model_validate(
            {
                "name": "Network Drive Import",
                "job_type": "Network Import",
                "user_email": (user_email or "developers@inuits.eu"),
                "track_async_children": True,
            }
        )

        parent_job_id = init_job_wrapper(parent_job_data)

        start_job_wrapper(parent_job_id)

        try:
            collection_api_service.validate(data)
        except ValidationError as error:
            fail_job_wrapper(
                parent_job_id,
                str(error),
            )
            abort(400, message=str(error))

        upload_links = collection_api_service.get_upload_link(data, parent_job_id)
        if upload_links:

            file_upload_parent_job_data = JobData.model_validate(
                {
                    "name": "Upload Mediafiles",
                    "job_type": "Mediafile upload",
                    "user_email": (user_email or "developers@inuits.eu"),
                    "track_async_children": True,
                    "parent_id": parent_job_id,
                }
            )

            file_upload_parent_job_id = init_job_wrapper(file_upload_parent_job_data)
            start_job_wrapper(file_upload_parent_job_id)

            signal_upload_file(
                get_rabbit(),
                upload_links,
                folder_path,
                parent_job_id=file_upload_parent_job_id,
            )

        return jsonify(status=200, message_id="import-success", count=len(csv_files))


class ImporterDirectories(ImporterBase):
    def __has_subdirs(self, path):
        with os.scandir(path) as entries:
            return any(entry.is_dir() for entry in entries)

    @policy_factory.authenticate(RequestContext(request))
    def get(self):
        path = self.upload_source
        if request_dir := request.args.get("dir"):
            path = os.path.join(self.upload_source, request_dir.removeprefix("/"))
        if not os.path.exists(path):
            abort(400, message=f"{path} not found")
        directories = []
        with os.scandir(path) as entries:
            for directory in [x for x in entries if x.is_dir()]:
                directories.append(
                    {
                        "dir": directory.path.removeprefix(self.upload_source),
                        "has_subdirs": self.__has_subdirs(directory.path),
                    }
                )
            directories.sort(key=lambda x: x["dir"].lower())
            return directories


def signal_upload_file(mq_client, upload_links, selected_folder, parent_job_id=None):
    data = {
        "upload_links": upload_links,
        "selected_folder": selected_folder,
        "parent_job_id": parent_job_id,
    }
    send_cloudevent(mq_client, "dams", f"{routing_key_prefix + '.'}upload_file", data)
