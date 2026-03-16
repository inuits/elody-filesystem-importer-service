import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import requests
from app import logger
from resources.utils import (
    fail_job_wrapper,
)
from singleton import Singleton

csv_headers = {
    "Content-Type": "text/csv",
    "Accept": "text/uri-list",
}

upload_file_headers = {
    "Content-Type": "application/octet-stream",
}


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors

    def __str__(self):
        error_str = ""
        for key, value in self.errors.items():
            error_str += f"{key}: {', '.join(value)}\n"
        return error_str


class CollectionApiService(metaclass=Singleton):
    def __init__(self):
        self.collection_api_url = os.getenv("COLLECTION_API_URL")
        self.headers = {"Authorization": f"Bearer {os.getenv('STATIC_JWT')}"}

    def validate(self, data):
        response = requests.post(
            f"{self.collection_api_url}/batch?dry_run=1",
            headers={**self.headers, **{"Content-Type": "text/csv"}},
            data=data,
        ).json()
        if errors := response.get("errors"):
            for _, error in errors.items():
                if error:
                    raise ValidationError(errors)
        return True

    def get_upload_link(self, data, parent_job_id, filename, *, ocr: bool = False):
        params = {"parent_job_id": parent_job_id}
        if ocr:
            params.update({"extra_mediafile_type": "ocr"})
        return (
            requests.post(
                f"{self.collection_api_url}/batch?filename={quote(filename)}",
                headers={**self.headers, **csv_headers},
                data=data,
                params=params,
            )
            .text.strip()
            .replace('"', "")
            .replace("'", "")
            .replace("\\n", "\n")
        )

    def upload_file(  # noqa: PLR0913
        self,
        upload_link,
        filename,
        folder,
        keep_files=True,
        parent_job_id=None,
        user_email=None,
    ):

        file_path = Path(f"{folder}/{filename}")
        if not file_path.exists():
            if not parent_job_id:
                parsed_url = urlparse(upload_link)
                parent_job_id = parse_qs(parsed_url.query)["parent_job_id"][0]
            if parent_job_id:
                fail_job_wrapper(
                    parent_job_id,
                    f"File {file_path.name} not found on NAS.",
                )

        with file_path.open("rb") as f:
            data = f.read()
        params = {}
        if parent_job_id:
            params.update({"parent_job_id": parent_job_id})
        if user_email:
            params.update({"user_email": user_email})
        response = requests.post(
            upload_link,
            headers={**self.headers, **upload_file_headers},
            data=data,
            params=params,
        )
        try:
            if (
                response.status_code in range(200, 300)
                or response.status_code
                in (
                    HTTPStatus.CONFLICT,  # 409: Duplicate file, can be deleted
                    HTTPStatus.UNPROCESSABLE_ENTITY,  # 422: Empty file
                )
            ) and not keep_files:
                file_path.unlink(missing_ok=True)
        except Exception as error:
            logger.error(str(error))
