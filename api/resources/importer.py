import os

from app import policy_factory, rabbit
from flask import request
from flask_restful import abort, Resource
from inuits_policy_based_auth import RequestContext
from services.collection_api_service import CollectionApiService
from elody.util import signal_upload_file


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
