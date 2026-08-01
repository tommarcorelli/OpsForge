import io
import json
from contextlib import redirect_stdout

from modules.authproxy.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_presets_with_engine():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "github-org" in out
    assert "homelab-simple" in out
    assert "[oauth2-proxy]" in out
    assert "[authelia]" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "github-org", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "provider" in out
    assert list(tmp_path.iterdir()) == []


def test_oauth2_preset_writes_two_files(tmp_path):
    code, out = _run(["--preset", "github-org", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "oauth2-proxy.cfg").exists()
    assert (tmp_path / "nginx-auth-snippet.conf").exists()
    assert "nginx-auth-snippet.conf" in out


def test_authelia_preset_writes_two_files(tmp_path):
    code, out = _run(["--preset", "homelab-simple", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "configuration.yml").exists()
    assert (tmp_path / "users_database.yml").exists()
    assert "argon2" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "engine": "oauth2-proxy",
        "provider": "github",
        "upstream": "http://127.0.0.1:3000",
        "redirect_url": "https://auth.exemple.com/oauth2/callback",
        "client_id": "id",
        "client_secret": "secret",
        "github_org": "monorg",
    }), encoding="utf-8")
    out_dir = tmp_path / "out"
    code, _ = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / "oauth2-proxy.cfg").read_text(encoding="utf-8")
    assert "monorg" in content


def test_invalid_config_returns_error(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "engine": "oauth2-proxy",
        "provider": "github",
    }), encoding="utf-8")
    code, out = _run([str(config_path), "-o", str(tmp_path / "out")])
    assert code == 1
    assert "Erreur" in out
