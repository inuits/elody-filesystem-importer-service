import os

from elody.job import (
    fail_job,
    init_job,
    start_job,
)
from elody.util import signal_upload_file
from flask import g, jsonify, request
from flask_restful import Resource, abort
from app import policy_factory
from rabbit import get_rabbit
from inuits_policy_based_auth import RequestContext
from services.collection_api_service import CollectionApiService, ValidationError


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

        parent_job_id = init_job(
            "Network Drive Import",
            "Network Import",
            get_rabbit=get_rabbit,
            get_user_context=lambda **_: g.get("user_context"),
            user_email=user_email or "developers@inuits.eu",
            track_async_children=True,
        )

        start_job(
            parent_job_id,
            get_rabbit=get_rabbit,
        )

        try:
            collection_api_service.validate(data)
        except ValidationError as error:
            fail_job(parent_job_id, str(error), get_rabbit=get_rabbit)
            abort(400, message=str(error))

        upload_links = collection_api_service.get_upload_link(data, parent_job_id)

        file_upload_parent_job_id = init_job(
            "Upload Mediafiles",
            "Mediafile upload",
            get_rabbit=get_rabbit,
            get_user_context=lambda **_: g.get("user_context"),
            user_email="developers@inuits.eu",
            parent_id=parent_job_id,
            track_async_children=True,
        )

        start_job(
            file_upload_parent_job_id,
            get_rabbit=get_rabbit,
        )

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
