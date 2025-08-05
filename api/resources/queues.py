import app
from os import getenv

from services.collection_api_service import CollectionApiService
from services.importer_service import ImporterService


@app.rabbit.queue("dams.upload_file")
def upload_file(routing_key, body, message_id):
    keep_files = getenv("KEEP_FILES", True) in [1, "1", True, "True", "true"]
    
    collection_api_service = CollectionApiService()
    importer_service = ImporterService()
    data = body["data"]
    upload_links = data["upload_links"]
    if upload_links:
        for upload_link in upload_links.splitlines():
            collection_api_service.upload_file(
                upload_link,
                importer_service.get_filename_from_upload_link(upload_link),
                data["selected_folder"],
                keep_files=keep_files,
            )
