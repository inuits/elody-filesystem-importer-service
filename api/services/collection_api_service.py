import requests
import os

from app import logger
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
        self.headers = {"Authorization": f'Bearer {os.getenv("STATIC_JWT")}'}

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

    def get_upload_link(self, data):
        return (
            requests.post(
                f"{self.collection_api_url}/batch",
                headers={**self.headers, **csv_headers},
                data=data,
            )
            .text.strip()
            .replace('"', "")
            .replace("'", "")
            .replace("\\n", "\n")
        )

    def upload_file(self, upload_link, filename, folder, keep_files=True):
        with open(f"{folder}/{filename}", "rb") as f:
            data = f.read()
        response = requests.post(
            upload_link,
            headers={**self.headers, **upload_file_headers},
            data=data,
        )
        try:
            if response.status_code in range(200, 300) and not keep_files:
                os.remove(f"{folder}/{filename}")
        except PermissionError as error:
            logger.error(str(error))
