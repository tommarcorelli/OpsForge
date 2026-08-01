import io
import json
from contextlib import redirect_stdout

from modules.ssh.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_presets_with_role():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "acces-bastion" in out
    assert "serveur-durci" in out
    assert "[client]" in out
    assert "[server]" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "acces-bastion", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "Host bastion" in out
    assert list(tmp_path.iterdir()) == []


def test_client_preset_writes_config_file(tmp_path):
    code, out = _run(["--preset", "poste-de-travail", "-o", str(tmp_path)])
    assert code == 0
    content = (tmp_path / "ssh_config").read_text(encoding="utf-8")
    assert "Host prod-web" in content
    assert "chmod 600" in out


def test_server_preset_writes_nested_fragment(tmp_path):
    code, out = _run(["--preset", "serveur-durci", "-o", str(tmp_path)])
    assert code == 0
    fragment = tmp_path / "sshd_config.d" / "10-opsforge-durcissement.conf"
    assert fragment.exists()
    assert "PermitRootLogin no" in fragment.read_text(encoding="utf-8")
    assert "sshd -t" in out


def test_restricted_key_preset_writes_two_files(tmp_path):
    code, _ = _run(["--preset", "cle-restreinte", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "authorized_keys").exists()
    assert (tmp_path / "sshd_config.d" / "10-opsforge-durcissement.conf").exists()


def test_port_override_applies(tmp_path):
    code, out = _run(["--preset", "serveur-durci", "--port", "2222", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "Port 2222" in out


def test_allow_groups_override_applies(tmp_path):
    code, out = _run([
        "--preset", "serveur-durci", "--allow-groups", "admins", "devops",
        "--dry-run", "-o", str(tmp_path),
    ])
    assert code == 0
    assert "AllowGroups admins devops" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "lab", "hostname": "192.168.1.50", "user": "tom", "port": 2222}],
    }), encoding="utf-8")
    out_dir = tmp_path / "out"
    code, _ = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / "ssh_config").read_text(encoding="utf-8")
    assert "Host lab" in content
    assert "Port 2222" in content


def test_invalid_config_returns_error(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "lab"}],
    }), encoding="utf-8")
    code, out = _run([str(config_path), "-o", str(tmp_path / "out")])
    assert code == 1
    assert "Erreur" in out
