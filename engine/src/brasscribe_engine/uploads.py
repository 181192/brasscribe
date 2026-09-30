"""Uploads written once: each uploaded file goes straight into the uploads folder as the request arrives.

Starlette spools an uploaded file to a temporary file first, and the upload routes then copied it into
the uploads folder: every upload was written to disk twice. Here the file part is written, and hashed, into
a hidden file in the uploads folder instead, which the route then only renames into place. A file the route
does not keep (a request refused after it was read) is deleted when the request's form is closed.

The engine's routes use UploadRoute; the size cap (guard.BodyLimit) applies to the stream as before.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException, MultiPartParser


class UploadSink:
    """A file being uploaded into `folder` under a hidden name, with its sha256 and size kept as it is written."""

    def __init__(self, folder: Path):
        self.path = folder / f".upload-{secrets.token_hex(8)}"
        self._file = self.path.open("w+b")
        self._hash = hashlib.sha256()
        self.size = 0
        self._kept = False

    def write(self, data: bytes) -> int:
        self._hash.update(data)
        self.size += len(data)
        return self._file.write(data)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._file.seek(offset, whence)

    def read(self, size: int = -1) -> bytes:
        return self._file.read(size)

    def keep(self) -> tuple[Path, str, int]:
        """The finished file (path, sha256, bytes); the caller moves it into place."""
        self._kept = True
        self._file.close()
        return self.path, self._hash.hexdigest(), self.size

    def close(self) -> None:
        self._file.close()
        if not self._kept:
            self.path.unlink(missing_ok=True)


class UploadParser(MultiPartParser):
    """Starlette's multipart parser, with each file part written into an UploadSink instead of a spooled file."""

    def __init__(self, *args, folder: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.folder = folder

    def on_headers_finished(self) -> None:
        super().on_headers_finished()
        upload = self._current_part.file
        if upload is not None:
            spooled = upload.file
            self._files_to_close_on_error.remove(spooled)
            spooled.close()  # still empty: nothing has been written to it
            upload.file = UploadSink(self.folder)  # has no `_rolled`, so UploadFile writes it off the event loop
            self._files_to_close_on_error.append(upload.file)


class UploadRequest(Request):
    async def _get_form(self, *, max_files: int | float = 1000, max_fields: int | float = 1000,
                        max_part_size: int = 1024 * 1024) -> FormData:
        if self._form is None and parse_options_header(self.headers.get("Content-Type"))[0] == b"multipart/form-data":
            parser = UploadParser(self.headers, self.stream(), max_files=max_files, max_fields=max_fields,
                                  max_part_size=max_part_size, folder=self.app.state.settings.uploads_dir)
            try:
                self._form = await parser.parse()
            except MultiPartException as exc:
                raise HTTPException(400, exc.message) from exc
        return await super()._get_form(max_files=max_files, max_fields=max_fields, max_part_size=max_part_size)


class UploadRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def route(request: Request):
            return await handler(UploadRequest(request.scope, request.receive))

        return route
