import os
from hashlib import md5
from logging import getLogger
from pathlib import Path
from time import sleep
from urllib.parse import parse_qs, urlparse

import requests
from elody.util import get_boolean_env
from singleton import Singleton

logger = getLogger(__name__)
IN_CLUSTER = get_boolean_env("IN_CLUSTER", False)


class StorageApiService(metaclass=Singleton):
    def __init__(self, session: requests.Session | None = None):
        self.storage_api_url = os.getenv("STORAGE_API_URL")
        self.headers = {
            "Authorization": f"Bearer {os.getenv('STATIC_JWT')}",
            "X-From-Service": f"{'filesystem-importer-service-internal' if IN_CLUSTER else 'filesystem-importer-service'}",
        }
        if session is None:
            self.session = requests.Session()
        else:
            self.session = session

    def upload_file(
        self,
        filename,
        file_location: Path,
        upload_link: str,
        headers: dict | None = None,
        params: dict | None = None,
    ):
        if not headers:
            headers = {}
        if not params:
            params = {}
        parsed_upload_location = urlparse(upload_link)
        mediafile_id = parse_qs(parsed_upload_location.query).get("id", [None])[0]
        if not mediafile_id:
            raise ValueError(f"Could not extract mediafile_id from {upload_link}")

        response = self.session.post(
            f"{self.storage_api_url}/upload/init-stream",
            params={"mediafile_id": mediafile_id},
            headers={**self.headers, **headers},
        )
        response.raise_for_status()
        stream_info = response.json()

        file_size = file_location.stat().st_size
        chunk_size = 50 * (1024**2)
        retry_count = 0
        while True:
            exception = None
            try:
                response = self.session.get(
                    f"{self.storage_api_url}/upload/stream-status",
                    params=stream_info,
                    headers=self.headers,
                )
                response.raise_for_status()
                existing_chunks = {
                    chunk["sequence_number"]: chunk["hash"]
                    for chunk in response.json().get("uploaded_chunks", [])
                }

                # Always read the whole file so the md5sum covers every byte,
                # chunks that were already uploaded are skipped below
                mediafile_md5sum = md5()
                chunks_info = []
                bytes_read = 0
                with file_location.open("rb") as mediafile:
                    for i, chunk in enumerate(
                        iter(lambda: mediafile.read(chunk_size), b""), start=1
                    ):
                        mediafile_md5sum.update(chunk)
                        bytes_read += len(chunk)
                        logger.info(
                            f"Progress: {bytes_read / (1024**2):.2f} MB / {file_size / (1024**2):.2f} MB ({(bytes_read / file_size) * 100 if file_size > 0 else 0:.2f}%)",
                        )
                        if i in existing_chunks:
                            chunks_info.append(
                                {"sequence_number": i, "hash": existing_chunks[i]}
                            )
                            continue

                        response = self.session.post(
                            f"{self.storage_api_url}/upload/sign-chunk",
                            json={**stream_info, "chunk_sequence": i},
                            headers=self.headers,
                        )
                        response.raise_for_status()
                        upload_url = response.json()["upload_url"]
                        if IN_CLUSTER:
                            upload_url = upload_url.replace(
                                "minio.localhost:8000", "minio:9000"
                            )

                        # Pre-signed url, so no auth headers
                        response = requests.put(upload_url, data=chunk, timeout=600)
                        response.raise_for_status()
                        etag = response.headers["ETag"]

                        chunks_info.append({"sequence_number": i, "hash": etag})

                response = self.session.post(
                    f"{self.storage_api_url}/upload/complete-stream",
                    json={
                        **stream_info,
                        "chunks_info": chunks_info,
                        "file_info": {
                            "md5sum": mediafile_md5sum.hexdigest(),
                            "name": filename,
                        },
                    },
                    headers={
                        **self.headers,
                        **headers,
                        "Content-type": "application/json",
                    },
                    params={**params},
                )
                response.raise_for_status()
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as e:
                exception = e
            except Exception as e:  # noqa: BLE001
                retry_count = 4
                exception = e
            if not exception:
                break

            retry_count += 1
            if retry_count >= 4:
                logger.error(
                    f"Failed to upload mediafile: {exception}. Aborting stream...",
                )
                self.session.post(
                    f"{self.storage_api_url}/upload/abort-stream",
                    json=stream_info,
                    headers=self.headers,
                )
                raise exception

            sleep_time = 10**retry_count
            logger.error(
                f"Upload error: {exception}. Retrying in {sleep_time}s... (Attempt {retry_count}/4)",
            )
            sleep(sleep_time)

        return response
