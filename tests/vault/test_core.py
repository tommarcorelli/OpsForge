"""Tests du coeur du module Vault d'OpsForge."""

import os

import pytest

from modules.vault.core import (
    AUDIT_DEVICE_CATALOG,
    BOOTSTRAP_FILENAME,
    CONFIG_FILENAME,
    PRESETS,
    SEAL_TYPES,
    STORAGE_BACKENDS,
    generate_bootstrap_script,
    generate_files,
    generate_policies,
    generate_policy_file,
    generate_server_config,
    get_preset,
    list_audit_devices,
    list_auth_methods,
    list_presets,
    list_seal_types,
    list_secrets_engines,
    list_storage_backends,
    validate_config,
    write_files,
)


def _valid_config(**overrides):
    base = {
        "server": {
            "storage": "file",
            "storage_args": {"path": "/opt/vault/data"},
            "listener_address": "127.0.0.1:8200",
            "listener_tls_disable": True,
            "seal": "shamir",
            "ui": True,
        },
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_storage_manquant_rejete():
    errors = validate_config({})
    assert any("storage" in e for e in errors)


def test_storage_inconnu_rejete():
    errors = validate_config({"server": {"storage": "s3"}})
    assert any("inconnu" in e for e in errors)


def test_storage_args_requis_manquants_rejetes():
    errors = validate_config({"server": {"storage": "raft", "storage_args": {"path": "/data"}}})
    assert any("node_id" in e for e in errors)


def test_storage_args_avec_defauts_ok():
    # "file" a un defaut pour "path" : pas besoin de le fournir explicitement.
    errors = validate_config({"server": {"storage": "file"}})
    assert errors == []


def test_seal_inconnu_rejete():
    errors = validate_config({"server": {"storage": "file", "seal": "vault-transit-v9"}})
    assert any("seal" in e.lower() for e in errors)


def test_seal_args_requis_manquants_rejetes():
    errors = validate_config({"server": {"storage": "file", "seal": "awskms"}})
    assert any("region" in e for e in errors)


def test_seal_shamir_sans_args_ok():
    errors = validate_config(_valid_config())
    assert errors == []


def test_policy_sans_nom_rejetee():
    cfg = _valid_config(policies=[{"rules": [{"path": "secret/*", "capabilities": ["read"]}]}])
    errors = validate_config(cfg)
    assert any("name" in e for e in errors)


def test_policy_nom_invalide_rejete():
    cfg = _valid_config(policies=[{"name": "app policy!", "rules": [{"path": "secret/*", "capabilities": ["read"]}]}])
    errors = validate_config(cfg)
    assert any("invalide" in e for e in errors)


def test_policy_sans_regle_rejetee():
    cfg = _valid_config(policies=[{"name": "empty", "rules": []}])
    errors = validate_config(cfg)
    assert any("au moins une regle" in e for e in errors)


def test_policy_capability_inconnue_rejetee():
    cfg = _valid_config(policies=[{
        "name": "bad",
        "rules": [{"path": "secret/*", "capabilities": ["fly"]}],
    }])
    errors = validate_config(cfg)
    assert any("capability inconnue" in e for e in errors)


def test_policy_path_manquant_rejete():
    cfg = _valid_config(policies=[{"name": "p", "rules": [{"capabilities": ["read"]}]}])
    errors = validate_config(cfg)
    assert any("path est requis" in e for e in errors)


def test_auth_method_type_inconnu_rejete():
    cfg = _valid_config(auth_methods=[{"type": "saml", "path": "saml"}])
    errors = validate_config(cfg)
    assert any("auth_methods" in e for e in errors)


def test_auth_method_path_manquant_rejete():
    cfg = _valid_config(auth_methods=[{"type": "userpass"}])
    errors = validate_config(cfg)
    assert any("path est requis" in e for e in errors)


def test_secrets_engine_type_inconnu_rejete():
    cfg = _valid_config(secrets_engines=[{"type": "redis", "path": "redis"}])
    errors = validate_config(cfg)
    assert any("secrets_engines" in e for e in errors)


def test_audit_device_type_inconnu_rejete():
    cfg = _valid_config(audit_devices=[{"type": "kafka"}])
    errors = validate_config(cfg)
    assert any("audit_devices" in e for e in errors)


def test_audit_device_file_sans_file_path_rejete():
    cfg = _valid_config(audit_devices=[{"type": "file", "options": {}}])
    errors = validate_config(cfg)
    assert any("file_path" in e for e in errors)


def test_audit_device_socket_sans_address_rejete():
    cfg = _valid_config(audit_devices=[{"type": "socket", "options": {}}])
    errors = validate_config(cfg)
    assert any("address" in e for e in errors)


def test_audit_device_syslog_sans_options_ok():
    cfg = _valid_config(audit_devices=[{"type": "syslog"}])
    assert validate_config(cfg) == []


def test_config_non_dict_rejete():
    errors = validate_config("pas un dict")
    assert errors == ["La configuration doit etre un objet JSON."]


def test_policy_capabilities_vide_rejetee():
    cfg = _valid_config(policies=[{
        "name": "p", "rules": [{"path": "secret/*", "capabilities": []}],
    }])
    errors = validate_config(cfg)
    assert any("capabilities est requis" in e for e in errors)


def test_secrets_engine_path_manquant_rejete():
    cfg = _valid_config(secrets_engines=[{"type": "kv-v2"}])
    errors = validate_config(cfg)
    assert any("secrets_engines" in e and "path est requis" in e for e in errors)


def test_config_valide_sans_erreur():
    assert validate_config(_valid_config()) == []


# --------------------------------------------------------------------------
# config.hcl (serveur)
# --------------------------------------------------------------------------

def test_config_hcl_contient_storage_et_listener():
    content = generate_server_config(_valid_config())
    assert 'storage "file"' in content
    assert 'path = "/opt/vault/data"' in content
    assert 'listener "tcp"' in content
    assert 'address = "127.0.0.1:8200"' in content
    assert "tls_disable = true" in content
    assert "ui = true" in content


def test_config_hcl_tls_active_par_defaut_avec_certs():
    cfg = _valid_config()
    cfg["server"]["listener_tls_disable"] = False
    content = generate_server_config(cfg)
    assert "tls_cert_file" in content
    assert "tls_key_file" in content
    assert "tls_disable" not in content


def test_config_hcl_seal_non_shamir_ajoute_bloc_seal():
    cfg = _valid_config(server={
        "storage": "file", "storage_args": {"path": "/data"},
        "seal": "awskms", "seal_args": {"region": "eu-west-1", "kms_key_id": "alias/x"},
    })
    content = generate_server_config(cfg)
    assert 'seal "awskms"' in content
    assert 'region = "eu-west-1"' in content


def test_config_hcl_seal_shamir_aucun_bloc_seal():
    content = generate_server_config(_valid_config())
    assert "seal " not in content


def test_config_hcl_raft_ajoute_cluster_addr():
    cfg = _valid_config(server={
        "storage": "raft",
        "storage_args": {"path": "/data", "node_id": "node-1"},
        "seal": "shamir",
        "cluster_addr": "https://node-1:8201",
        "api_addr": "https://node-1:8200",
    })
    content = generate_server_config(cfg)
    assert 'cluster_addr = "https://node-1:8201"' in content
    assert 'api_addr = "https://node-1:8200"' in content


def test_config_hcl_log_level_et_disable_mlock():
    cfg = _valid_config()
    cfg["server"]["log_level"] = "warn"
    cfg["server"]["disable_mlock"] = True
    content = generate_server_config(cfg)
    assert 'log_level = "warn"' in content
    assert "disable_mlock = true" in content


def test_config_hcl_seal_args_valeur_numerique():
    cfg = _valid_config(server={
        "storage": "file", "storage_args": {"path": "/data"},
        "seal": "transit", "seal_args": {"address": "https://x", "key_name": "k", "mount_path": "transit", "port": 8200},
    })
    content = generate_server_config(cfg)
    assert "port = 8200" in content


def test_config_invalide_leve_erreur():
    with pytest.raises(ValueError):
        generate_server_config({})


# --------------------------------------------------------------------------
# Policies ACL
# --------------------------------------------------------------------------

def test_policy_file_rend_path_et_capabilities():
    policy = {
        "name": "app-readonly",
        "rules": [{"path": "secret/data/app/*", "capabilities": ["read", "list"]}],
    }
    content = generate_policy_file(policy)
    assert 'path "secret/data/app/*"' in content
    assert 'capabilities = ["read", "list"]' in content


def test_policy_file_plusieurs_regles():
    policy = {
        "name": "multi",
        "rules": [
            {"path": "secret/data/a/*", "capabilities": ["read"]},
            {"path": "secret/data/b/*", "capabilities": ["read", "list"]},
        ],
    }
    content = generate_policy_file(policy)
    assert content.count("path \"") == 2


def test_generate_policies_un_fichier_par_policy():
    cfg = _valid_config(policies=[
        {"name": "a", "rules": [{"path": "secret/a/*", "capabilities": ["read"]}]},
        {"name": "b", "rules": [{"path": "secret/b/*", "capabilities": ["read"]}]},
    ])
    fichiers = generate_policies(cfg)
    assert set(fichiers.keys()) == {"policies/a.hcl", "policies/b.hcl"}


def test_generate_policies_vide_sans_policies():
    assert generate_policies(_valid_config()) == {}


# --------------------------------------------------------------------------
# bootstrap.sh
# --------------------------------------------------------------------------

def test_bootstrap_absent_si_rien_a_bootstrapper():
    fichiers = generate_files(_valid_config())
    assert BOOTSTRAP_FILENAME not in fichiers


def test_bootstrap_present_si_policies():
    cfg = _valid_config(policies=[{"name": "p", "rules": [{"path": "secret/*", "capabilities": ["read"]}]}])
    fichiers = generate_files(cfg)
    assert BOOTSTRAP_FILENAME in fichiers
    assert "vault policy write p policies/p.hcl" in fichiers[BOOTSTRAP_FILENAME]


def test_bootstrap_active_auth_methods():
    cfg = _valid_config(auth_methods=[{"type": "approle", "path": "approle", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault auth enable -path=approle approle" in script


def test_bootstrap_active_auth_method_oidc():
    cfg = _valid_config(auth_methods=[{
        "type": "oidc", "path": "oidc",
        "config": {"oidc_discovery_url": "https://idp.example.com"},
    }])
    script = generate_bootstrap_script(cfg)
    assert "vault auth enable -path=oidc oidc" in script
    assert 'vault write auth/oidc/config oidc_discovery_url="https://idp.example.com"' in script


def test_bootstrap_active_auth_method_jwt():
    cfg = _valid_config(auth_methods=[{"type": "jwt", "path": "jwt", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault auth enable -path=jwt jwt" in script


def test_bootstrap_active_auth_method_cert():
    cfg = _valid_config(auth_methods=[{"type": "cert", "path": "cert", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault auth enable -path=cert cert" in script


def test_bootstrap_active_secrets_engines_kv_v2():
    cfg = _valid_config(secrets_engines=[{"type": "kv-v2", "path": "secret", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault secrets enable -version=2 -path=secret kv" in script


def test_bootstrap_active_secrets_engines_pki():
    cfg = _valid_config(secrets_engines=[{"type": "pki", "path": "pki", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault secrets enable -path=pki pki" in script


def test_bootstrap_active_secrets_engine_gcp():
    cfg = _valid_config(secrets_engines=[{"type": "gcp", "path": "gcp", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault secrets enable -path=gcp gcp" in script


def test_bootstrap_active_secrets_engine_azure():
    cfg = _valid_config(secrets_engines=[{"type": "azure", "path": "azure", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault secrets enable -path=azure azure" in script


def test_bootstrap_active_secrets_engine_totp():
    cfg = _valid_config(secrets_engines=[{"type": "totp", "path": "totp", "config": {}}])
    script = generate_bootstrap_script(cfg)
    assert "vault secrets enable -path=totp totp" in script


def test_bootstrap_ecrit_config_moteur():
    cfg = _valid_config(secrets_engines=[
        {"type": "pki", "path": "pki", "config": {"max_lease_ttl": "87600h"}},
    ])
    script = generate_bootstrap_script(cfg)
    assert 'vault write pki/config max_lease_ttl="87600h"' in script


def test_bootstrap_config_moteur_valeurs_bool_et_liste():
    cfg = _valid_config(secrets_engines=[
        {"type": "database", "path": "database", "config": {"rotate": True, "allowed_roles": ["ro", "rw"]}},
    ])
    script = generate_bootstrap_script(cfg)
    assert "rotate=true" in script
    assert 'allowed_roles="ro,rw"' in script


def test_bootstrap_shebang_et_set_e():
    script = generate_bootstrap_script(_valid_config(policies=[
        {"name": "p", "rules": [{"path": "secret/*", "capabilities": ["read"]}]},
    ]))
    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script


def test_bootstrap_present_si_audit_devices():
    cfg = _valid_config(audit_devices=[{"type": "file", "options": {"file_path": "/var/log/vault/audit.log"}}])
    fichiers = generate_files(cfg)
    assert BOOTSTRAP_FILENAME in fichiers


def test_bootstrap_active_audit_device_file():
    cfg = _valid_config(audit_devices=[{"type": "file", "options": {"file_path": "/var/log/vault/audit.log"}}])
    script = generate_bootstrap_script(cfg)
    assert "vault audit enable -path=file file file_path=\"/var/log/vault/audit.log\"" in script


def test_bootstrap_active_audit_device_syslog_avec_defauts():
    cfg = _valid_config(audit_devices=[{"type": "syslog"}])
    script = generate_bootstrap_script(cfg)
    assert "vault audit enable -path=syslog syslog facility=\"AUTH\"" in script


def test_bootstrap_active_audit_device_socket():
    cfg = _valid_config(audit_devices=[{"type": "socket", "options": {"address": "127.0.0.1:9090"}}])
    script = generate_bootstrap_script(cfg)
    assert "vault audit enable -path=socket socket" in script
    assert 'address="127.0.0.1:9090"' in script


def test_bootstrap_audit_device_path_personnalise():
    cfg = _valid_config(audit_devices=[
        {"type": "file", "path": "audit-primaire", "options": {"file_path": "/var/log/vault/a.log"}},
    ])
    script = generate_bootstrap_script(cfg)
    assert "vault audit enable -path=audit-primaire file" in script


def test_bootstrap_plusieurs_audit_devices_meme_type_paths_distincts():
    cfg = _valid_config(audit_devices=[
        {"type": "file", "options": {"file_path": "/var/log/vault/a.log"}},
        {"type": "file", "options": {"file_path": "/var/log/vault/b.log"}},
    ])
    script = generate_bootstrap_script(cfg)
    assert "vault audit enable -path=file-1 file" in script
    assert "vault audit enable -path=file-2 file" in script


# --------------------------------------------------------------------------
# generate_files / write_files
# --------------------------------------------------------------------------

def test_generate_files_inclut_toujours_config_hcl():
    fichiers = generate_files(_valid_config())
    assert CONFIG_FILENAME in fichiers


def test_generate_files_config_invalide_leve():
    with pytest.raises(ValueError):
        generate_files({})


def test_write_files_ecrit_sur_disque(tmp_path):
    cfg = _valid_config(
        policies=[{"name": "p", "rules": [{"path": "secret/*", "capabilities": ["read"]}]}],
        secrets_engines=[{"type": "kv-v2", "path": "secret", "config": {}}],
    )
    chemins = write_files(cfg, str(tmp_path))

    assert os.path.exists(os.path.join(tmp_path, CONFIG_FILENAME))
    assert os.path.exists(os.path.join(tmp_path, "policies", "p.hcl"))
    assert os.path.exists(os.path.join(tmp_path, BOOTSTRAP_FILENAME))
    assert len(chemins) == 3


def test_write_files_bootstrap_est_executable(tmp_path):
    cfg = _valid_config(policies=[{"name": "p", "rules": [{"path": "secret/*", "capabilities": ["read"]}]}])
    write_files(cfg, str(tmp_path))
    path = os.path.join(tmp_path, BOOTSTRAP_FILENAME)
    assert os.access(path, os.X_OK)


# --------------------------------------------------------------------------
# Catalogues / listing
# --------------------------------------------------------------------------

def test_list_storage_backends():
    backends = list_storage_backends()
    assert set(backends) == set(STORAGE_BACKENDS.keys())
    assert "file" in backends and "raft" in backends and "consul" in backends


def test_list_seal_types():
    assert set(list_seal_types()) == set(SEAL_TYPES.keys())


def test_list_auth_methods_non_vide():
    methods = list_auth_methods()
    assert "userpass" in methods
    assert "approle" in methods


def test_list_auth_methods_inclut_les_nouvelles_methodes():
    methods = list_auth_methods()
    for m in ("oidc", "jwt", "aws", "gcp", "azure", "cert"):
        assert m in methods


def test_list_secrets_engines_non_vide():
    engines = list_secrets_engines()
    assert "kv-v2" in engines
    assert "pki" in engines


def test_list_secrets_engines_inclut_les_nouveaux_moteurs():
    engines = list_secrets_engines()
    for e in ("gcp", "azure", "consul", "nomad", "totp"):
        assert e in engines


def test_list_audit_devices():
    devices = list_audit_devices()
    assert set(devices) == set(AUDIT_DEVICE_CATALOG.keys())
    assert "file" in devices and "syslog" in devices and "socket" in devices


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

def test_list_presets_correspond_au_dict():
    assert set(list_presets()) == set(PRESETS.keys())


def test_get_preset_inconnu_leve():
    with pytest.raises(ValueError):
        get_preset("does-not-exist")


def test_get_preset_retourne_copie_independante():
    p1 = get_preset("dev-single-node")
    p1["server"]["storage"] = "raft"
    p2 = get_preset("dev-single-node")
    assert p2["server"]["storage"] == "file"


@pytest.mark.parametrize("nom", list(PRESETS.keys()))
def test_tous_les_presets_sont_valides(nom):
    cfg = get_preset(nom)
    errors = validate_config(cfg)
    assert errors == [], f"Preset '{nom}' invalide : {errors}"


@pytest.mark.parametrize("nom", list(PRESETS.keys()))
def test_tous_les_presets_generent_des_fichiers(nom):
    cfg = get_preset(nom)
    fichiers = generate_files(cfg)
    assert CONFIG_FILENAME in fichiers
    for contenu in fichiers.values():
        assert contenu.strip() != ""
