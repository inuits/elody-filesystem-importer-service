# NOTE: these wrappers could arguably be moved to job.py in the elody format?
from os import getenv

import requests
from elody.job import fail_job, init_job, start_job
from elody.util import send_cloudevent
from flask import g
from models.job_data import JobData
from rabbit import get_rabbit

job_endpoints_enabled = getenv("JOB_ENDPOINTS_ENABLED", False) in {  # noqa: PLW1508
    "true",
    "True",
    True,
}
job_api_base = getenv("JOB_API_URL")
static_jwt = getenv("STATIC_JWT")

headers = {"Authorization": f"Bearer {static_jwt}"}

routing_key_prefix = getenv("ROUTING_KEY_PREFIX", "dams")


def init_job_wrapper(job_data: JobData) -> str:
    if job_endpoints_enabled:
        return requests.post(
            url=f"{job_api_base}/job/init",
            json=job_data.model_dump(),
            headers=headers,
        ).json()["job_id"]

    return init_job(
        get_rabbit=get_rabbit,
        get_user_context=lambda **_: g.get("user_context"),
        **job_data.model_dump(),
    )


def start_job_wrapper(job_id: str) -> None:

    if job_endpoints_enabled:
        requests.post(
            url=f"{job_api_base}/job/start/{job_id}",
            headers=headers,
        )
    else:
        start_job(
            job_id,
            get_rabbit=get_rabbit,
        )


def fail_job_wrapper(job_id: str, error_message: str) -> None:

    if job_endpoints_enabled:
        requests.post(
            url=f"{job_api_base}/job/fail/{job_id}",
            json={"exception_message": error_message},
            headers=headers,
        )
    else:
        fail_job(
            job_id,
            get_rabbit=get_rabbit,
            exception_message=error_message,
        )


def signal_import_csv(
    mq_client,
    csv_path,
    selected_folder,
    parent_job_id=None,
    *,
    ocr: bool = False,
):
    data = {
        "csv_path": csv_path,
        "selected_folder": selected_folder,
        "parent_job_id": parent_job_id,
        "ocr": ocr,
    }
    send_cloudevent(mq_client, "dams", f"{routing_key_prefix + '.'}import_csv", data)


def signal_upload_file(mq_client, upload_links, selected_folder, parent_job_id=None):
    data = {
        "upload_links": upload_links,
        "selected_folder": selected_folder,
        "parent_job_id": parent_job_id,
    }
    send_cloudevent(mq_client, "dams", f"{routing_key_prefix + '.'}upload_file", data)
