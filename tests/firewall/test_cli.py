import io
import json
import os
from contextlib import redirect_stdout

import pytest

from modules.firewall.cli import main


def _run(argv):
    """Execute main(argv) en capturant stdout, retourne (exit_code, stdout)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_all_presets():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "web-public" in out
    assert "db-private" in out
    assert "ssh-bastion" in out
    assert "custom" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_preset_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "web-public", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "setup-firewall.sh" in out
    assert "jail.local" in out
    # rien ecrit sur disque en dry-run
    assert list(tmp_path.iterdir()) == []


def test_preset_writes_files_to_output_dir(tmp_path):
    code, out = _run(["--preset", "ssh-bastion", "--backend", "nftables", "-o", str(tmp_path)])
    assert code == 0
    written = {p.name for p in tmp_path.iterdir()}
    assert "nftables.conf" in written


def test_preset_with_fail2ban_flag_writes_jail_file(tmp_path):
    code, out = _run(["--preset", "db-private", "--fail2ban", "-o", str(tmp_path)])
    assert code == 0
    written = {p.name for p in tmp_path.iterdir()}
    assert "jail.local" in written


def test_no_fail2ban_flag_overrides_preset_default(tmp_path):
    # web-public a fail2ban=True par defaut ; --no-fail2ban doit le desactiver
    code, out = _run(["--preset", "web-public", "--no-fail2ban", "-o", str(tmp_path)])
    assert code == 0
    written = {p.name for p in tmp_path.iterdir()}
    assert "jail.local" not in written


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "backend": "ufw",
        "rules": [{"port": 8080, "proto": "tcp", "source": "any", "action": "allow", "comment": "app"}],
    }))
    out_dir = tmp_path / "out"
    code, out = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / "setup-firewall.sh").read_text()
    assert "8080" in content


def test_written_shell_script_is_executable(tmp_path):
    _run(["--preset", "web-public", "-o", str(tmp_path)])
    script_path = tmp_path / "setup-firewall.sh"
    assert os.access(script_path, os.X_OK)
