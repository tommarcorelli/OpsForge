"""
modules/vault/core.py
----------------------
Coeur du module HashiCorp Vault d'OpsForge — dernier module candidat de la
roadmap (distinct de l'Ansible Vault existant, qui ne fait que chiffrer des
variables : ici on genere la configuration du serveur Vault lui-meme).

Genere trois types d'artefacts, sur le meme principe que modules/packer et
modules/terraform (rendu HCL "a la main", aligne façon `terraform fmt`) :

  - `config.hcl`            : configuration serveur (listener TCP, backend
                               de storage, seal, UI, adresses cluster/API).
  - `policies/<nom>.hcl`    : fichiers de policy ACL (blocs `path { capabilities = [...] }`).
  - `bootstrap.sh`          : script shell `vault auth enable` / `vault
                               secrets enable` / `vault policy write`, car
                               les methodes d'auth et moteurs de secrets sont
                               des operations d'API/CLI a l'execution, pas un
                               format de fichier natif (contrairement au
                               listener/storage de config.hcl).

Fonctions cles :
  - generate_server_config(config)  -> contenu config.hcl
  - generate_policy_file(policy)    -> contenu HCL d'une policy
  - generate_bootstrap_script(cfg)  -> contenu bootstrap.sh
  - generate_files(config)          -> {nom_fichier: contenu} (tous les artefacts)
  - validate_config(config)         -> liste d'erreurs (vide si valide)
  - PRESETS / get_preset            -> configs pretes a l'emploi
"""

import copy
import os
import re

CONFIG_FILENAME = "config.hcl"
BOOTSTRAP_FILENAME = "bootstrap.sh"

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_/-]*$")

CAPABILITIES = ("create", "read", "update", "delete", "list", "sudo", "deny")

# --------------------------------------------------------------------------
# Catalogues
# --------------------------------------------------------------------------
STORAGE_BACKENDS = {
    "file": {
        "label": "Fichier local (dev / single-node)",
        "required": ["path"],
        "defaults": {"path": "/opt/vault/data"},
    },
    "raft": {
        "label": "Integrated Storage (Raft — HA multi-noeuds)",
        "required": ["path", "node_id"],
        "defaults": {"path": "/opt/vault/data"},
    },
    "consul": {
        "label": "Consul (backend externe)",
        "required": ["address", "path"],
        "defaults": {"path": "vault/"},
    },
}

SEAL_TYPES = {
    "shamir": {"label": "Shamir (defaut, cles de descellement locales)", "required": []},
    "awskms": {
        "label": "AWS KMS (auto-unseal)",
        "required": ["region", "kms_key_id"],
        "defaults": {},
    },
    "transit": {
        "label": "Transit (auto-unseal via un autre cluster Vault)",
        "required": ["address", "key_name", "mount_path"],
        "defaults": {},
    },
}

AUTH_METHOD_CATALOG = {
    "userpass": {"label": "Userpass (utilisateur/mot de passe)"},
    "approle": {"label": "AppRole (machine-to-machine)"},
    "kubernetes": {"label": "Kubernetes (auth via ServiceAccount)"},
    "ldap": {"label": "LDAP"},
    "github": {"label": "GitHub (org + equipes)"},
}

SECRETS_ENGINE_CATALOG = {
    "kv-v2": {"label": "KV v2 (secrets versionnes)", "opts": "-version=2"},
    "kv-v1": {"label": "KV v1 (secrets simples)", "opts": "-version=1"},
    "database": {"label": "Database (identifiants dynamiques)", "opts": ""},
    "pki": {"label": "PKI (autorite de certification interne)", "opts": ""},
    "transit": {"label": "Transit (chiffrement as-a-service)", "opts": ""},
    "aws": {"label": "AWS (identifiants IAM dynamiques)", "opts": ""},
    "ssh": {"label": "SSH (certificats/cles a la volee)", "opts": ""},
}


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _hcl_value(value):
    """Rend une valeur Python en litteral HCL (bool/nombre/chaine/liste)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_hcl_value(v) for v in value) + "]"
    return '"' + str(value).replace('"', '\\"') + '"'


def _render_block(block_type, labels, args, indent=0):
    header = block_type + "".join(f' "{lbl}"' for lbl in labels)
    lignes = [f"{k} = {_hcl_value(v)}" for k, v in args.items()]
    corps = "\n".join(lignes)
    pad = " " * indent
    return f"{pad}{header} {{\n" + _indent(corps, indent + 2) + f"\n{pad}}}"


def _indent(text, spaces):
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_config(config):
    errors = []
    if not isinstance(config, dict):
        return ["La configuration doit etre un objet JSON."]

    server = config.get("server") or {}
    storage = _clean(server.get("storage"))
    if not storage:
        errors.append("server.storage est requis.")
    elif storage not in STORAGE_BACKENDS:
        errors.append(
            f"Backend de storage inconnu : '{storage}'. "
            f"Disponibles : {', '.join(STORAGE_BACKENDS)}."
        )
    else:
        storage_args = server.get("storage_args") or {}
        for req in STORAGE_BACKENDS[storage]["required"]:
            if req not in storage_args and req not in STORAGE_BACKENDS[storage].get("defaults", {}):
                errors.append(f"server.storage_args.{req} est requis pour le backend '{storage}'.")

    seal = _clean(server.get("seal")) or "shamir"
    if seal not in SEAL_TYPES:
        errors.append(f"Type de seal inconnu : '{seal}'. Disponibles : {', '.join(SEAL_TYPES)}.")
    else:
        seal_args = server.get("seal_args") or {}
        for req in SEAL_TYPES[seal]["required"]:
            if req not in seal_args:
                errors.append(f"server.seal_args.{req} est requis pour le seal '{seal}'.")

    for i, policy in enumerate(config.get("policies") or []):
        name = _clean(policy.get("name"))
        if not name or not _NAME_RE.match(name):
            errors.append(f"policies[{i}].name invalide ou manquant (lettres/chiffres/-/_ uniquement).")
        rules = policy.get("rules") or []
        if not rules:
            errors.append(f"policies[{i}] ('{name}') doit avoir au moins une regle (path).")
        for j, rule in enumerate(rules):
            if not _clean(rule.get("path")):
                errors.append(f"policies[{i}].rules[{j}].path est requis.")
            caps = rule.get("capabilities") or []
            if not caps:
                errors.append(f"policies[{i}].rules[{j}].capabilities est requis (au moins une).")
            for cap in caps:
                if cap not in CAPABILITIES:
                    errors.append(
                        f"policies[{i}].rules[{j}] : capability inconnue '{cap}'. "
                        f"Disponibles : {', '.join(CAPABILITIES)}."
                    )

    for i, auth in enumerate(config.get("auth_methods") or []):
        atype = _clean(auth.get("type"))
        if atype not in AUTH_METHOD_CATALOG:
            errors.append(
                f"auth_methods[{i}] : type inconnu '{atype}'. "
                f"Disponibles : {', '.join(AUTH_METHOD_CATALOG)}."
            )
        if not _clean(auth.get("path")):
            errors.append(f"auth_methods[{i}].path est requis (point de montage, ex: '{atype}').")

    for i, engine in enumerate(config.get("secrets_engines") or []):
        etype = _clean(engine.get("type"))
        if etype not in SECRETS_ENGINE_CATALOG:
            errors.append(
                f"secrets_engines[{i}] : type inconnu '{etype}'. "
                f"Disponibles : {', '.join(SECRETS_ENGINE_CATALOG)}."
            )
        if not _clean(engine.get("path")):
            errors.append(f"secrets_engines[{i}].path est requis (point de montage).")

    return errors


# --------------------------------------------------------------------------
# config.hcl (serveur)
# --------------------------------------------------------------------------
def generate_server_config(config):
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    server = config.get("server") or {}
    storage = _clean(server["storage"])
    storage_args = dict(STORAGE_BACKENDS[storage].get("defaults", {}))
    storage_args.update(server.get("storage_args") or {})

    seal = _clean(server.get("seal")) or "shamir"
    ui = server.get("ui", True)
    listener_address = _clean(server.get("listener_address")) or "0.0.0.0:8200"
    tls_disable = server.get("listener_tls_disable", False)

    listener_args = {"address": listener_address}
    if tls_disable:
        listener_args["tls_disable"] = True
    else:
        listener_args["tls_cert_file"] = _clean(server.get("cert_file")) or "/opt/vault/tls/vault.crt"
        listener_args["tls_key_file"] = _clean(server.get("key_file")) or "/opt/vault/tls/vault.key"

    blocs = [
        _render_block("storage", [storage], storage_args),
        _render_block("listener", ["tcp"], listener_args),
    ]

    if seal != "shamir":
        blocs.append(_render_block("seal", [seal], server.get("seal_args") or {}))

    lignes_racine = [f"ui = {_hcl_value(ui)}"]
    if server.get("api_addr"):
        lignes_racine.append(f'api_addr = {_hcl_value(server["api_addr"])}')
    if storage == "raft" and server.get("cluster_addr"):
        lignes_racine.append(f'cluster_addr = {_hcl_value(server["cluster_addr"])}')
    if server.get("cluster_name"):
        lignes_racine.append(f'cluster_name = {_hcl_value(server["cluster_name"])}')
    if server.get("log_level"):
        lignes_racine.append(f'log_level = {_hcl_value(server["log_level"])}')
    if server.get("disable_mlock"):
        lignes_racine.append(f"disable_mlock = {_hcl_value(server['disable_mlock'])}")

    contenu = (
        "\n\n".join(blocs)
        + "\n\n"
        + "\n".join(lignes_racine)
        + "\n"
    )
    return contenu


# --------------------------------------------------------------------------
# Policies ACL
# --------------------------------------------------------------------------
def generate_policy_file(policy):
    """Genere le contenu HCL d'une seule policy ACL (un fichier `<nom>.hcl`)."""
    lignes = []
    for rule in policy.get("rules") or []:
        path = _clean(rule["path"])
        caps = rule.get("capabilities") or []
        bloc = _render_block("path", [path], {"capabilities": caps})
        # Convention Vault : "path" est le mot-cle, le path est un label —
        # _render_block produit deja `path "secret/data/app/*" { ... }`.
        lignes.append(bloc)
    return "\n\n".join(lignes) + "\n"


def generate_policies(config):
    """Retourne {nom_fichier: contenu} pour chaque policy declaree."""
    fichiers = {}
    for policy in config.get("policies") or []:
        name = _clean(policy["name"])
        fichiers[f"policies/{name}.hcl"] = generate_policy_file(policy)
    return fichiers


# --------------------------------------------------------------------------
# bootstrap.sh (auth methods + secrets engines + policies)
# --------------------------------------------------------------------------
def generate_bootstrap_script(config):
    """
    Genere un script shell idempotent qui active les methodes d'auth, les
    moteurs de secrets et charge les policies — ce sont des operations
    d'API/CLI a l'execution (pas de fichier de config natif Vault pour ca),
    contrairement au listener/storage/seal geres par config.hcl.
    """
    lignes = [
        "#!/usr/bin/env bash",
        "# Genere par OpsForge — module Vault.",
        "# Suppose que VAULT_ADDR est exporte et que le token courant a les",
        "# droits sudo/root (initialisation + descellement deja effectues).",
        "set -euo pipefail",
        "",
    ]

    policies = config.get("policies") or []
    if policies:
        lignes.append("# --- Policies ACL ---")
        for policy in policies:
            name = _clean(policy["name"])
            lignes.append(f'vault policy write {name} policies/{name}.hcl')
        lignes.append("")

    auth_methods = config.get("auth_methods") or []
    if auth_methods:
        lignes.append("# --- Methodes d'authentification ---")
        for auth in auth_methods:
            atype = _clean(auth["type"])
            path = _clean(auth["path"])
            lignes.append(f'vault auth enable -path={path} {atype} || true')
            for key, value in (auth.get("config") or {}).items():
                lignes.append(f'vault write auth/{path}/config {key}={_shell_value(value)}')
        lignes.append("")

    engines = config.get("secrets_engines") or []
    if engines:
        lignes.append("# --- Moteurs de secrets ---")
        for engine in engines:
            etype = _clean(engine["type"])
            path = _clean(engine["path"])
            opts = SECRETS_ENGINE_CATALOG[etype]["opts"]
            base_type = "kv" if etype.startswith("kv-") else etype
            opt_str = f" {opts}" if opts else ""
            lignes.append(f'vault secrets enable{opt_str} -path={path} {base_type} || true')
            for key, value in (engine.get("config") or {}).items():
                lignes.append(f'vault write {path}/config {key}={_shell_value(value)}')
        lignes.append("")

    lignes.append('echo "Bootstrap Vault termine."')
    return "\n".join(lignes) + "\n"


def _shell_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return '"' + ",".join(str(v) for v in value) + '"'
    return '"' + str(value).replace('"', '\\"') + '"'


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------
def generate_files(config):
    """Retourne {nom_fichier: contenu} : config.hcl, policies/*.hcl, bootstrap.sh."""
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    fichiers = {CONFIG_FILENAME: generate_server_config(config)}
    fichiers.update(generate_policies(config))
    if (config.get("auth_methods") or config.get("secrets_engines") or config.get("policies")):
        fichiers[BOOTSTRAP_FILENAME] = generate_bootstrap_script(config)
    return fichiers


def write_files(config, output_dir):
    fichiers = generate_files(config)
    chemins = []
    for nom, contenu in fichiers.items():
        path = os.path.join(output_dir, nom)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(contenu)
        if nom == BOOTSTRAP_FILENAME:
            os.chmod(path, 0o755)
        chemins.append(path)
    return chemins


def list_storage_backends():
    return list(STORAGE_BACKENDS.keys())


def list_seal_types():
    return list(SEAL_TYPES.keys())


def list_auth_methods():
    return list(AUTH_METHOD_CATALOG.keys())


def list_secrets_engines():
    return list(SECRETS_ENGINE_CATALOG.keys())


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "dev-single-node": {
        "server": {
            "storage": "file",
            "storage_args": {"path": "/opt/vault/data"},
            "listener_address": "127.0.0.1:8200",
            "listener_tls_disable": True,
            "seal": "shamir",
            "ui": True,
        },
        "policies": [
            {
                "name": "app-readonly",
                "rules": [
                    {"path": "secret/data/app/*", "capabilities": ["read", "list"]},
                ],
            },
        ],
        "secrets_engines": [
            {"type": "kv-v2", "path": "secret", "config": {}},
        ],
        "auth_methods": [
            {"type": "userpass", "path": "userpass", "config": {}},
        ],
    },
    "ha-raft-cluster": {
        "server": {
            "storage": "raft",
            "storage_args": {"path": "/opt/vault/data", "node_id": "vault-node-1"},
            "listener_address": "0.0.0.0:8200",
            "listener_tls_disable": False,
            "cert_file": "/opt/vault/tls/vault.crt",
            "key_file": "/opt/vault/tls/vault.key",
            "seal": "shamir",
            "ui": True,
            "api_addr": "https://vault-node-1.internal:8200",
            "cluster_addr": "https://vault-node-1.internal:8201",
            "cluster_name": "vault-prod",
        },
        "policies": [
            {
                "name": "admins",
                "rules": [
                    {"path": "*", "capabilities": ["create", "read", "update", "delete", "list", "sudo"]},
                ],
            },
        ],
    },
    "app-secrets-kv": {
        "server": {
            "storage": "file",
            "storage_args": {"path": "/opt/vault/data"},
            "listener_address": "0.0.0.0:8200",
            "listener_tls_disable": True,
            "seal": "shamir",
            "ui": True,
        },
        "policies": [
            {
                "name": "app-readwrite",
                "rules": [
                    {"path": "secret/data/app/*", "capabilities": ["create", "read", "update", "list"]},
                    {"path": "secret/metadata/app/*", "capabilities": ["list"]},
                ],
            },
        ],
        "secrets_engines": [
            {"type": "kv-v2", "path": "secret", "config": {}},
        ],
        "auth_methods": [
            {"type": "approle", "path": "approle", "config": {}},
        ],
    },
    "pki-internal-ca": {
        "server": {
            "storage": "file",
            "storage_args": {"path": "/opt/vault/data"},
            "listener_address": "0.0.0.0:8200",
            "listener_tls_disable": False,
            "cert_file": "/opt/vault/tls/vault.crt",
            "key_file": "/opt/vault/tls/vault.key",
            "seal": "shamir",
            "ui": True,
        },
        "policies": [
            {
                "name": "pki-issuer",
                "rules": [
                    {"path": "pki/issue/internal-role", "capabilities": ["create", "update"]},
                ],
            },
        ],
        "secrets_engines": [
            {"type": "pki", "path": "pki", "config": {"max_lease_ttl": "87600h"}},
        ],
    },
    "database-dynamic-creds": {
        "server": {
            "storage": "raft",
            "storage_args": {"path": "/opt/vault/data", "node_id": "vault-node-1"},
            "listener_address": "0.0.0.0:8200",
            "listener_tls_disable": True,
            "seal": "awskms",
            "seal_args": {"region": "eu-west-1", "kms_key_id": "alias/vault-unseal"},
            "ui": True,
        },
        "policies": [
            {
                "name": "db-readonly",
                "rules": [
                    {"path": "database/creds/readonly-role", "capabilities": ["read"]},
                ],
            },
        ],
        "secrets_engines": [
            {"type": "database", "path": "database", "config": {}},
        ],
        "auth_methods": [
            {"type": "kubernetes", "path": "kubernetes", "config": {}},
        ],
    },
}


def list_presets():
    return list(PRESETS.keys())


def get_preset(name):
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Presets disponibles : {', '.join(PRESETS.keys())}."
        )
    return copy.deepcopy(PRESETS[name])
