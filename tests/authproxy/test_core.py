import yaml

from modules.authproxy.core import (
    generate_authelia_configuration,
    generate_authelia_users_database,
    generate_authproxy,
    generate_oauth2_proxy_cfg,
    generate_oauth2_proxy_nginx_snippet,
    get_preset,
    list_presets,
    list_presets_by_engine,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "github-org" in presets
    assert "google-domain" in presets
    assert "homelab-simple" in presets
    assert "custom" in presets


def test_list_presets_by_engine_splits_correctly():
    oauth2 = list_presets_by_engine("oauth2-proxy")
    authelia = list_presets_by_engine("authelia")
    assert "github-org" in oauth2
    assert "github-org" not in authelia
    assert "homelab-simple" in authelia
    assert "homelab-simple" not in oauth2


def test_all_presets_are_valid():
    for name in list_presets():
        if name == "custom":
            continue
        assert validate_config(get_preset(name)) == [], name


def test_get_preset_returns_deep_copy():
    p1 = get_preset("homelab-simple")
    p1["users"].append({"username": "ajoute", "groups": ["x"]})
    p2 = get_preset("homelab-simple")
    assert len(p2["users"]) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_validate_rejects_unknown_engine():
    errors = validate_config({"preset": "custom", "engine": "keycloak-direct"})
    assert any("Moteur non supporte" in e for e in errors)


def test_validate_oauth2_rejects_unknown_provider():
    config = {"preset": "custom", "engine": "oauth2-proxy", "provider": "facebook"}
    errors = validate_config(config)
    assert any("Fournisseur non supporte" in e for e in errors)


def test_validate_oauth2_rejects_missing_upstream():
    config = get_preset("github-org")
    config["upstream"] = ""
    errors = validate_config(config)
    assert any("Upstream manquant" in e for e in errors)


def test_validate_oauth2_github_requires_org():
    config = get_preset("github-org")
    config["github_org"] = ""
    errors = validate_config(config)
    assert any("Organisation GitHub manquante" in e for e in errors)


def test_validate_oauth2_google_requires_email_domains():
    config = get_preset("google-domain")
    config["email_domains"] = []
    errors = validate_config(config)
    assert any("Aucun domaine email autorise" in e for e in errors)


def test_validate_oauth2_oidc_requires_issuer():
    config = get_preset("generic-oidc")
    config["oidc_issuer_url"] = ""
    errors = validate_config(config)
    assert any("emetteur OIDC manquante" in e for e in errors)


def test_validate_authelia_rejects_invalid_domain():
    config = get_preset("homelab-simple")
    config["domain"] = "pas un domaine"
    errors = validate_config(config)
    assert any("Domaine invalide" in e for e in errors)


def test_validate_authelia_rejects_no_users():
    config = get_preset("homelab-simple")
    config["users"] = []
    errors = validate_config(config)
    assert any("Aucun utilisateur" in e for e in errors)


def test_validate_authelia_rejects_user_without_groups():
    config = get_preset("homelab-simple")
    config["users"] = [{"username": "sansgroupe", "groups": []}]
    errors = validate_config(config)
    assert any("aucun groupe" in e for e in errors)


def test_validate_authelia_rejects_duplicate_username():
    config = get_preset("homelab-simple")
    config["users"] = [
        {"username": "admin", "groups": ["a"]},
        {"username": "admin", "groups": ["b"]},
    ]
    errors = validate_config(config)
    assert any("plusieurs fois" in e for e in errors)


def test_validate_authelia_rejects_no_rules():
    config = get_preset("homelab-simple")
    config["access_rules"] = []
    errors = validate_config(config)
    assert any("Aucune regle d'acces" in e for e in errors)


def test_validate_authelia_rejects_unknown_policy():
    config = get_preset("homelab-simple")
    config["access_rules"] = [{"domain": "*.exemple.com", "policy": "maybe"}]
    errors = validate_config(config)
    assert any("politique invalide" in e for e in errors)


def test_validate_authelia_rejects_subject_referencing_undefined_group():
    config = get_preset("homelab-simple")
    config["access_rules"] = [{"domain": "*.exemple.com", "policy": "one_factor", "subject": "group:fantome"}]
    errors = validate_config(config)
    assert any("aucun utilisateur defini" in e for e in errors)


def test_validate_authelia_rejects_subject_referencing_undefined_user():
    config = get_preset("homelab-simple")
    config["access_rules"] = [{"domain": "*.exemple.com", "policy": "one_factor", "subject": "user:fantome"}]
    errors = validate_config(config)
    assert any("n'est pas defini" in e for e in errors)


def test_validate_authelia_rejects_malformed_subject():
    config = get_preset("homelab-simple")
    config["access_rules"] = [{"domain": "*.exemple.com", "policy": "one_factor", "subject": "admin"}]
    errors = validate_config(config)
    assert any("sujet invalide" in e.lower() for e in errors)


def test_validate_authelia_rejects_all_deny_rules():
    config = get_preset("homelab-simple")
    config["access_rules"] = [{"domain": "*.exemple.com", "policy": "deny"}]
    errors = validate_config(config)
    assert any("refusent l'acces" in e for e in errors)


def test_validate_authelia_accepts_valid_subject_forms():
    config = get_preset("two-factor-sensitive")
    assert validate_config(config) == []


# ---------------------------------------------------------------------------
# Generation oauth2-proxy
# ---------------------------------------------------------------------------
def test_oauth2_cfg_contains_provider_and_upstream():
    cfg = generate_oauth2_proxy_cfg(get_preset("github-org"))
    assert 'provider = "github"' in cfg
    assert 'upstreams = ["http://127.0.0.1:8080"]' in cfg


def test_oauth2_cfg_generates_random_cookie_secret_each_time():
    cfg1 = generate_oauth2_proxy_cfg(get_preset("github-org"))
    cfg2 = generate_oauth2_proxy_cfg(get_preset("github-org"))
    secret1 = [ln for ln in cfg1.splitlines() if ln.startswith("cookie_secret")][0]
    secret2 = [ln for ln in cfg2.splitlines() if ln.startswith("cookie_secret")][0]
    assert secret1 != secret2


def test_oauth2_cfg_github_includes_org_not_email_domains_block():
    cfg = generate_oauth2_proxy_cfg(get_preset("github-org"))
    assert "github_org" in cfg


def test_oauth2_cfg_oidc_includes_issuer():
    cfg = generate_oauth2_proxy_cfg(get_preset("generic-oidc"))
    assert "oidc_issuer_url" in cfg


def test_oauth2_nginx_snippet_points_to_upstream():
    snippet = generate_oauth2_proxy_nginx_snippet(get_preset("github-org"))
    assert "proxy_pass http://127.0.0.1:8080;" in snippet
    assert "auth_request /oauth2/auth;" in snippet


# ---------------------------------------------------------------------------
# Generation Authelia
# ---------------------------------------------------------------------------
def test_authelia_configuration_is_valid_yaml():
    for name in list_presets_by_engine("authelia"):
        conf = generate_authelia_configuration(get_preset(name))
        parsed = yaml.safe_load(conf)
        assert "access_control" in parsed
        assert "session" in parsed


def test_authelia_configuration_access_rules_order_preserved():
    conf = generate_authelia_configuration(get_preset("multi-domain"))
    parsed = yaml.safe_load(conf)
    domains = [r["domain"] for r in parsed["access_control"]["rules"]]
    assert domains == ["public.exemple.com", "admin.exemple.com", "*.exemple.com"]


def test_authelia_configuration_secrets_differ_each_generation():
    conf1 = generate_authelia_configuration(get_preset("homelab-simple"))
    conf2 = generate_authelia_configuration(get_preset("homelab-simple"))
    assert yaml.safe_load(conf1)["jwt_secret"] != yaml.safe_load(conf2)["jwt_secret"]


def test_authelia_configuration_sqlite_vs_postgres_storage():
    config = get_preset("homelab-simple")
    conf_sqlite = yaml.safe_load(generate_authelia_configuration(config))
    assert "local" in conf_sqlite["storage"]

    config["storage_backend"] = "postgres"
    conf_pg = yaml.safe_load(generate_authelia_configuration(config))
    assert "postgres" in conf_pg["storage"]


def test_authelia_users_database_is_valid_yaml():
    content = generate_authelia_users_database(get_preset("homelab-simple"))
    parsed = yaml.safe_load(content)
    assert "admin" in parsed["users"]
    assert parsed["users"]["admin"]["groups"] == ["admins"]


def test_authelia_users_database_never_contains_plaintext_password():
    content = generate_authelia_users_database(get_preset("homelab-simple"))
    assert "$argon2id$" in content
    assert "REMPLACE_PAR_TON_HASH" in content


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------
def test_generate_authproxy_oauth2_returns_two_files():
    files = generate_authproxy(get_preset("github-org"))
    assert set(files) == {"oauth2-proxy.cfg", "nginx-auth-snippet.conf"}


def test_generate_authproxy_authelia_returns_two_files():
    files = generate_authproxy(get_preset("homelab-simple"))
    assert set(files) == {"configuration.yml", "users_database.yml"}


def test_generate_authproxy_invalid_config_raises():
    try:
        generate_authproxy({"preset": "custom", "engine": "oauth2-proxy", "provider": "github"})
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass
