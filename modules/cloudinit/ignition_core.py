"""
modules/cloudinit/ignition_core.py
-----------------------------------
Genere une config **Ignition** (JSON, spec 3.4.0) — l'equivalent premier-boot
de `#cloud-config` pour **Fedora CoreOS / Flatcar / RHCOS**. Ces distributions
n'utilisent pas cloud-init : leur agent de premier demarrage consomme
directement un document Ignition (souvent produit via Butane, ici genere
directement en JSON pour eviter une dependance supplementaire).

Reutilise le MEME schema de config que le module cloud-init
(`modules.cloudinit.core.validate_config`) : hostname, users (nom, groupes,
cles SSH), write_files, runcmd, packages. Ainsi un formulaire deja rempli
pour `#cloud-config` produit aussi une config Ignition valide, sans champs
supplementaires a saisir.

Differences de fond avec cloud-init (documentees, pas contournees) :
- Pas de gestionnaire de paquets mutable : CoreOS est un OS immuable
  (rpm-ostree/Flatcar). Les `packages` demandes sont donc installes via
  `rpm-ostree install` dans une unite systemd de premier boot (necessite un
  redemarrage, gere automatiquement par l'unite generee).
- Pas de `runcmd` natif : les commandes sont enchainees dans cette meme
  unite systemd `oneshot` (executees dans l'ordre, apres l'installation des
  paquets eventuels).
- Les mots de passe ne sont pas geres (connexion par cle SSH uniquement,
  pratique standard CoreOS) : seuls `sshAuthorizedKeys` et `groups` sont
  repris pour chaque utilisateur.

Usage basique :
    from modules.cloudinit.ignition_core import generate_ignition

    config = {
        "hostname": "web-01",
        "packages": ["nginx"],
        "users": [{"name": "core", "groups": "wheel", "ssh_authorized_keys": ["ssh-ed25519 AAAA..."]}],
    }
    text = generate_ignition(config)
"""

import base64
import json

from modules.cloudinit.core import validate_config, _as_list, _clean

IGNITION_VERSION = "3.4.0"
OUTPUT_FILENAME = "config.ign"

FIRSTBOOT_UNIT_NAME = "opsforge-firstboot.service"


def _mode_from_permissions(perms, default=420):
    """Convertit une permission octale (ex: '0644' ou '644') en entier decimal
    (Ignition attend un `mode` en decimal, ex: 0644 octal = 420 decimal)."""
    perms = _clean(perms)
    if not perms:
        return default
    try:
        return int(perms, 8)
    except ValueError:
        return default


def _data_url(content):
    """Encode le contenu en data URL base64 (format attendu par Ignition
    pour `storage.files[].contents.source`)."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f"data:text/plain;charset=utf-8;base64,{encoded}"


def _build_user(user):
    entry = {"name": _clean(user["name"])}

    keys = _as_list(user.get("ssh_authorized_keys"))
    if keys:
        entry["sshAuthorizedKeys"] = keys

    groups = _as_list(user.get("groups"))
    if groups:
        entry["groups"] = groups

    return entry


def _build_file(wf):
    return {
        "path": _clean(wf["path"]),
        "overwrite": True,
        "contents": {"source": _data_url(str(wf["content"]))},
        "mode": _mode_from_permissions(wf.get("permissions")),
    }


def _hostname_file(hostname):
    return {
        "path": "/etc/hostname",
        "overwrite": True,
        "contents": {"source": _data_url(hostname + "\n")},
        "mode": 420,
    }


def _build_firstboot_unit(config):
    """
    Assemble l'unite systemd `oneshot` de premier boot : installation des
    paquets (rpm-ostree) puis commandes `runcmd`, dans l'ordre. Retourne None
    si ni paquets ni commandes ne sont demandes (aucune unite necessaire).
    """
    exec_lines = []

    packages = _as_list(config.get("packages"))
    if packages:
        pkg_list = " ".join(packages)
        exec_lines.append(
            f"/usr/bin/rpm-ostree install -y --idempotent --allow-inactive {pkg_list}"
        )

    runcmd = _as_list(config.get("runcmd"))
    exec_lines.extend(runcmd)

    if not exec_lines:
        return None

    exec_start = "\n".join(f'ExecStart=/bin/bash -c "{cmd}"' for cmd in exec_lines)

    needs_reboot = bool(packages)
    reboot_line = "\nExecStartPost=/bin/systemctl reboot" if needs_reboot else ""

    unit_contents = (
        "[Unit]\n"
        "Description=OpsForge - commandes de premier boot (genere)\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        f"{exec_start}"
        f"{reboot_line}\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    return {
        "name": FIRSTBOOT_UNIT_NAME,
        "enabled": True,
        "contents": unit_contents,
    }


def generate_ignition(config):
    """
    Genere le contenu complet d'une config Ignition (JSON) a partir du meme
    schema de config que `generate_cloud_config`.

    Args:
        config (dict): voir modules.cloudinit.core.validate_config().

    Returns:
        str: document Ignition JSON (indente, pret a servir comme `config.ign`).

    Raises:
        ValueError: si la config est invalide (memes regles que cloud-init).
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    doc = {"ignition": {"version": IGNITION_VERSION}}

    users = [_build_user(u) for u in (config.get("users") or []) if _clean(u.get("name"))]
    if users:
        doc["passwd"] = {"users": users}

    files = []
    hostname = _clean(config.get("hostname"))
    if hostname:
        files.append(_hostname_file(hostname))
    for wf in (config.get("write_files") or []):
        if _clean(wf.get("path")):
            files.append(_build_file(wf))
    if files:
        doc["storage"] = {"files": files}

    unit = _build_firstboot_unit(config)
    if unit:
        doc["systemd"] = {"units": [unit]}

    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def generate_files(config):
    """Retourne {nom_de_fichier: contenu} (une seule entree : config.ign)."""
    return {OUTPUT_FILENAME: generate_ignition(config)}


def write_files(config, output_dir):
    """Genere le fichier Ignition et l'ecrit dans output_dir. Retourne les chemins."""
    import os

    content = generate_ignition(config)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, OUTPUT_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return [path]
