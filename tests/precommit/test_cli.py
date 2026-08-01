import io
import json
import os
from contextlib import redirect_stdout

from modules.precommit.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_list_presets_prints_all_presets():
    code, out = _run(["--list-presets"])
    assert code == 0
    assert "python" in out
    assert "javascript" in out


def test_missing_config_and_preset_returns_error():
    code, out = _run([])
    assert code == 1
    assert "Erreur" in out


def test_dry_run_preset_prints_preview_without_writing(tmp_path):
    code, out = _run(["--preset", "python", "--dry-run", "-o", str(tmp_path)])
    assert code == 0
    assert ".pre-commit-config.yaml" in out
    assert list(tmp_path.iterdir()) == []


def test_preset_writes_file_to_output_dir(tmp_path):
    code, out = _run(["--preset", "python", "-o", str(tmp_path)])
    assert code == 0
    written = {p.name for p in tmp_path.iterdir()}
    assert ".pre-commit-config.yaml" in written


def test_husky_preset_writes_nested_file(tmp_path):
    code, out = _run(["--preset", "javascript", "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / ".husky" / "pre-commit").exists()
    assert (tmp_path / "lint-staged.config.json").exists()


def test_husky_hook_script_is_executable(tmp_path):
    _run(["--preset", "javascript", "-o", str(tmp_path)])
    script_path = tmp_path / ".husky" / "pre-commit"
    assert os.access(script_path, os.X_OK)


def test_unknown_preset_returns_error():
    code, out = _run(["--preset", "ce-preset-nexiste-pas"])
    assert code == 1
    assert "Erreur" in out


def test_config_file_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "preset": "custom",
        "backend": "pre-commit",
        "hooks": ["gitleaks"],
    }))
    out_dir = tmp_path / "out"
    code, out = _run([str(config_path), "-o", str(out_dir)])
    assert code == 0
    content = (out_dir / ".pre-commit-config.yaml").read_text()
    assert "gitleaks" in content
