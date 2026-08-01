import io
import json
from contextlib import redirect_stdout

from modules.sops.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_all_presets():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "solo-dev" in out
    assert "multi-env" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "multi-env", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert "creation_rules" in out
    assert list(tmp_path.iterdir()) == []


def test_preset_writes_two_files(tmp_path):
    code, out = _run(["--preset", "k8s-secrets", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / ".sops.yaml").exists()
    assert (tmp_path / "sops-diff.gitattributes").exists()
    assert "age-keygen" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "rules": [{"path_regex": "secrets/.*\\.yaml$", "age_recipients": ["age1" + "a" * 40]}],
    }), encoding="utf-8")
    out_dir = tmp_path / "out"
    code, _ = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / ".sops.yaml").read_text(encoding="utf-8")
    assert "secrets/" in content


def test_invalid_config_returns_error(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"preset": "custom", "rules": []}), encoding="utf-8")
    code, out = _run([str(config_path), "-o", str(tmp_path / "out")])
    assert code == 1
    assert "Erreur" in out
