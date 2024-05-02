import os

from app import policy_factory, rabbit
from flask import request
from flask_restful import abort, Resource
from inuits_policy_based_auth import RequestContext
from services.collection_api_service import CollectionApiService
from elody.util import signal_upload_file
from cloudevents.conversion import to_dict
from cloudevents.http import CloudEvent


class Importer(Resource):
    upload_source = os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

    def __get_request_body(self):
        if request_body := request.get_json(silent=True):
            return request_body
        abort(405, message="Invalid input")

    @policy_factory.authenticate(RequestContext(request))
    def post(self):
        path = self.upload_source
        request_body = self.__get_request_body()
        request_path = os.path.join(
            request_body["selected-folder"], request_body["selected-file"]
        )
        path = os.path.join(self.upload_source, request_path.removeprefix("/"))
        if not os.path.exists(path):
            abort(400, message=f"{path} not found")

        with open(path, "rb") as f:
            data = f.read()
        collection_api_service = CollectionApiService()
        collection_api_service.validate(data)
        upload_links = collection_api_service.get_upload_link(data)
        signal_upload_file(rabbit, upload_links, request_body["selected-folder"])

class ImporterStart(Resource):
    def __get_request_body(self):
        if request_body := request.get_json(silent=True):
            return request_body
        abort(405, message="Invalid input")

    @policy_factory.apply_policies(RequestContext(request, ["start-importer"]))
    def post(self):
        request_body = self.__get_request_body()
        attributes = {"type": "dams.import_requested", "source": "dams"}
        data = {
            "selected_folder": request_body["selected_folder"],
            "user": policy_factory.get_user_context().email,
        }
        event = to_dict(CloudEvent(attributes, data))
        rabbit.send(event, routing_key="dams.import_requested")
        return event, 201


class ImporterDirectories(Resource):
    upload_source = os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

    def __has_subdirs(self, path):
        with os.scandir(path) as entries:
            return any(entry.is_dir() for entry in entries)

    @policy_factory.apply_policies(
        RequestContext(request, ["get-importer-directories"])
    )
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
            return directories
