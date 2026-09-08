import os
from urllib.parse import ParseResult, parse_qs, unquote, urlparse


class ImporterService:
    def get_filename_from_upload_link(self, upload_link):
        parsed_url: ParseResult = urlparse(upload_link)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        if upload_source := query_params.get("upload_source"):
            return unquote(upload_source[0])
        filename = path.split("/")[-1]
        return unquote(filename)

    def __has_subdirs(self, path):
        with os.scandir(path) as entries:
            return any(entry.is_dir() for entry in entries)
