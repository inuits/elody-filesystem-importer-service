import os

from app import policy_factory, rabbit
from flask import request
from flask_restful import abort, Resource
from inuits_policy_based_auth import RequestContext
from services.collection_api_service import CollectionApiService
from elody.util import signal_upload_file

def get_upload_source():
    return os.getenv("UPLOAD_SOURCE", "/mnt/media-import")

class ImporterBase(Resource):
    def __init__(self):
        super().__init__()
        self.upload_source = get_upload_source()

class Importer(ImporterBase):
    def __get_request_body(self):
        if request_body := request.get_json(silent=True):
            return request_body
        abort(405, message="Invalid input")

    @policy_factory.authenticate(RequestContext(request))
    def post(self):
        path = self.upload_source
        request_body = self.__get_request_body()
        if 'selected-folder' not in request_body:
            abort(400, message="Missing 'selected-folder' in request body")

        selected_folder = request_body["selected-folder"]
        folder_path = os.path.join(self.upload_source, selected_folder.removeprefix("/"))
        csv_files = [file for file in os.listdir(folder_path) if file.endswith('.csv')]

        if len(csv_files) != 1:
            abort(400, message=f"Expected exactly 1 CSV file in {selected_folder}, found {len(csv_files)}")

        selected_file = csv_files[0]
        request_path = os.path.join(selected_folder, selected_file)
        path = os.path.join(self.upload_source, request_path.removeprefix("/"))

        if not os.path.exists(path):
            abort(400, message=f"{path} not found")

        with open(path, "rb") as f:
            data = f.read()
        collection_api_service = CollectionApiService()
        collection_api_service.validate(data)
        upload_links = collection_api_service.get_upload_link(data)
        signal_upload_file(rabbit, upload_links, selected_folder)


class ImporterDirectories(ImporterBase):
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
