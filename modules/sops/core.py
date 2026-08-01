"""
core.py
-------
Generation d'une config `.sops.yaml` (chiffrement de secrets versionnes
dans Git, via SOPS + age) a partir d'une config JSON. Comble le trou laisse
par le module gitops : celui-ci genere des manifests ArgoCD/FluxCD qui
pointent vers un depot Git, mais rien n'y dit quoi faire des secrets qu'on
voudrait y mettre — le module vault gere les secrets COTE SERVEUR, pas ceux
versionnes dans le depot lui-meme.

SOPS ne chiffre pas un fichier entier : il chiffre les VALEURS d'un
YAML/JSON, en laissant les cles en clair (un diff Git reste lisible : on
voit QUELLE cle a change, pas sa nouvelle valeur). `.sops.yaml`, a la
racine du depot, associe chaque fichier (par regex de chemin) aux
destinataires age autorises a le dechiffrer — `sops` lit ce fichier tout
seul, aucune option a repeter a la main.

Ce module ne genere ni ne manipule de cle privee age : comme pour les cles
SSH, seule la cle PUBLIQUE (le destinataire) a sa place dans une config
versionnee. La paire se genere avec `age-keygen`, hors d'OpsForge.

Usage basique :
    from modules.sops.core import generate_sops

    config = {"preset": "solo-dev", "rules": [...]}
    files = generate_sops(config)   # {".sops.yaml": "...", "sops-diff.gitattributes": "..."}
"""

import copy
import os
import re

SOPS_CONFIG_NAME = ".sops.yaml"
GITATTRIBUTES_SNIPPET_NAME = "sops-diff.gitattributes"

INPUT_TYPES = ["", "yaml", "json", "dotenv", "binary"]

AGE_PRIVATE_KEY_PREFIX = "AGE-SECRET-KEY-1"
# Une vraie cle publique age est "age1" + 58 caracteres bech32 (minuscules
# uniquement). On ne verifie que le prefixe et une longueur plancher, sans
# imposer le charset exact : comme pour les cles SSH placeholder du module
# ssh, un texte lisible ("REMPLACE_PAR_TA_CLE") reste embarque dans le
# placeholder et doit continuer a passer la validation.
AGE_PUBLIC_KEY_MIN_LENGTH = 20


def _is_plausible_age_public_key(value):
    return value.startswith("age1") and len(value) >= AGE_PUBLIC_KEY_MIN_LENGTH


def _looks_like_valid_regex(pattern):
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


# --------------------------------------------------------------------------
# Presets : chaque preset est une liste de regles (path_regex + age +
# encrypted_regex optionnel), pensee pour un cas d'usage courant. Les cles
# publiques age sont des PLACEHOLDERS a remplacer par les tiennes
# (generees avec `age-keygen`) — comme pour les cles SSH, une fausse
# "bonne" valeur n'existe pas ici, il n'y a que la tienne.
# --------------------------------------------------------------------------
PRESETS = {
    "solo-dev": {
        "label": "Solo (une seule cle, tous les secrets du depot)",
        "rules": [
            {
                "label": "Tous les fichiers de secrets",
                "path_regex": r"secrets.*\.(yaml|yml|json|env)$",
                "age_recipients": ["age1REMPLACE_PAR_TA_CLE_PUBLIQUE"],
                "encrypted_regex": "",
                "input_type": "",
            },
        ],
    },
    "team-shared": {
        "label": "Equipe (plusieurs destinataires sur les memes secrets)",
        "rules": [
            {
                "label": "Tous les fichiers de secrets",
                "path_regex": r"secrets.*\.(yaml|yml|json|env)$",
                "age_recipients": [
                    "age1REMPLACE_PAR_LA_CLE_DE_TOM",
                    "age1REMPLACE_PAR_LA_CLE_DE_LEQUIPE",
                ],
                "encrypted_regex": "",
                "input_type": "",
            },
        ],
    },
    "multi-env": {
        "label": "Multi-environnements (une cle differente par environnement)",
        "rules": [
            {
                "label": "Environnement de developpement",
                "path_regex": r"environments/dev/.*\.yaml$",
                "age_recipients": ["age1REMPLACE_PAR_LA_CLE_DEV"],
                "encrypted_regex": "",
                "input_type": "",
            },
            {
                "label": "Environnement de staging",
                "path_regex": r"environments/staging/.*\.yaml$",
                "age_recipients": ["age1REMPLACE_PAR_LA_CLE_STAGING"],
                "encrypted_regex": "",
                "input_type": "",
            },
            {
                "label": "Environnement de production (cle restreinte)",
                "path_regex": r"environments/prod/.*\.yaml$",
                "age_recipients": ["age1REMPLACE_PAR_LA_CLE_PROD"],
                "encrypted_regex": "",
                "input_type": "",
            },
        ],
    },
    "k8s-secrets": {
        "label": "Secrets Kubernetes (seules les valeurs sont chiffrees)",
        "rules": [
            {
                "label": "Manifests Secret (metadonnees en clair, valeurs chiffrees)",
                "path_regex": r"k8s/secrets/.*\.yaml$",
                "age_recipients": ["age1REMPLACE_PAR_TA_CLE_PUBLIQUE"],
                # Ne chiffre QUE les cles 'data'/'stringData' : le reste du
                # manifest (kind, metadata, apiVersion) reste lisible en
                # clair, donc diffable et relisable sans dechiffrer.
                "encrypted_regex": "^(data|stringData)$",
                "input_type": "",
            },
        ],
    },
    "terraform-tfvars": {
        "label": "Variables Terraform (*.tfvars.json)",
        "rules": [
            {
                "label": "Fichiers de variables Terraform",
                "path_regex": r".*\.tfvars\.json$",
                "age_recipients": ["age1REMPLACE_PAR_TA_CLE_PUBLIQUE"],
                "encrypted_regex": "",
                "input_type": "json",
            },
        ],
    },
    "custom": {
        "label": "Personnalise (regles fournies manuellement)",
        "rules": [],
    },
}


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def get_preset(name):
    """
    Retourne une config de depart prete a generer pour le preset donne
    (copie profonde : modifiable sans affecter PRESETS).
    """
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Disponibles : {', '.join(PRESETS)}."
        )
    preset_def = PRESETS[name]
    return {
        "preset": name,
        "rules": copy.deepcopy(preset_def["rules"]),
    }


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    rules = config.get("rules") or []
    if not rules:
        errors.append("Aucune regle definie : ajoute au moins une regle (chemin + destinataires).")

    seen_path_regex = []
    for index, rule in enumerate(rules, start=1):
        label = f"Regle #{index}"

        path_regex = (rule.get("path_regex") or "").strip()
        if not path_regex:
            errors.append(f"{label} : expression de chemin manquante (path_regex).")
        elif not _looks_like_valid_regex(path_regex):
            errors.append(f"{label} : expression de chemin invalide ('{path_regex}').")
        else:
            if path_regex in seen_path_regex:
                errors.append(f"{label} : expression de chemin '{path_regex}' deja utilisee par une autre regle.")
            seen_path_regex.append(path_regex)

        recipients = rule.get("age_recipients") or []
        if not recipients:
            errors.append(f"{label} : aucun destinataire age (age_recipients) — personne ne pourrait dechiffrer.")
        for recipient in recipients:
            recipient = (recipient or "").strip()
            if recipient.startswith(AGE_PRIVATE_KEY_PREFIX):
                errors.append(
                    f"{label} : ceci est une cle PRIVEE age. Seule la cle PUBLIQUE "
                    "(destinataire, commence par 'age1') a sa place ici — la cle privee "
                    "ne doit jamais quitter la machine qui dechiffre."
                )
            elif not _is_plausible_age_public_key(recipient):
                errors.append(
                    f"{label} : destinataire age invalide ('{recipient}'). "
                    "Attendu : une cle publique commencant par 'age1' (generee par age-keygen)."
                )

        encrypted_regex = (rule.get("encrypted_regex") or "").strip()
        if encrypted_regex and not _looks_like_valid_regex(encrypted_regex):
            errors.append(f"{label} : expression 'encrypted_regex' invalide ('{encrypted_regex}').")

        input_type = rule.get("input_type") or ""
        if input_type not in INPUT_TYPES:
            errors.append(
                f"{label} : type d'entree non supporte ('{input_type}'). "
                f"Disponibles : {', '.join(t or 'auto' for t in INPUT_TYPES)}."
            )

    return errors


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
def _yaml_escape(value):
    """Echappement minimal pour une valeur scalaire YAML entre guillemets simples."""
    return str(value).replace("'", "''")


def generate_sops_yaml(config):
    """Genere le contenu de .sops.yaml."""
    rules = config.get("rules") or []

    lines = [
        "# Genere par OpsForge (module sops).",
        "# A placer a la racine du depot Git : `sops` le lit tout seul,",
        "# aucune option a repeter a la main a chaque chiffrement.",
        "#",
        "# Ce fichier ne contient QUE des cles publiques age (destinataires) :",
        "# la cle privee correspondante reste hors du depot, generee et gardee",
        "# localement via `age-keygen`.",
        "creation_rules:",
    ]

    for rule in rules:
        label = (rule.get("label") or "").strip()
        if label:
            lines.append(f"  # {label}")
        lines.append(f"  - path_regex: {rule['path_regex']}")

        recipients = [r.strip() for r in (rule.get("age_recipients") or [])]
        lines.append(f"    age: {','.join(recipients)}")

        encrypted_regex = (rule.get("encrypted_regex") or "").strip()
        if encrypted_regex:
            lines.append(f"    encrypted_regex: '{_yaml_escape(encrypted_regex)}'")

        input_type = rule.get("input_type") or ""
        if input_type:
            lines.append(f"    input_type: {input_type}")

        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def generate_gitattributes_snippet(config):
    """
    Genere un fragment .gitattributes (diff SOPS lisible) + le rappel de la
    commande de config Git associee. Un fichier a part, pas '.gitattributes'
    directement : coller a la main evite d'ecraser un .gitattributes deja
    existant dans le depot cible.
    """
    lines = [
        "# Genere par OpsForge (module sops).",
        "# A COLLER dans le .gitattributes du depot (ne remplace pas le tien,",
        "# c'est un fragment a fusionner avec le reste).",
        "#",
        "# Sans ca, `git diff` sur un fichier chiffre n'affiche que du texte",
        "# chiffre illisible. Avec ce driver, git appelle `sops -d` avant de",
        "# comparer : le diff redevient lisible (valeurs en clair QUE dans le",
        "# terminal de qui a la cle, jamais ecrites sur disque).",
        "",
    ]

    seen_patterns = set()
    for rule in config.get("rules") or []:
        path_regex = rule.get("path_regex") or ""
        # Best-effort : une regex Python/Go n'est pas un glob Git, on ne
        # peut pas la convertir fidelement. On propose un pattern large
        # base sur l'extension pour rester correct plutot que precis.
        pattern = "*.yaml diff=sopsdiffer"
        if path_regex.endswith(r"\.json$") or ".json" in path_regex:
            pattern = "*.json diff=sopsdiffer"
        if pattern not in seen_patterns:
            lines.append(pattern)
            seen_patterns.add(pattern)

    lines += [
        "",
        "# Puis, une fois par clone (pas versionne, c'est une config locale) :",
        "#   git config diff.sopsdiffer.textconv \"sops -d\"",
    ]

    return "\n".join(lines) + "\n"


def generate_sops(config):
    """
    Genere le(s) fichier(s) SOPS a partir d'une config validee.
    Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)

    return {
        SOPS_CONFIG_NAME: generate_sops_yaml(config),
        GITATTRIBUTES_SNIPPET_NAME: generate_gitattributes_snippet(config),
    }


def write_sops(config, output_dir):
    """Ecrit le(s) fichier(s) genere(s) dans output_dir. Retourne la liste des chemins ecrits."""
    files = generate_sops(config)
    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(path)

    return written
