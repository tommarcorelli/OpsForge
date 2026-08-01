import json

import yaml

from modules.precommit.core import (
    generate_husky_files,
    generate_precommit,
    generate_precommit_yaml,
    get_preset,
    list_hooks,
    list_presets,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "python" in presets
    assert "javascript" in presets
    assert "generic" in presets
    assert "secrets-scan" in presets
    assert "custom" in presets


def test_list_hooks_contains_expected():
    hooks = list_hooks()
    assert "black" in hooks
    assert "eslint" in hooks
    assert "gitleaks" in hooks


def test_validate_config_rejects_unknown_backend():
    errors = validate_config({"preset": "python", "backend": "bogus"})
    assert any("Backend non supporte" in e for e in errors)


def test_validate_config_rejects_unknown_hook():
    config = {"preset": "custom", "backend": "pre-commit", "hooks": ["hook-inexistant"]}
    errors = validate_config(config)
    assert any("Hook inconnu" in e for e in errors)


def test_validate_config_rejects_custom_without_hooks():
    errors = validate_config({"preset": "custom", "backend": "pre-commit"})
    assert any("aucun hook fourni" in e for e in errors)


def test_validate_config_rejects_no_supported_hook_for_backend():
    # black n'a pas de mapping husky
    config = {"preset": "custom", "backend": "husky", "hooks": ["black"]}
    errors = validate_config(config)
    assert any("disponible pour le backend" in e for e in errors)


def test_validate_config_accepts_valid_preset():
    for preset in list_presets():
        if preset == "custom":
            continue
        cfg = get_preset(preset)
        assert validate_config(cfg) == []


def test_generate_precommit_yaml_groups_hooks_by_repo():
    conf = generate_precommit_yaml(get_preset("python"))
    parsed = yaml.safe_load(conf)
    repos = {r["repo"] for r in parsed["repos"]}
    assert "https://github.com/pre-commit/pre-commit-hooks" in repos
    assert "https://github.com/psf/black" in repos
    # 4 hooks du meme repo pre-commit-hooks doivent etre groupes en un seul bloc
    hooks_repo = next(r for r in parsed["repos"] if "pre-commit-hooks" in r["repo"])
    assert len(hooks_repo["hooks"]) == 4


def test_generate_precommit_yaml_is_valid_yaml_for_all_presets():
    for preset in list_presets():
        if preset == "custom":
            continue
        cfg = get_preset(preset)
        cfg["backend"] = "pre-commit"
        conf = generate_precommit_yaml(cfg)
        parsed = yaml.safe_load(conf)
        assert "repos" in parsed


def test_generate_husky_files_lint_staged_is_valid_json():
    files = generate_husky_files(get_preset("javascript"))
    parsed = json.loads(files["lint-staged.config.json"])
    assert "*.{js,jsx,ts,tsx}" in parsed
    assert "eslint --fix" in parsed["*.{js,jsx,ts,tsx}"]


def test_generate_husky_files_hook_script_calls_lint_staged():
    files = generate_husky_files(get_preset("javascript"))
    assert "npx lint-staged" in files[".husky/pre-commit"]


def test_generate_husky_files_gitleaks_adds_raw_command():
    config = {"preset": "custom", "backend": "husky", "hooks": ["gitleaks", "eslint"]}
    files = generate_husky_files(config)
    assert "gitleaks protect --staged" in files[".husky/pre-commit"]


def test_generate_precommit_dispatches_by_backend():
    files_pc = generate_precommit({"preset": "python", "backend": "pre-commit"})
    assert set(files_pc.keys()) == {".pre-commit-config.yaml"}

    files_husky = generate_precommit({"preset": "javascript", "backend": "husky"})
    assert set(files_husky.keys()) == {".husky/pre-commit", "lint-staged.config.json"}


def test_generate_precommit_invalid_config_raises():
    try:
        generate_precommit({"preset": "unknown-preset"})
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass


def test_get_preset_returns_deep_copy():
    p1 = get_preset("python")
    p1["hooks"].append("mypy")
    p2 = get_preset("python")
    assert "mypy" not in p2["hooks"]


def test_secrets_scan_preset_works_on_both_backends():
    for backend in ("pre-commit", "husky"):
        config = {"preset": "secrets-scan", "backend": backend}
        errors = validate_config(config)
        assert errors == []
        files = generate_precommit(config)
        assert files  # au moins un fichier genere
