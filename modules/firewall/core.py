"""
core.py
-------
Generation de regles pare-feu (ufw ou nftables) + config fail2ban a partir
d'une config JSON. Prolonge naturellement les modules cloudinit / ansible /
systemd : ce qu'on deploie et qu'on supervise, le firewall le protege.

Deux backends de regles :

  - "ufw"       : script bash idempotent (`ufw allow ...`), le plus simple,
                  pense pour Debian/Ubuntu.
  - "nftables"  : fichier `nftables.conf` natif (table/chain/rules), pour
                  systemes plus bas niveau (RHEL/Alpine/durcissement avance).

Plus, en option, une config fail2ban standalone (jail.local) — jusqu'ici
fail2ban n'existait que comme case a cocher a l'interieur du module Ansible ;
ce module devient la source de vraie pour cette logique (Ansible peut
l'appeler au lieu de dupliquer les regles de jails).

Usage basique :
    from modules.firewall.core import generate_firewall

    config = {
        "preset": "web-public",
        "backend": "ufw",
        "fail2ban": True,
    }
    files = generate_firewall(config)   # {"setup-firewall.sh": "...", "jail.local": "..."}
"""

import copy
import ipaddress
import os
import re

SUPPORTED_BACKENDS = ["ufw", "nftables"]

# --------------------------------------------------------------------------
# Presets : chaque preset est une liste de regles de base, pensee pour un
# cas d'usage courant. L'utilisateur peut aussi partir de "custom" et
# fournir sa propre liste de regles.
# --------------------------------------------------------------------------
PRESETS = {
    "web-public": {
        "label": "Serveur web public (SSH + HTTP/HTTPS uniquement)",
        "rules": [
            {"port": 22, "proto": "tcp", "source": "any", "action": "allow", "comment": "SSH"},
            {"port": 80, "proto": "tcp", "source": "any", "action": "allow", "comment": "HTTP"},
            {"port": 443, "proto": "tcp", "source": "any", "action": "allow", "comment": "HTTPS"},
        ],
        "default_deny_incoming": True,
    },
    "db-private": {
        "label": "Serveur de base de donnees (acces restreint par IP)",
        "rules": [
            {"port": 22, "proto": "tcp", "source": "any", "action": "allow", "comment": "SSH"},
            {"port": 5432, "proto": "tcp", "source": "10.0.0.0/8", "action": "allow", "comment": "PostgreSQL (reseau prive)"},
        ],
        "default_deny_incoming": True,
    },
    "ssh-bastion": {
        "label": "Bastion SSH (uniquement SSH, rate-limite)",
        "rules": [
            {"port": 22, "proto": "tcp", "source": "any", "action": "limit", "comment": "SSH (rate-limited)"},
        ],
        "default_deny_incoming": True,
    },
    "custom": {
        "label": "Personnalise (regles fournies manuellement)",
        "rules": [],
        "default_deny_incoming": True,
    },
}

# Preset de jails fail2ban par defaut (sshd seul, toujours actif).
DEFAULT_FAIL2BAN_JAILS = {
    "sshd": {"enabled": True, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
}

# Catalogue complet des jails disponibles (au-dela de sshd) : chacune
# correspond a un filtre fail2ban standard, deja fourni par le paquet
# fail2ban sur la plupart des distributions (pas besoin de filtre custom).
FAIL2BAN_CATALOG = {
    "sshd": {"enabled": True, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
    "nginx-http-auth": {"enabled": False, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
    "nginx-limit-req": {"enabled": False, "maxretry": 10, "bantime": "30m", "findtime": "10m"},
    "nginx-botsearch": {"enabled": False, "maxretry": 3, "bantime": "1h", "findtime": "10m"},
    "postfix": {"enabled": False, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
    "vsftpd": {"enabled": False, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
}

# Jails suggerees (desactivees par defaut, l'utilisateur les active si le
# service correspondant tourne reellement sur la machine) par preset.
PRESET_SUGGESTED_JAILS = {
    "web-public": ["nginx-http-auth", "nginx-limit-req", "nginx-botsearch"],
    "db-private": [],
    "ssh-bastion": [],
    "custom": [],
}

_PORT_RE = re.compile(r"^\d{1,5}$")


def _clean(value):
    return (value or "").strip() if isinstance(value, str) else value


def _is_valid_address(value):
    """True si value est une IP ou un CIDR IPv4/IPv6 valide."""
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def _address_family(value):
    """Retourne 'ip6' ou 'ip' selon que value est une adresse/CIDR IPv6 ou IPv4."""
    try:
        return "ip6" if ipaddress.ip_network(value, strict=False).version == 6 else "ip"
    except ValueError:
        # Ne devrait pas arriver si validate_config est passe avant, mais on
        # reste permissif plutot que de planter la generation.
        return "ip"


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def list_fail2ban_jails():
    """Liste les jails fail2ban disponibles dans le catalogue (ordre stable)."""
    return list(FAIL2BAN_CATALOG.keys())


def get_preset(name):
    """
    Retourne une config de depart prete a generer pour le preset donne
    (copie profonde : modifiable sans affecter PRESETS).

    Inclut les jails fail2ban suggerees pour ce preset (sshd toujours actif,
    le reste desactive par defaut : a l'utilisateur de les activer si le
    service correspondant tourne reellement sur la machine).
    """
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Disponibles : {', '.join(PRESETS)}."
        )
    preset_def = PRESETS[name]

    jails = {"sshd": copy.deepcopy(FAIL2BAN_CATALOG["sshd"])}
    for jail_name in PRESET_SUGGESTED_JAILS.get(name, []):
        jails[jail_name] = copy.deepcopy(FAIL2BAN_CATALOG[jail_name])

    return {
        "preset": name,
        "backend": "ufw",
        "fail2ban": name != "custom",
        "fail2ban_jails": jails,
        "rules": copy.deepcopy(preset_def["rules"]),
        "default_deny_incoming": preset_def["default_deny_incoming"],
    }


def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    preset = config.get("preset", "custom")
    if preset not in PRESETS:
        errors.append(
            f"Preset non supporte : '{preset}'. Disponibles : {', '.join(PRESETS)}."
        )
        preset = "custom"

    backend = config.get("backend", "ufw")
    if backend not in SUPPORTED_BACKENDS:
        errors.append(
            f"Backend non supporte : '{backend}'. Disponibles : {', '.join(SUPPORTED_BACKENDS)}."
        )

    rules = config.get("rules") if preset == "custom" else PRESETS[preset]["rules"]
    if preset == "custom" and not rules:
        errors.append("Preset 'custom' choisi mais aucune regle fournie (rules).")

    for i, rule in enumerate(rules or []):
        port = rule.get("port")
        if not port or not _PORT_RE.match(str(port)) or not (0 < int(port) <= 65535):
            errors.append(f"Regle #{i + 1} : port invalide ({port!r}).")
        if rule.get("proto") not in ("tcp", "udp"):
            errors.append(f"Regle #{i + 1} : proto invalide ({rule.get('proto')!r}), attendu tcp/udp.")
        if rule.get("action") not in ("allow", "deny", "limit"):
            errors.append(f"Regle #{i + 1} : action invalide ({rule.get('action')!r}).")
        source = rule.get("source", "any")
        if source and source != "any" and not _is_valid_address(source):
            errors.append(f"Regle #{i + 1} : source invalide ({source!r}), attendu une IP/CIDR IPv4 ou IPv6.")

    if config.get("fail2ban"):
        jails = config.get("fail2ban_jails")
        if jails:
            for jail_name in jails:
                if jail_name not in FAIL2BAN_CATALOG:
                    errors.append(
                        f"Jail fail2ban inconnue : '{jail_name}'. "
                        f"Disponibles : {', '.join(FAIL2BAN_CATALOG)}."
                    )

    return errors


def _resolve_rules(config):
    preset = config.get("preset", "custom")
    if preset == "custom":
        return config.get("rules", []), config.get(
            "default_deny_incoming", True
        )
    preset_def = PRESETS[preset]
    return preset_def["rules"], preset_def["default_deny_incoming"]


# --------------------------------------------------------------------------
# Backend ufw : script bash idempotent (safe a relancer plusieurs fois).
# --------------------------------------------------------------------------
def generate_ufw_script(config):
    rules, default_deny = _resolve_rules(config)

    lines = [
        "#!/usr/bin/env bash",
        "# Genere par OpsForge (module firewall) — a executer avec sudo.",
        "# Idempotent : peut etre relance sans dupliquer les regles.",
        "set -euo pipefail",
        "",
        "# S'assure qu'IPv6 est active (necessaire pour que les regles avec",
        "# une source IPv6 soient bien appliquees) — idempotent.",
        "if [ -f /etc/default/ufw ]; then",
        "    sed -i 's/^IPV6=.*/IPV6=yes/' /etc/default/ufw",
        "fi",
        "",
        "ufw --force reset",
        "ufw default deny incoming" if default_deny else "ufw default allow incoming",
        "ufw default allow outgoing",
        "",
    ]

    for rule in rules:
        port, proto = rule["port"], rule["proto"]
        comment = rule.get("comment", "")
        source = rule.get("source", "any")
        action = rule["action"]

        if action == "limit":
            # ufw limit : protection anti brute-force native (6 tentatives / 30s)
            cmd = f"ufw limit {port}/{proto}"
        else:
            ufw_action = "allow" if action == "allow" else "deny"
            if source and source != "any":
                cmd = f"ufw {ufw_action} from {source} to any port {port} proto {proto}"
            else:
                cmd = f"ufw {ufw_action} {port}/{proto}"

        lines.append(f"{cmd}{'  # ' + comment if comment else ''}")

    lines += ["", "ufw --force enable", "ufw status verbose", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Backend nftables : table/chain natives.
# --------------------------------------------------------------------------
def generate_nftables_conf(config):
    rules, default_deny = _resolve_rules(config)
    policy = "drop" if default_deny else "accept"

    lines = [
        "#!/usr/sbin/nft -f",
        "# Genere par OpsForge (module firewall).",
        "# Table 'inet' : filtre a la fois IPv4 et IPv6 dans les memes regles.",
        "flush ruleset",
        "",
        "table inet filter {",
        "    chain input {",
        f"        type filter hook input priority 0; policy {policy};",
        "",
        "        ct state established,related accept",
        "        ct state invalid drop",
        "        iif lo accept",
        "",
        "        # Indispensable en IPv6 (decouverte de voisins, MTU, etc.) :",
        "        # sans ca, policy drop casse silencieusement IPv6 entier.",
        "        icmpv6 type { destination-unreachable, packet-too-big, time-exceeded,",
        "            parameter-problem, nd-router-solicit, nd-router-advert,",
        "            nd-neighbor-solicit, nd-neighbor-advert } accept",
    ]

    if rules:
        lines.append("")

    for rule in rules:
        port, proto = rule["port"], rule["proto"]
        comment = rule.get("comment", "")
        source = rule.get("source", "any")
        action = rule["action"]

        verdict = "accept" if action in ("allow", "limit") else "drop"
        if source and source != "any":
            family = _address_family(source)
            src_clause = f"{family} saddr {source} "
        else:
            src_clause = ""
        limit_clause = "limit rate 10/minute " if action == "limit" else ""
        comment_clause = f' comment "{comment}"' if comment else ""

        lines.append(
            f"        {src_clause}{proto} dport {port} {limit_clause}{verdict}{comment_clause}"
        )

    lines += [
        "    }",
        "",
        "    chain forward {",
        "        type filter hook forward priority 0; policy drop;",
        "    }",
        "",
        "    chain output {",
        "        type filter hook output priority 0; policy accept;",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# fail2ban : jail.local standalone (reutilisable tel quel par le module
# Ansible existant au lieu de re-ecrire la meme logique).
# --------------------------------------------------------------------------
def generate_fail2ban_jail(config):
    jails = config.get("fail2ban_jails") or DEFAULT_FAIL2BAN_JAILS

    lines = [
        "# jail.local — genere par OpsForge (module firewall)",
        "# A placer dans /etc/fail2ban/jail.local",
        "",
        "[DEFAULT]",
        "bantime  = 1h",
        "findtime = 10m",
        "maxretry = 5",
        "",
    ]

    for name, opts in jails.items():
        lines.append(f"[{name}]")
        lines.append(f"enabled = {'true' if opts.get('enabled', True) else 'false'}")
        if opts.get("maxretry") is not None:
            lines.append(f"maxretry = {opts['maxretry']}")
        if opts.get("bantime"):
            lines.append(f"bantime = {opts['bantime']}")
        if opts.get("findtime"):
            lines.append(f"findtime = {opts['findtime']}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Point d'entree principal : assemble les fichiers a ecrire selon la config.
# --------------------------------------------------------------------------
def generate_firewall(config):
    """
    Genere le(s) fichier(s) de pare-feu (+ fail2ban en option) a partir
    d'une config validee. Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)
    backend = config.get("backend", "ufw")

    files = {}
    if backend == "ufw":
        files["setup-firewall.sh"] = generate_ufw_script(config)
    else:
        files["nftables.conf"] = generate_nftables_conf(config)

    if config.get("fail2ban"):
        files["jail.local"] = generate_fail2ban_jail(config)

    return files


def write_firewall(config, output_dir):
    """Ecrit les fichiers generes dans output_dir. Retourne la liste des chemins ecrits."""
    files = generate_firewall(config)
    os.makedirs(output_dir, exist_ok=True)

    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if filename.endswith(".sh"):
            os.chmod(path, 0o755)
        written.append(path)

    return written
