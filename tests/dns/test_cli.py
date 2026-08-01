import io
import json
from contextlib import redirect_stdout

from modules.dns.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_all_presets():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "site-statique" in out
    assert "domaine-mail" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "site-statique", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "ORIGIN" in out
    assert list(tmp_path.iterdir()) == []


def test_bind_preset_writes_zone_file(tmp_path):
    code, out = _run(["--preset", "site-statique", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "exemple.com.zone").exists()
    assert "zone maitre" in out


def test_route53_engine_writes_json_file(tmp_path):
    code, out = _run(["--preset", "site-statique", "--engine", "route53", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "exemple.com.route53.json").exists()
    assert "change-resource-record-sets" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "engine": "bind",
        "domain": "monsite.dev",
        "ttl": 3600,
        "nameservers": ["ns1.monsite.dev."],
        "soa": {"primary_ns": "ns1.monsite.dev.", "admin_email": "admin.monsite.dev."},
        "records": [{"type": "A", "name": "@", "value": "203.0.113.5"}],
    }), encoding="utf-8")
    out_dir = tmp_path / "out"
    code, _ = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / "monsite.dev.zone").read_text(encoding="utf-8")
    assert "203.0.113.5" in content


def test_invalid_config_returns_error(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"preset": "custom", "domain": "x.com", "records": []}), encoding="utf-8")
    code, out = _run([str(config_path), "-o", str(tmp_path / "out")])
    assert code == 1
    assert "Erreur" in out
