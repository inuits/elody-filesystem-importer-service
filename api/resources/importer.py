import os
from os import getenv

from amqpstorm.exception import AMQPConnectionError
from app import policy_factory
from flask import g, jsonify, request
from flask_restful import Resource, abort
from inuits_policy_based_auth import RequestContext
from models.job_data import JobData
from rabbit import get_rabbit
from resources.utils import fail_job_wrapper, init_job_wrapper, signal_import_csv

routing_key_prefix = getenv("ROUTING_KEY_PREFIX", "dams")


class ImporterBase(Resource):
    @staticmethod
    def get_upload_source():
        return os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

    def __init__(self):
        super().__init__()
        self.upload_source = self.get_upload_source()


class Importer(ImporterBase):
    def __get_request_body(self):  # noqa: RET503
        if request_body := request.get_json(silent=True):
            return request_body
        abort(405, message="Invalid input")

    @policy_factory.authenticate(RequestContext(request))
    def post(self):
        path = self.upload_source
        request_body = self.__get_request_body()
        ocr = False
        if "selected-folder" not in request_body:
            abort(400, message="Missing 'selected-folder' in request body")
        if "ocr" in request_body:
            ocr = request_body["ocr"] in {True, "true", "True"}

        selected_folder = request_body["selected-folder"]
        folder_path = os.path.join(
            self.upload_source,
            selected_folder.removeprefix("/"),
        )
        csv_files = [file for file in os.listdir(folder_path) if file.endswith(".csv")]

        if len(csv_files) != 1:
            abort(400, status=400, message_id="error-csv-count", count=len(csv_files))

        selected_file = csv_files[0]
        request_path = os.path.join(selected_folder, selected_file)
        path = os.path.join(self.upload_source, request_path.removeprefix("/"))

        if not os.path.exists(path):
            abort(400, message=f"{path} not found")

        header_email = request.headers.get("X-User-Email", None)
        user_email = header_email or g.get("user_context").email

        parent_job_data = JobData.model_validate(
            {
                "name": f"Network Drive Import {path.split('/')[-1]}",
                "job_type": "Network Import",
                "user_email": (user_email or "developers@inuits.eu"),
                "track_async_children": True,
            },
        )
        parent_job_id = init_job_wrapper(parent_job_data)

        try:
            signal_import_csv(get_rabbit(), path, folder_path, parent_job_id, ocr=ocr)
        except AMQPConnectionError:
            fail_job_wrapper(parent_job_id, "Task could not be processed")
            return jsonify(
                status=500,
                message_id="import-failure",
                job_id=parent_job_id,
            )

        return jsonify(
            status=200,
            message_id="import-success",
            job_id=parent_job_id,
            count=len(csv_files),
        )


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
                    },
                )
            directories.sort(key=lambda x: x["dir"].lower())
            return directories
