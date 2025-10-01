from rabbit import get_rabbit
from os import getenv
import requests
import os

from services.collection_api_service import CollectionApiService
from services.importer_service import ImporterService


collection_api_url = os.getenv("COLLECTION_API_URL")


@get_rabbit().queue("dams.upload_file")
def upload_file(routing_key, body, message_id):
    keep_files = getenv("KEEP_FILES", True) in [1, "1", True, "True", "true"]

    collection_api_service = CollectionApiService()
    importer_service = ImporterService()
    data = body["data"]
    upload_links = data["upload_links"]
    parent_job_id = data.get("parent_job_id", None)
    user_email = __resolve_user_from_parent_job(parent_job_id)
    if upload_links:
        for upload_link in upload_links.splitlines():
            collection_api_service.upload_file(
                upload_link,
                importer_service.get_filename_from_upload_link(upload_link),
                data["selected_folder"],
                keep_files=keep_files,
                parent_job_id=parent_job_id,
                user_email=user_email,
            )


# NOTE: This is currently a direct copy of a function in the OCR_service, so
# it should probably be moved to a common place
def __resolve_user_from_parent_job(main_job_id):
    try:
        headers = {"Authorization": f'Bearer {os.getenv("STATIC_JWT")}'}
        r = requests.get(
            f"{collection_api_url}/jobs/{main_job_id}", headers=headers, timeout=5
        )
        if r.status_code == 200:
            job = r.json()
            return job.get("created_by") or job.get("last_editor") or None
    except Exception:
        pass
    return None
