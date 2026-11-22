"""Touchscreen setup server. Bound to localhost only."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from journal_app.auth import provision_password
from journal_app.files import adopt_tree
from journal_app.cert import generate_certificate, local_names
from journal_app.config import Settings
from journal_app.password import assess
from journal_app.service import ServiceError, start_journal
from journal_app.status import ethernet_up, hostname, ipv4_addresses, journal_url
from journal_app.wifi import WifiError, connect, scan, set_country

STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("journal.setup")


def create_app(
    settings: Settings,
    *,
    wifi_run=None,
    ip_run=None,
    system_run=None,
    iwd_conf: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Secure Journal setup", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.wifi_run = wifi_run
    app.state.ip_run = ip_run
    app.state.system_run = system_run
    app.state.iwd_conf = iwd_conf or Path("/etc/iwd/main.conf")

    @app.middleware("http")
    async def baseline_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "setup.html")

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/state")
    def state() -> JSONResponse:
        return JSONResponse(_state(settings, app.state.ip_run))

    @app.post("/api/wifi/country")
    async def country(request: Request) -> JSONResponse:
        if settings.auth_path.is_file():
            return JSONResponse({"detail": "Setup is already finished."}, status_code=409)
        body = await _json(request)
        code = body.get("country", "")
        if not isinstance(code, str):
            return JSONResponse({"detail": "Choose a Wi-Fi country."}, status_code=400)
        try:
            saved = set_country(code, conf_path=app.state.iwd_conf, run=_wifi(app))
        except WifiError as exc:
            return JSONResponse({"detail": exc.message}, status_code=400)
        return JSONResponse({"country": saved})

    @app.get("/api/wifi/scan")
    def wifi_scan() -> JSONResponse:
        try:
            rows = scan(run=_wifi(app))
        except WifiError as exc:
            return JSONResponse({"detail": exc.message}, status_code=400)
        return JSONResponse({"networks": rows})

    @app.post("/api/wifi/connect")
    async def wifi_connect(request: Request) -> JSONResponse:
        if settings.auth_path.is_file():
            return JSONResponse({"detail": "Setup is already finished."}, status_code=409)
        body = await _json(request)
        ssid = body.get("ssid", "")
        password = body.get("password", "")
        if not isinstance(ssid, str) or not isinstance(password, str):
            return JSONResponse({"detail": "Enter the network and its password."}, status_code=400)
        try:
            connect(ssid, password, iface=settings.wifi_iface, run=_wifi(app))
        except WifiError as exc:
            return JSONResponse({"detail": exc.message}, status_code=400)
        return JSONResponse({"ok": True, "ssid": ssid.strip()})

    @app.post("/api/password/check")
    async def check(request: Request) -> JSONResponse:
        body = await _json(request)
        password = body.get("password", "")
        confirmation = body.get("confirmation", "")
        if not isinstance(password, str) or not isinstance(confirmation, str):
            return JSONResponse({"detail": "Enter the security password twice."}, status_code=400)
        result = assess(password)
        if result["accepted"] and confirmation and password != confirmation:
            result = {**result, "accepted": False, "summary": "The two passwords do not match."}
        return JSONResponse(result)

    @app.post("/api/setup")
    async def finish(request: Request) -> JSONResponse:
        if settings.auth_path.is_file():
            return JSONResponse({"detail": "Setup is already finished."}, status_code=409)
        body = await _json(request)
        password = body.get("password", "")
        confirmation = body.get("confirmation", "")
        if not isinstance(password, str) or not isinstance(confirmation, str):
            return JSONResponse({"detail": "Enter the security password twice."}, status_code=400)
        result = assess(password)
        if not result["accepted"]:
            return JSONResponse({"detail": result["summary"]}, status_code=400)
        if password != confirmation:
            return JSONResponse({"detail": "The two passwords do not match."}, status_code=400)
        addresses = ipv4_addresses(run=_ip(app))
        if not addresses and not ethernet_up(run=_ip(app)):
            return JSONResponse(
                {"detail": "Join a Wi-Fi network, or connect Ethernet, before setting the password."},
                status_code=400,
            )
        try:
            provision_password(settings, password)
            generate_certificate(
                settings.cert_path.parent,
                hostnames=local_names(),
                ips=addresses,
            )
            adopt_tree(settings.data_dir, settings.owner)
            start_journal(settings, run=_system(app))
        except (OSError, ServiceError) as exc:
            log.exception("setup failed")
            return JSONResponse({"detail": str(exc)}, status_code=500)
        return JSONResponse(_state(settings, app.state.ip_run))

    @app.post("/api/service/start")
    def restart() -> JSONResponse:
        if not settings.auth_path.is_file():
            return JSONResponse({"detail": "Finish setup first."}, status_code=409)
        try:
            start_journal(settings, run=_system(app))
        except ServiceError as exc:
            return JSONResponse({"detail": exc.message}, status_code=500)
        return JSONResponse(_state(settings, app.state.ip_run))

    return app


def _state(settings: Settings, ip_run) -> dict[str, Any]:
    name = hostname()
    addresses = ipv4_addresses(run=ip_run) if ip_run else ipv4_addresses()
    configured = settings.auth_path.is_file()
    return {
        "configured": configured,
        "hostname": name,
        "mdns": f"{name}.local",
        "url": journal_url(name, settings.web_port),
        "addresses": addresses,
        "ethernet": ethernet_up(run=ip_run) if ip_run else ethernet_up(),
        "cert_note": (
            "The browser will warn that the certificate is not from a known "
            "authority. That warning is expected. The certificate was created "
            "on this Pi. Continue, then sign in with the security password."
        ),
    }


def _wifi(app: FastAPI):
    return app.state.wifi_run or subprocess.run


def _ip(app: FastAPI):
    return app.state.ip_run or subprocess.run


def _system(app: FastAPI):
    return app.state.system_run or subprocess.run


async def _json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    if settings.setup_host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("The setup server must listen on localhost only.")
    app = create_app(settings)
    uvicorn.run(app, host=settings.setup_host, port=settings.setup_port, log_level="info")


if __name__ == "__main__":
    main()
