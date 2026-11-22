from pathlib import Path

import pytest

from journal_app.wifi import WifiError, connect, parse_wifi_list, render_iwd_conf, set_country, split_nmcli


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_split_and_parse_wifi_list():
    assert split_nmcli(r"*:My\: Network:80:WPA2") == ["*", "My: Network", "80", "WPA2"]
    text = "\n".join(
        [
            " :Cafe:40:WPA2",
            r"*:My\: Network:80:WPA1 WPA2",
            ": :55:WPA2",
            " :Cafe:20:WPA2",
        ]
    )
    rows = parse_wifi_list(text)
    assert [row["ssid"] for row in rows] == ["My: Network", "Cafe"]
    assert rows[0]["in_use"] is True
    assert rows[0]["signal"] == 80


def test_country_is_written_for_iwd(tmp_path: Path):
    conf = tmp_path / "main.conf"
    calls = []

    def run(argv, check=False, capture_output=True, text=True):
        calls.append(argv)
        return Result()

    assert set_country("gb", conf_path=conf, run=run) == "GB"
    text = conf.read_text()
    assert "Country=GB" in text
    assert "EnableNetworkConfiguration=false" in text
    assert ["iw", "reg", "set", "GB"] in calls
    with pytest.raises(WifiError):
        set_country("G;B", conf_path=conf, run=run)


def test_wifi_secret_stays_out_of_argv(tmp_path: Path):
    secret = "p@ss:word 99"
    seen = []

    def run(argv, check=False, capture_output=True, text=True):
        seen.append(list(argv))
        if "passwd-file" in argv:
            path = argv[argv.index("passwd-file") + 1]
            seen.append(["FILE", Path(path).read_text()])
        return Result()

    connect("My Network", secret, iface="wlan0", run=run)
    flat = [" ".join(item) for item in seen if item[0] != "FILE"]
    assert all(secret not in line for line in flat)
    files = [item[1] for item in seen if item[0] == "FILE"]
    assert files == [f"802-11-wireless-security.psk:{secret}\n"]
    assert any("passwd-file" in item for item in seen if item[0] != "FILE")


def test_render_replaces_an_existing_country():
    updated = render_iwd_conf("[General]\nCountry=US\n", "DE")
    assert "Country=DE" in updated
    assert "Country=US" not in updated
