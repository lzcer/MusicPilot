from __future__ import annotations

import re

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        path = path.replace("\\", "/")
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            accepts_html = any(
                name == b"accept" and b"text/html" in value
                for name, value in scope.get("headers", [])
            )
            if (
                error.status_code != 404
                or scope["method"] not in {"GET", "HEAD"}
                or not accepts_html
                or path.split("/", 1)[0] in {"api", "assets"}
                or "." in path.rsplit("/", 1)[-1]
            ):
                raise
            response = await super().get_response("index.html", scope)

        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
        elif path == "sw.js":
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith("assets/") and re.search(r"-[\w-]{8,}\.[\w.]+$", path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        if path == "manifest.webmanifest" and response.status_code == 200:
            response.headers["Content-Type"] = "application/manifest+json"
        return response
