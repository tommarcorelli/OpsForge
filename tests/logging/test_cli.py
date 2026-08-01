import io
import json
import os
from contextlib import redirect_stdout

from modules.logging.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_all_presets():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "docker-loki" in out
    assert "nginx-loki" in out
    assert "syslog-elasticsearch" in out
    assert "app-json-loki" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_preset_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "docker-loki", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "fluent-bit.conf" in out
    assert list(tmp_path.iterdir()) == []


def test_preset_writes_file_to_output_dir(tmp_path):
    code, out = _run(["--preset", "nginx-loki", "--backend", "vector", "-o", str(tmp_path)])
    assert code == 0
    written = {p.name for p in tmp_path.iterdir()}
    assert "vector.toml" in written


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "backend": "fluent-bit",
        "sources": [{"type": "tail", "path": "/var/log/custom/*.log", "tag": "custom"}],
        "destination": {"type": "stdout"},
    }))
    out_dir = tmp_path / "out"
    code, out = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / "fluent-bit.conf").read_text()
    assert "/var/log/custom/*.log" in content


def test_invalid_config_file_returns_error(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"preset": "custom", "backend": "fluent-bit", "sources": []}))
    code, out = _run([str(config_path), "-o", str(tmp_path / "out")])
    assert code == 1
    assert "Erreur" in out
