from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class ClassroomStaticFiles(StaticFiles):
    """Serve a prebuilt Vite app and fall back to index.html for client routes."""

    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_spa_route(path, scope):
                raise
            response = await super().get_response("index.html", scope)
            response.headers["Cache-Control"] = "no-cache"
        else:
            if _is_hashed_asset(path):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path in {"", ".", "index.html"}:
                response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def mount_classroom_web(app: FastAPI, dist_root: str | Path) -> Path:
    root = Path(dist_root).expanduser().resolve()
    index = root / "index.html"
    assets = root / "assets"
    if not index.is_file() or not assets.is_dir():
        raise RuntimeError(
            "prebuilt classroom web app is incomplete; expected index.html and assets/ "
            f"under {root}"
        )
    app.mount(
        "/",
        ClassroomStaticFiles(directory=root, html=True, check_dir=True),
        name="classroom-web",
    )
    return root


def _is_spa_route(path: str, scope: dict) -> bool:
    if str(scope.get("method", "GET")).upper() not in {"GET", "HEAD"}:
        return False
    normalized = _normalized_static_path(path)
    parts = PurePosixPath(normalized).parts if normalized else ()
    if parts and parts[0].casefold() == "api":
        return False
    return not PurePosixPath(normalized).suffix


def _is_hashed_asset(path: str) -> bool:
    normalized = _normalized_static_path(path)
    return normalized.startswith("assets/") and bool(PurePosixPath(normalized).suffix)


def _normalized_static_path(path: str) -> str:
    """Starlette uses OS-native separators before calling get_response."""

    return path.replace("\\", "/").strip("/")


__all__ = ["ClassroomStaticFiles", "mount_classroom_web"]
