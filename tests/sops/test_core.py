import yaml

from modules.sops.core import (
    GITATTRIBUTES_SNIPPET_NAME,
    SOPS_CONFIG_NAME,
    generate_gitattributes_snippet,
    generate_sops,
    generate_sops_yaml,
    get_preset,
    list_presets,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "solo-dev" in presets
    assert "team-shared" in presets
    assert "multi-env" in presets
    assert "k8s-secrets" in presets
    assert "terraform-tfvars" in presets
    assert "custom" in presets


def test_all_presets_are_valid():
    for name in list_presets():
        if name == "custom":
            continue
        assert validate_config(get_preset(name)) == [], name


def test_get_preset_returns_deep_copy():
    p1 = get_preset("solo-dev")
    p1["rules"].append({"path_regex": "x", "age_recipients": ["age1x"]})
    p2 = get_preset("solo-dev")
    assert len(p2["rules"]) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_validate_rejects_no_rules():
    errors = validate_config({"preset": "custom", "rules": []})
    assert any("Aucune regle" in e for e in errors)


def test_validate_rejects_missing_path_regex():
    config = {"preset": "custom", "rules": [{"age_recipients": ["age1" + "a" * 30]}]}
    errors = validate_config(config)
    assert any("chemin manquante" in e for e in errors)


def test_validate_rejects_invalid_path_regex():
    config = {"preset": "custom", "rules": [{"path_regex": "[unclosed", "age_recipients": ["age1" + "a" * 30]}]}
    errors = validate_config(config)
    assert any("chemin invalide" in e for e in errors)


def test_validate_rejects_duplicate_path_regex():
    rule = {"path_regex": "secrets/.*", "age_recipients": ["age1" + "a" * 30]}
    config = {"preset": "custom", "rules": [dict(rule), dict(rule)]}
    errors = validate_config(config)
    assert any("deja utilisee" in e for e in errors)


def test_validate_rejects_no_recipients():
    config = {"preset": "custom", "rules": [{"path_regex": "secrets/.*", "age_recipients": []}]}
    errors = validate_config(config)
    assert any("aucun destinataire" in e.lower() for e in errors)


def test_validate_rejects_private_key_as_recipient():
    config = {
        "preset": "custom",
        "rules": [{
            "path_regex": "secrets/.*",
            "age_recipients": ["AGE-SECRET-KEY-1QZ9F0J..."],
        }],
    }
    errors = validate_config(config)
    assert any("cle PRIVEE" in e for e in errors)


def test_validate_rejects_malformed_recipient():
    config = {"preset": "custom", "rules": [{"path_regex": "secrets/.*", "age_recipients": ["pas-une-cle"]}]}
    errors = validate_config(config)
    assert any("invalide" in e for e in errors)


def test_validate_accepts_readable_placeholder_recipient():
    # Meme convention que le module ssh : un placeholder lisible embarque
    # dans le format attendu (prefixe age1) doit passer la validation.
    config = {
        "preset": "custom",
        "rules": [{"path_regex": "secrets/.*", "age_recipients": ["age1REMPLACE_PAR_TA_CLE_PUBLIQUE"]}],
    }
    assert validate_config(config) == []


def test_validate_rejects_invalid_encrypted_regex():
    config = {
        "preset": "custom",
        "rules": [{
            "path_regex": "secrets/.*",
            "age_recipients": ["age1" + "a" * 30],
            "encrypted_regex": "[unclosed",
        }],
    }
    errors = validate_config(config)
    assert any("encrypted_regex" in e for e in errors)


def test_validate_rejects_unknown_input_type():
    config = {
        "preset": "custom",
        "rules": [{
            "path_regex": "secrets/.*",
            "age_recipients": ["age1" + "a" * 30],
            "input_type": "xml",
        }],
    }
    errors = validate_config(config)
    assert any("type d'entree non supporte" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Generation .sops.yaml
# ---------------------------------------------------------------------------
def test_sops_yaml_is_valid_yaml_for_all_presets():
    for name in list_presets():
        if name == "custom":
            continue
        content = generate_sops_yaml(get_preset(name))
        parsed = yaml.safe_load(content)
        assert "creation_rules" in parsed
        assert len(parsed["creation_rules"]) == len(get_preset(name)["rules"])


def test_sops_yaml_age_is_comma_joined_string():
    content = generate_sops_yaml(get_preset("team-shared"))
    parsed = yaml.safe_load(content)
    age_value = parsed["creation_rules"][0]["age"]
    assert isinstance(age_value, str)
    assert "," in age_value


def test_sops_yaml_multi_env_preserves_rule_order():
    content = generate_sops_yaml(get_preset("multi-env"))
    parsed = yaml.safe_load(content)
    paths = [r["path_regex"] for r in parsed["creation_rules"]]
    assert paths == [
        r"environments/dev/.*\.yaml$",
        r"environments/staging/.*\.yaml$",
        r"environments/prod/.*\.yaml$",
    ]


def test_sops_yaml_k8s_includes_encrypted_regex():
    content = generate_sops_yaml(get_preset("k8s-secrets"))
    parsed = yaml.safe_load(content)
    assert parsed["creation_rules"][0]["encrypted_regex"] == "^(data|stringData)$"


def test_sops_yaml_omits_encrypted_regex_when_absent():
    content = generate_sops_yaml(get_preset("solo-dev"))
    parsed = yaml.safe_load(content)
    assert "encrypted_regex" not in parsed["creation_rules"][0]


def test_sops_yaml_terraform_includes_input_type():
    content = generate_sops_yaml(get_preset("terraform-tfvars"))
    parsed = yaml.safe_load(content)
    assert parsed["creation_rules"][0]["input_type"] == "json"


# ---------------------------------------------------------------------------
# Generation gitattributes
# ---------------------------------------------------------------------------
def test_gitattributes_snippet_mentions_sopsdiffer():
    content = generate_gitattributes_snippet(get_preset("solo-dev"))
    assert "diff=sopsdiffer" in content
    assert "git config diff.sopsdiffer.textconv" in content


def test_gitattributes_snippet_json_pattern_for_terraform_preset():
    content = generate_gitattributes_snippet(get_preset("terraform-tfvars"))
    assert "*.json diff=sopsdiffer" in content


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------
def test_generate_sops_returns_two_files():
    files = generate_sops(get_preset("solo-dev"))
    assert set(files) == {SOPS_CONFIG_NAME, GITATTRIBUTES_SNIPPET_NAME}
    assert SOPS_CONFIG_NAME == ".sops.yaml"


def test_generate_sops_invalid_config_raises():
    try:
        generate_sops({"preset": "custom", "rules": []})
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass


def test_generate_sops_never_contains_a_plausible_private_key():
    # Filet de securite : aucun preset ne doit jamais embarquer une cle
    # AGE-SECRET-KEY, meme par erreur de copier-coller lors d'un futur ajout.
    for name in list_presets():
        if name == "custom":
            continue
        content = generate_sops_yaml(get_preset(name))
        assert "AGE-SECRET-KEY" not in content
