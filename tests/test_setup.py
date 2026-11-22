from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from journal_app.setup_server import create_app
from journal_app.status import ethernet_up, ipv4_addresses

PASSWORD = "Correct-Horse-Battery"


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _ip(output: str):
    def run(argv, **_kwargs):
        return Result(stdout=output)

    return run


ONLINE = _ip("2: eth0    inet 192.168.4.20/24 brd 192.168.4.255 scope global eth0\n")
OFFLINE = _ip("1: lo    inet 127.0.0.1/8 scope host lo\n")


def test_setup_requires_a_network_then_stores_only_a_hash(settings, tmp_path: Path):
    calls = []

    def wifi(argv, check=False, capture_output=True, text=True):
        calls.append(list(argv))
        if argv[:2] == ["nmcli", "-t"]:
            return Result(stdout=" :Cafe:70:WPA2\n")
        if "passwd-file" in argv:
            calls.append(["FILE", Path(argv[argv.index("passwd-file") + 1]).read_text()])
        return Result()

    def system(argv, check=False, capture_output=True, text=True):
        calls.append(list(argv))
        return Result()

    app = create_app(
        replace(settings, enable_systemctl=True),
        wifi_run=wifi,
        ip_run=OFFLINE,
        system_run=system,
        iwd_conf=tmp_path / "iwd.conf",
    )
    client = TestClient(app)
    assert client.get("/health").json() == {"ok": True}
    refused = client.post(
        "/api/setup",
        json={"password": PASSWORD, "confirmation": PASSWORD},
    )
    assert refused.status_code == 400

    app.state.ip_run = ONLINE
    weak = client.post("/api/setup", json={"password": "short", "confirmation": "short"})
    assert weak.status_code == 400

    mismatch = client.post(
        "/api/setup",
        json={"password": PASSWORD, "confirmation": PASSWORD + "x"},
    )
    assert mismatch.status_code == 400

    country = client.post("/api/wifi/country", json={"country": "us"})
    assert country.status_code == 200
    scan = client.get("/api/wifi/scan")
    assert scan.json()["networks"][0]["ssid"] == "Cafe"
    joined = client.post("/api/wifi/connect", json={"ssid": "Cafe", "password": "cafe-secret"})
    assert joined.status_code == 200
    assert all("cafe-secret" not in " ".join(item) for item in calls if item[0] != "FILE")

    done = client.post("/api/setup", json={"password": PASSWORD, "confirmation": PASSWORD})
    assert done.status_code == 200
    body = done.json()
    assert body["configured"] is True
    assert body["url"].startswith("https://")
    assert "192.168.4.20" in body["addresses"]
    raw = settings.auth_path.read_text()
    assert PASSWORD not in raw
    assert "$argon2id$" in raw
    assert settings.cert_path.is_file()
    assert settings.key_path.is_file()
    again = client.post("/api/setup", json={"password": PASSWORD, "confirmation": PASSWORD})
    assert again.status_code == 409
    assert ["systemctl", "enable", "--now", "secure-journal.service"] in calls


def test_missing_ip_command_leaves_the_screen_usable():
    def run(argv, **_kwargs):
        raise FileNotFoundError(argv[0])

    assert ipv4_addresses(run=run) == []
    assert ethernet_up(run=run) is False


def test_setup_host_defaults_to_localhost():
    from journal_app.config import Settings

    assert Settings(data_dir=Path("data")).setup_host == "127.0.0.1"
