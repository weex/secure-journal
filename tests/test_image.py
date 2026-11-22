import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "image" / "layer" / "journal.d" / "hooks" / "customize10-install"
DOTD = ROOT / "image" / "layer" / "journal.d"


def test_firewall_allows_the_journal_and_mdns_only(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "ufw.log"
    fake = bin_dir / "ufw"
    fake.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$UFW_LOG\"\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["UFW_LOG"] = str(log)
    subprocess.run([str(DOTD / "assets" / "enable-firewall.sh")], check=True, env=env)
    text = log.read_text()
    assert "default deny incoming" in text
    assert "allow 443/tcp comment secure-journal" in text
    assert "allow 5353/udp comment avahi" in text
    assert "22" not in text
    assert "--force enable" in text


def test_customize_hook_installs_a_locked_down_root(tmp_path: Path):
    root = tmp_path / "root"
    payload = tmp_path / "payload" / "journal_app"
    payload.mkdir(parents=True)
    (payload / "__init__.py").write_text("# test\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "LAYER_DOTD": str(DOTD),
            "JOURNAL_PAYLOAD": str(tmp_path / "payload"),
            "JOURNAL_HOOK_TEST": "1",
            "IGconf_device_user1": "journal",
            "IGconf_device_hostname": "journal",
        }
    )
    subprocess.run(["bash", str(HOOK), str(root)], check=True, env=env)

    assert (root / "etc/hostname").read_text().strip() == "journal"
    for masked in ("ssh.service", "ssh.socket", "systemd-networkd.service", "getty@tty1.service"):
        link = root / "etc/systemd/system" / masked
        assert link.is_symlink()
        assert os.readlink(link) == "/dev/null"
    kiosk = (root / "etc/systemd/system/secure-journal-kiosk.service").read_text()
    assert "User=journal" in kiosk
    assert "http://127.0.0.1:8080/" in kiosk
    assert (root / "opt/secure-journal/journal_app/__init__.py").is_file()
    wants = root / "etc/systemd/system/multi-user.target.wants"
    assert (wants / "secure-journal-setup.service").is_symlink()
    assert not (wants / "secure-journal.service").exists()
    assert not (wants / "ssh.service").exists()


def test_image_config_matches_the_appliance():
    config = (ROOT / "image/config/journal.yaml").read_text()
    layer = (ROOT / "image/layer/journal.yaml").read_text()
    assert "hostname: journal" in config
    assert "network-manager-iwd" in config
    assert "trixie-minbase.yaml" in config
    assert "X-Env-Layer-Name: journal" in layer
    assert "cage" in layer
    assert "chromium" in layer
    upgrades = (
        DOTD / "customize.overlay/etc/apt/apt.conf.d/52secure-journal-unattended"
    ).read_text()
    assert "rpi-eeprom" in upgrades
    assert "Automatic-Reboot \"true\"" in upgrades
    assert "${distro_codename}" in upgrades
