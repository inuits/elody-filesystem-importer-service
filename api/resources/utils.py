# NOTE: these wrappers could arguably be moved to job.py in the elody format?
from os import getenv

import requests
from elody.job import init_job, start_job, fail_job
from flask import g
from models.job_data import JobData
from rabbit import get_rabbit

job_endpoints_enabled = getenv("JOB_ENDPOINTS_ENABLED", False) in [
    "true",
    "True",
    1,
    True,
]
job_api_base = getenv("JOB_API_BASE_URL")
static_jwt = getenv("STATIC_JWT")

headers = {"Authorization": f"Bearer {static_jwt}"}


def init_job_wrapper(job_data: JobData) -> str:
    if job_endpoints_enabled:

        job_id = requests.post(
            url=f"{job_api_base}/job/init",
            json=job_data.model_dump(),
            headers=headers,
        ).json()["job_id"]

        return job_id

    else:

        job_id = init_job(
            get_rabbit=get_rabbit,
            get_user_context=lambda **_: g.get("user_context"),
            **job_data.model_dump(),
        )
        return job_id


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
