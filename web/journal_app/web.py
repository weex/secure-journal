"""Journal web application. Served on the LAN over HTTPS after setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from journal_app.auth import (
    AuthError,
    KeyCache,
    clear_failures,
    clear_sessions,
    cookie_kwargs,
    end_session,
    login_locked,
    open_auth_db,
    read_session,
    record_failure,
    start_session,
    verify_password,
)
from journal_app.config import Settings
from journal_app.store import StoreError, connect, create_entry, delete_entry, get_entry, list_entries, update_entry

STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("journal")


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Secure Journal", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db = connect(settings)
    app.state.auth_db = open_auth_db(settings)
    app.state.keys = KeyCache()
    clear_sessions(app.state.auth_db)
    app.state.keys.clear()

    @app.middleware("http")
    async def baseline_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE"}:
            origin = request.headers.get("origin")
            host = request.headers.get("host")
            if origin and host:
                expected = f"{request.url.scheme}://{host}"
                if origin.rstrip("/") != expected:
                    return JSONResponse({"detail": "Cross-site request was rejected."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "journal.html")

    @app.post("/api/login")
    async def login(request: Request) -> JSONResponse:
        body = await _json(request)
        password = body.get("password")
        if not isinstance(password, str) or not password or len(password) > 1024:
            return JSONResponse({"detail": "Enter the security password."}, status_code=400)
        ip = request.client.host if request.client else "unknown"
        if login_locked(app.state.auth_db, ip):
            return JSONResponse(
                {"detail": "Too many attempts. Wait 15 minutes."},
                status_code=429,
            )
        try:
            dek = verify_password(settings, password)
        except AuthError as exc:
            if exc.status == 401:
                record_failure(app.state.auth_db, ip)
            return JSONResponse({"detail": exc.message}, status_code=exc.status)
        clear_failures(app.state.auth_db, ip)
        token = start_session(
            app.state.auth_db,
            app.state.keys,
            dek,
            hours=settings.session_hours,
        )
        response = JSONResponse({"ok": True})
        response.set_cookie(value=token, **cookie_kwargs(settings))
        return response

    @app.post("/api/logout")
    def logout(request: Request) -> JSONResponse:
        token = request.cookies.get("sj_session", "")
        if token:
            end_session(app.state.auth_db, app.state.keys, token)
        response = JSONResponse({"ok": True})
        response.delete_cookie(
            "sj_session",
            path="/",
            secure=settings.secure_cookies,
            samesite="strict",
        )
        return response

    @app.get("/api/session")
    def session(request: Request) -> JSONResponse:
        if _session(request) is None:
            return JSONResponse({"detail": "Sign in."}, status_code=401)
        return JSONResponse({"ok": True})

    @app.get("/api/entries")
    def entries(request: Request, q: str = "") -> JSONResponse:
        current = _session(request)
        if current is None:
            return JSONResponse({"detail": "Sign in."}, status_code=401)
        if len(q) > 200:
            return JSONResponse({"detail": "Search is too long."}, status_code=400)
        try:
            rows = list_entries(app.state.db, current.dek, query=q)
        except Exception:
            log.exception("list failed")
            return JSONResponse({"detail": "Could not read the journal."}, status_code=500)
        return JSONResponse({"entries": rows})

    @app.post("/api/entries")
    async def create(request: Request) -> JSONResponse:
        current = _session(request)
        if current is None:
            return JSONResponse({"detail": "Sign in."}, status_code=401)
        body = await _json(request)
        try:
            item = create_entry(
                app.state.db,
                current.dek,
                title=body.get("title", ""),
                doc=body.get("doc") or {"type": "doc", "content": [{"type": "paragraph"}]},
            )
        except StoreError as exc:
            return JSONResponse({"detail": exc.message}, status_code=exc.status)
        return JSONResponse(item, status_code=201)

    @app.get("/api/entries/{entry_id}")
    def read(request: Request, entry_id: str) -> JSONResponse:
        current = _session(request)
        if current is None:
            return JSONResponse({"detail": "Sign in."}, status_code=401)
        try:
            return JSONResponse(get_entry(app.state.db, current.dek, entry_id))
        except StoreError as exc:
            return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.put("/api/entries/{entry_id}")
    async def update(request: Request, entry_id: str) -> JSONResponse:
        current = _session(request)
        if current is None:
            return JSONResponse({"detail": "Sign in."}, status_code=401)
        body = await _json(request)
        try:
            item = update_entry(
                app.state.db,
                current.dek,
                entry_id,
                title=body.get("title", ""),
                doc=body.get("doc") or {"type": "doc", "content": []},
            )
        except StoreError as exc:
            return JSONResponse({"detail": exc.message}, status_code=exc.status)
        return JSONResponse(item)

    @app.delete("/api/entries/{entry_id}")
    def remove(request: Request, entry_id: str) -> JSONResponse:
        current = _session(request)
        if current is None:
            return JSONResponse({"detail": "Sign in."}, status_code=401)
        try:
            delete_entry(app.state.db, entry_id)
        except StoreError as exc:
            return JSONResponse({"detail": exc.message}, status_code=exc.status)
        return JSONResponse({"ok": True})

    def _session(request: Request):
        token = request.cookies.get("sj_session", "")
        return read_session(app.state.auth_db, app.state.keys, token)

    return app


async def _json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    if not settings.auth_path.is_file():
        raise SystemExit(
            f"No password record at {settings.auth_path}. "
            "Finish touchscreen setup, or run: python -m journal_app.init --password '...'"
        )
    if not settings.dev and (not settings.cert_path.is_file() or not settings.key_path.is_file()):
        raise SystemExit(f"Missing TLS certificate in {settings.cert_path.parent}.")
    app = create_app(settings)
    kwargs: dict[str, Any] = {
        "host": settings.web_host,
        "port": settings.web_port,
        "log_level": "info",
    }
    if not settings.dev:
        kwargs["ssl_certfile"] = str(settings.cert_path)
        kwargs["ssl_keyfile"] = str(settings.key_path)
    uvicorn.run(app, **kwargs)


if __name__ == "__main__":
    main()
