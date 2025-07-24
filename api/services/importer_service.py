import os

from urllib.parse import urlparse


class ImporterService:
    def get_filename_from_upload_link(self, upload_link):
        path = urlparse(upload_link).path
        filename = path.split("/")[-1]
        return filename

    def __has_subdirs(self, path):
        with os.scandir(path) as entries:
            return any(entry.is_dir() for entry in entries)
