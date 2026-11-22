from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from journal_app.auth import (
    clear_sessions,
    login_locked,
    open_auth_db,
    provision_password,
    record_failure,
)
from journal_app.config import Settings
from journal_app.web import create_app

PASSWORD = "Correct-Horse-Battery"


def _client(settings: Settings) -> TestClient:
    provision_password(settings, PASSWORD)
    app = create_app(settings)
    return TestClient(app, base_url="https://journal.local")


def test_login_session_and_rejection(settings):
    client = _client(settings)
    blocked = client.get("/api/entries")
    assert blocked.status_code == 401

    wrong = client.post("/api/login", json={"password": "not-the-password"})
    assert wrong.status_code == 401

    good = client.post("/api/login", json={"password": PASSWORD})
    assert good.status_code == 200
    assert "sj_session" in good.cookies
    cookie = good.cookies["sj_session"]
    assert client.cookies["sj_session"]
    header = good.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=strict" in header

    created = client.post(
        "/api/entries",
        json={"title": "First", "doc": {"type": "doc", "content": []}},
    )
    assert created.status_code == 201
    listed = client.get("/api/entries")
    assert listed.json()["entries"][0]["title"] == "First"

    client.post("/api/logout")
    assert client.get("/api/entries").status_code == 401

    # A cookie from before logout is not enough, and the token is not the password.
    assert PASSWORD not in cookie


def test_rate_limit_locks_an_address(settings):
    client = _client(settings)
    for _ in range(8):
        response = client.post("/api/login", json={"password": "nope-nope-nope"})
        assert response.status_code == 401
    locked = client.post("/api/login", json={"password": PASSWORD})
    assert locked.status_code == 429


def test_cross_site_post_is_rejected(settings):
    client = _client(settings)
    response = client.post(
        "/api/login",
        json={"password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_restart_forgets_sessions(settings):
    client = _client(settings)
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200
    clear_sessions(open_auth_db(settings))
    # A new app process starts with an empty key cache.
    again = TestClient(create_app(settings), base_url="https://journal.local")
    again.cookies.set("sj_session", client.cookies["sj_session"])
    assert again.get("/api/session").status_code == 401


def test_production_argon_parameters_can_verify(tmp_path):
    strong = Settings(
        data_dir=tmp_path / "unused",
        argon_time=2,
        argon_memory=65536,
        argon_parallelism=1,
    )
    from journal_app.auth import hasher_for

    stored = hasher_for(strong).hash("Correct-Horse-Battery")
    assert stored.startswith("$argon2id$")
    hasher_for(strong).verify(stored, "Correct-Horse-Battery")


def test_lock_window_helper(settings):
    conn = open_auth_db(settings)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(8):
        record_failure(conn, "10.0.0.8", now)
    assert login_locked(conn, "10.0.0.8", now + timedelta(minutes=1))
    assert not login_locked(conn, "10.0.0.8", now + timedelta(minutes=16))
