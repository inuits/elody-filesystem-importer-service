import app
import os

from elody import Client
from flask import request, Response
from flask_restful import abort, Resource
from inuits_policy_based_auth import RequestContext
from services.collection_api_service import CollectionApiService
from services.importer_service import ImporterService

collection_api_url = os.getenv("COLLECTION_API_URL")
elody_client = Client(collection_api_url, os.getenv("STATIC_JWT"))


class Importer(Resource):
    def __init__(self):
        self.headers = {"Authorization": f'Bearer {os.getenv("STATIC_JWT")}'}

    def __get_request_body(self):
        if request_body := request.get_json(silent=True):
            return request_body
        abort(405, message="Invalid input")

    @app.policy_factory.authenticate(RequestContext(request))
    def post(self):
        request_body = self.__get_request_body()
        with open(f"{request_body['selected-folder']}/{request_body['selected-file']}", "rb") as f:
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
