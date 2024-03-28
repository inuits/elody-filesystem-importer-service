import os

UPLOAD_SOURCE = os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

from app import policy_factory
from flask import request
from flask_restful import abort, Resource
from cloudevents.conversion import to_dict
from cloudevents.http import CloudEvent
from inuits_policy_based_auth import RequestContext
from services.collection_api_service import CollectionApiService
from services.importer_service import ImporterService


def get_request_body():
    if request_body := request.get_json(silent=True):
        return request_body
    abort(405, message="Invalid input")


class Importer(Resource):

    @policy_factory.authenticate(RequestContext(request))
    def post(self):
        request_body = get_request_body()
        with open(
                f"{request_body['selected-folder']}/{request_body['selected-file']}", "rb"
        ) as f:
            data = f.read()
        collection_api_service = CollectionApiService()
        importer_service = ImporterService()
        collection_api_service.validate(data)
        upload_link = collection_api_service.get_upload_link(data)
        if upload_link:
            collection_api_service.upload_file(
                upload_link,
                importer_service.get_filename_from_upload_link(upload_link),
                request_body["selected-folder"],
                False,
            )


class ImporterStart(Resource):

    @policy_factory.apply_policies(RequestContext(request, ["start-importer"]))
    def post(self):
        request_body = get_request_body()
        attributes = {"type": "dams.import_requested", "source": "dams"}
        data = {
            "selected_folder": request_body["selected_folder"],
            "user": policy_factory.get_user_context().email,
        }
        event = to_dict(CloudEvent(attributes, data))
        rabbit.send(event, routing_key="dams.import_requested")
        return event, 201


def has_subdirs(path):
    with os.scandir(path) as entries:
        return any(entry.is_dir() for entry in entries)


class ImporterDirectories(Resource):
    upload_source = os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

    @policy_factory.apply_policies(
        RequestContext(request, ["get-importer-directories"])
    )
    def get(self):
        path = UPLOAD_SOURCE
        if request_dir := request.args.get("dir"):
            path = os.path.join(UPLOAD_SOURCE, request_dir.removeprefix("/"))
        if not os.path.exists(path):
            abort(400, message=f"{path} not found")
        directories = []
        with os.scandir(path) as entries:
            for directory in [x for x in entries if x.is_dir()]:
                directories.append(
                    {
                        "dir": directory.path.removeprefix(UPLOAD_SOURCE),
                        "has_subdirs": has_subdirs(directory.path),
                    }
                )
            return directories


def list_directories_recursively(path):
    directories = []
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.is_dir() and entry.name not in ('.', '..'):
                subdir_path = os.path.join(path, entry.name)
                subdirectories = list_directories_recursively(subdir_path)
                directory_id = subdir_path[len(UPLOAD_SOURCE):]
                directories.append({
                    "id": directory_id,
                    "dir": directory_id,
                    "has_subdirs": bool(subdirectories),
                    "subdirectories": subdirectories
                })
    return directories


class ListDirectories(Resource):
    def get(self):
        directory_param = request.args.get("dir")
        if directory_param:
            path = os.path.join(UPLOAD_SOURCE, directory_param.lstrip("/"))
        else:
            path = UPLOAD_SOURCE

        if not os.path.exists(path):
            abort(400, message=f"{path} not found")

        directories = list_directories_recursively(path)
        return directories, 200
