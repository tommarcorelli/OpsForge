"""
core.py
-------
Generation d'un fichier cloud-init `#cloud-config` (user-data) a partir d'une
config JSON. Ferme la chaine : ce que Vagrant/Terraform instancie, cloud-init
le configure au PREMIER demarrage (users, cles SSH, paquets, fichiers,
commandes) — avant meme qu'Ansible ne prenne le relais.

Sections gerees : identite (hostname/timezone), mise a jour des paquets,
utilisateurs (groupes, sudo, cles SSH), paquets a installer, fichiers a ecrire
(write_files), commandes de premier boot (runcmd), et durcissement SSH de base
(disable_root, ssh_pwauth).

Le YAML est produit via PyYAML (garanti valide) et prefixe de la ligne
obligatoire `#cloud-config`.

Usage basique :
    from modules.cloudinit.core import generate_cloud_config

    config = {
        "hostname": "web-01",
        "packages": ["nginx"],
        "users": [{"name": "deploy", "sudo": True, "ssh_authorized_keys": ["ssh-ed25519 AAAA..."]}],
    }
    text = generate_cloud_config(config)
"""

import copy
import os
import re

import yaml

OUTPUT_FILENAME = "user-data"

DEFAULT_SHELL = "/bin/bash"
SUDO_NOPASSWD = "ALL=(ALL) NOPASSWD:ALL"

# Permissions type "0644" / "644".
_PERM_RE = re.compile(r"^0?[0-7]{3,4}$")
# Nom d'utilisateur Linux (garde-fou simple).
_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*$")

# Directives dont au moins une doit etre presente pour que la config ait un sens.
_CONTENT_KEYS = (
    "hostname",
    "packages",
    "users",
    "write_files",
    "runcmd",
    "package_update",
    "package_upgrade",
)


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _as_list(value):
    """Accepte une liste, ou une chaine (separateurs virgule / retour ligne)."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[\n,]+", value) if part.strip()]
    return []


def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    if not any(config.get(key) for key in _CONTENT_KEYS):
        errors.append(
            "Configuration vide : ajoute au moins une directive "
            "(hostname, paquets, utilisateur, fichier ou commande)."
        )

    for i, user in enumerate(config.get("users") or []):
        name = _clean(user.get("name"))
        if not name:
            errors.append(f"Utilisateur #{i + 1} : le nom est requis.")
        elif not _USER_RE.match(name):
            errors.append(f"Utilisateur #{i + 1} : nom invalide '{name}'.")

    for i, wf in enumerate(config.get("write_files") or []):
        if not _clean(wf.get("path")):
            errors.append(f"Fichier #{i + 1} : le chemin (path) est requis.")
        if wf.get("content") in (None, ""):
            errors.append(f"Fichier #{i + 1} : le contenu est requis.")
        perms = _clean(wf.get("permissions"))
        if perms and not _PERM_RE.match(perms):
            errors.append(f"Fichier #{i + 1} : permissions invalides '{perms}' (ex : 0644).")

    return errors


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def _build_user(user):
    entry = {"name": _clean(user["name"])}

    groups = _as_list(user.get("groups"))
    if groups:
        entry["groups"] = groups

    if user.get("sudo"):
        entry["sudo"] = SUDO_NOPASSWD

    entry["shell"] = _clean(user.get("shell")) or DEFAULT_SHELL

    keys = _as_list(user.get("ssh_authorized_keys"))
    if keys:
        entry["ssh_authorized_keys"] = keys
        # Une cle SSH => on verrouille le mot de passe (connexion par cle only).
        entry["lock_passwd"] = user.get("lock_passwd", True)
    elif "lock_passwd" in user:
        entry["lock_passwd"] = bool(user["lock_passwd"])

    return entry


def _build_write_file(wf):
    entry = {"path": _clean(wf["path"]), "content": wf["content"]}
    perms = _clean(wf.get("permissions"))
    if perms:
        # cloud-init attend une chaine (ex : "0644").
        entry["permissions"] = perms if perms.startswith("0") else "0" + perms
    if _clean(wf.get("owner")):
        entry["owner"] = wf["owner"]
    return entry


def _assemble(config):
    """Construit le dict cloud-config (sections vides omises), dans un ordre lisible."""
    data = {}

    if _clean(config.get("hostname")):
        data["hostname"] = _clean(config["hostname"])
    if _clean(config.get("timezone")):
        data["timezone"] = _clean(config["timezone"])

    if config.get("package_update"):
        data["package_update"] = True
    if config.get("package_upgrade"):
        data["package_upgrade"] = True

    if config.get("disable_root"):
        data["disable_root"] = True
    if "ssh_pwauth" in config:
        data["ssh_pwauth"] = bool(config["ssh_pwauth"])

    users = [_build_user(u) for u in (config.get("users") or []) if _clean(u.get("name"))]
    if users:
        data["users"] = users

    packages = _as_list(config.get("packages"))
    if packages:
        data["packages"] = packages

    write_files = [
        _build_write_file(wf)
        for wf in (config.get("write_files") or [])
        if _clean(wf.get("path"))
    ]
    if write_files:
        data["write_files"] = write_files

    runcmd = _as_list(config.get("runcmd"))
    if runcmd:
        data["runcmd"] = runcmd

    if _clean(config.get("final_message")):
        data["final_message"] = _clean(config["final_message"])

    return data


def generate_cloud_config(config):
    """
    Genere le contenu complet d'un fichier cloud-init `#cloud-config`.

    Args:
        config (dict): voir validate_config() pour les cles attendues.

    Returns:
        str: contenu pret a etre servi comme user-data.

    Raises:
        ValueError: si la config est invalide (voir validate_config()).
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    data = _assemble(config)
    body = yaml.dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True, width=4096)
    # La premiere ligne `#cloud-config` est OBLIGATOIRE (cloud-init la detecte).
    return "#cloud-config\n" + body


def generate_files(config):
    """Retourne {nom_de_fichier: contenu} (une seule entree : user-data)."""
    return {OUTPUT_FILENAME: generate_cloud_config(config)}


def generate_combined(config):
    return generate_cloud_config(config)


def write_files(config, output_dir):
    """Genere le fichier et l'ecrit dans output_dir. Retourne les chemins."""
    content = generate_cloud_config(config)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, OUTPUT_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return [path]


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "docker-host": {
        "hostname": "docker-01",
        "package_update": True,
        "package_upgrade": True,
        "packages": ["docker.io", "docker-compose-plugin"],
        "users": [{
            "name": "deploy",
            "groups": "sudo, docker",
            "sudo": True,
            "ssh_authorized_keys": ["ssh-ed25519 AAAA...remplace-moi"],
        }],
        "runcmd": [
            "systemctl enable --now docker",
            "usermod -aG docker deploy",
        ],
        "final_message": "Hote Docker pret apres $UPTIME secondes.",
    },
    "web-server": {
        "hostname": "web-01",
        "package_update": True,
        "packages": ["nginx"],
        "users": [{
            "name": "deploy",
            "groups": "sudo",
            "sudo": True,
            "ssh_authorized_keys": ["ssh-ed25519 AAAA...remplace-moi"],
        }],
        "runcmd": ["systemctl enable --now nginx"],
    },
    "secure-baseline": {
        "hostname": "srv-01",
        "package_update": True,
        "package_upgrade": True,
        "disable_root": True,
        "ssh_pwauth": False,
        "packages": ["ufw", "fail2ban", "unattended-upgrades"],
        "users": [{
            "name": "admin",
            "groups": "sudo",
            "sudo": True,
            "ssh_authorized_keys": ["ssh-ed25519 AAAA...remplace-moi"],
        }],
        "runcmd": [
            "ufw default deny incoming",
            "ufw allow OpenSSH",
            "ufw --force enable",
            "systemctl enable --now fail2ban",
        ],
    },
    "minimal": {
        "hostname": "node-01",
        "users": [{
            "name": "user",
            "groups": "sudo",
            "sudo": True,
            "ssh_authorized_keys": ["ssh-ed25519 AAAA...remplace-moi"],
        }],
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
