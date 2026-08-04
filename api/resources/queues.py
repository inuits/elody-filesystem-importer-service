import os
from os import getenv
from pathlib import Path

import requests
from app import logger
from elody.util import get_boolean_env
from rabbit import get_rabbit
from resources.utils import (
    fail_job_wrapper,
    signal_upload_file,
    start_job_wrapper,
)
from services.collection_api_service import CollectionApiService, ValidationError
from services.importer_service import ImporterService

collection_api_url = os.getenv("COLLECTION_API_URL")

queue_prefix = getenv("QUEUE_PREFIX", "")
queue_type = getenv("QUEUE_TYPE", "classic")
routing_key_prefix = getenv("ROUTING_KEY_PREFIX", "dams")


def __is_malformed_message(data, fields):
    if not all(x in data for x in fields):
        logger.error(f"Message malformed: missing one of {fields}")
        return True
    return False


def __argument_wrapper(*, queue_name, routing_key):
    arguments = {"routing_key": routing_key}
    if getenv("AMQP_MANAGER", "amqpstorm_flask") == "amqpstorm_flask":
        arguments["queue_name"] = queue_name
        if queue_type:
            arguments["queue_arguments"] = {"x-queue-type": queue_type}
    return arguments


@get_rabbit().queue(
    **__argument_wrapper(
        queue_name=f"{(queue_prefix + '.') if queue_prefix else ''}import_csv",
        routing_key=f"{routing_key_prefix}.import_csv",
    ),
)
def upload_csv(_routing_key, body, _message_id):

    collection_api_service = CollectionApiService()
    data = body["data"]
    csv_path = Path(data["csv_path"])
    folder_path = data["selected_folder"]
    ocr = data["ocr"]
    parent_job_id = data.get("parent_job_id", None)
    headers = data.get("headers")

    with csv_path.open("rb") as f:
        data = f.read()

    start_job_wrapper(parent_job_id)

    try:
        collection_api_service.validate(data)
    except ValidationError as error:
        fail_job_wrapper(
            parent_job_id,
            str(error),
        )
        return

    upload_links = collection_api_service.get_upload_link(
        data,
        parent_job_id,
        csv_path.name,
        ocr=ocr,
        headers=headers,
    )
    if upload_links:
        signal_upload_file(
            get_rabbit(),
            upload_links,
            folder_path,
            headers=headers,
        )
    else:
        fail_job_wrapper(
            parent_job_id,
            "No files to upload!",
        )


@get_rabbit().queue(
    **__argument_wrapper(
        queue_name=f"{(queue_prefix + '.') if queue_prefix else ''}upload_file",
        routing_key=f"{routing_key_prefix}.upload_file",
    ),
)
def upload_file(_routing_key, body, _message_id):
    keep_files = get_boolean_env("KEEP_FILES", True)

    collection_api_service = CollectionApiService()
    importer_service = ImporterService()
    data = body["data"]
    upload_links = data["upload_links"]
    parent_job_id = data.get("parent_job_id", None)
    headers = data["headers"]
    user_email = __resolve_user_from_parent_job(parent_job_id)
    if upload_links:
        for upload_link in upload_links.splitlines():
            collection_api_service.upload_file(
                upload_link,
                importer_service.get_filename_from_upload_link(upload_link),
                data["selected_folder"],
                headers=headers,
                keep_files=keep_files,
                parent_job_id=parent_job_id,
                user_email=user_email,
            )
    else:
        fail_job_wrapper(
            parent_job_id,
            "No files to upload!",
        )


# NOTE: This is currently a direct copy of a function in the OCR_service, so
# it should probably be moved to a common place
def __resolve_user_from_parent_job(main_job_id):
    try:
        headers = {"Authorization": f"Bearer {os.getenv('STATIC_JWT')}"}
        r = requests.get(
            f"{collection_api_url}/jobs/{main_job_id}",
            headers=headers,
            timeout=5,
        )
        if r.status_code == 200:
            job = r.json()
            return job.get("created_by") or job.get("last_editor") or None
    except Exception:  # noqa: BLE001
        logger.exception("Error occurred getting user from parent job")

    return None
