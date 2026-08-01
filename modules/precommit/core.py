"""
core.py
-------
Generation de hooks Git pre-commit (verifications avant chaque commit) a
partir d'une config JSON. Comble un trou courant : la plupart des projets
n'ont ni lint, ni format, ni scan de secrets avant que le code n'atterisse
dans l'historique — corrige a la main, en retard, ou jamais.

Deux backends :

  - "pre-commit" : le framework Python standard (pre-commit.com), agnostique
                    du langage, tres repandu meme hors ecosystemes Python.
  - "husky"       : hooks Git natifs pour projets Node.js/JS, couple a
                    lint-staged (ne verifie que les fichiers modifies).

Chaque hook du catalogue sait se traduire dans l'un des deux formats (ou les
deux). Les presets choisissent un sous-ensemble de hooks pertinent pour un
langage/cas d'usage donne ; le backend determine juste le format de sortie.

Usage basique :
    from modules.precommit.core import generate_precommit

    config = {"preset": "python", "backend": "pre-commit"}
    files = generate_precommit(config)   # {".pre-commit-config.yaml": "..."}
"""

import copy

SUPPORTED_BACKENDS = ["pre-commit", "husky"]

# --------------------------------------------------------------------------
# Catalogue des hooks disponibles. Chaque hook peut avoir un mapping vers
# l'un ou l'autre backend (ou les deux) ; un hook sans mapping pour le
# backend choisi est silencieusement ignore a la generation (ex: black n'a
# pas de sens cote husky, un projet Node).
# --------------------------------------------------------------------------
HOOK_CATALOG = {
    "trailing-whitespace": {
        "label": "Supprimer les espaces en fin de ligne",
        "pre_commit": {"repo": "https://github.com/pre-commit/pre-commit-hooks", "rev": "v4.6.0", "hook_id": "trailing-whitespace"},
    },
    "end-of-file-fixer": {
        "label": "Forcer une ligne vide en fin de fichier",
        "pre_commit": {"repo": "https://github.com/pre-commit/pre-commit-hooks", "rev": "v4.6.0", "hook_id": "end-of-file-fixer"},
    },
    "check-yaml": {
        "label": "Valider la syntaxe des fichiers YAML",
        "pre_commit": {"repo": "https://github.com/pre-commit/pre-commit-hooks", "rev": "v4.6.0", "hook_id": "check-yaml"},
    },
    "check-added-large-files": {
        "label": "Bloquer les gros fichiers commites par erreur",
        "pre_commit": {"repo": "https://github.com/pre-commit/pre-commit-hooks", "rev": "v4.6.0", "hook_id": "check-added-large-files"},
    },
    "detect-private-key": {
        "label": "Detecter les cles privees commitees par erreur",
        "pre_commit": {"repo": "https://github.com/pre-commit/pre-commit-hooks", "rev": "v4.6.0", "hook_id": "detect-private-key"},
    },
    "black": {
        "label": "Formater le code Python (Black)",
        "pre_commit": {"repo": "https://github.com/psf/black", "rev": "24.4.2", "hook_id": "black"},
    },
    "ruff": {
        "label": "Linter Python rapide (Ruff)",
        "pre_commit": {"repo": "https://github.com/astral-sh/ruff-pre-commit", "rev": "v0.4.4", "hook_id": "ruff"},
    },
    "mypy": {
        "label": "Verification de types statique (mypy)",
        "pre_commit": {"repo": "https://github.com/pre-commit/mirrors-mypy", "rev": "v1.10.0", "hook_id": "mypy"},
    },
    "eslint": {
        "label": "Linter JavaScript/TypeScript (ESLint)",
        "husky": {"pattern": "*.{js,jsx,ts,tsx}", "command": "eslint --fix"},
    },
    "prettier": {
        "label": "Formater JS/TS/JSON/CSS/Markdown (Prettier)",
        "husky": {"pattern": "*.{js,jsx,ts,tsx,json,css,md}", "command": "prettier --write"},
    },
    "gitleaks": {
        "label": "Scanner les secrets avant commit (Gitleaks)",
        "pre_commit": {"repo": "https://github.com/gitleaks/gitleaks", "rev": "v8.18.4", "hook_id": "gitleaks"},
        "husky": {"raw_command": "gitleaks protect --staged --verbose"},
    },
}

# --------------------------------------------------------------------------
# Presets : chaque preset est une liste de hooks du catalogue, pensee pour
# un langage/cas d'usage courant. "custom" part d'une liste vide.
# --------------------------------------------------------------------------
PRESETS = {
    "python": {
        "label": "Projet Python (format, lint, hygiene generale)",
        "hooks": ["trailing-whitespace", "end-of-file-fixer", "check-yaml", "check-added-large-files", "black", "ruff"],
    },
    "javascript": {
        "label": "Projet JavaScript/TypeScript (lint, format)",
        "hooks": ["trailing-whitespace", "end-of-file-fixer", "eslint", "prettier"],
    },
    "generic": {
        "label": "Hygiene generale (n'importe quel langage)",
        "hooks": ["trailing-whitespace", "end-of-file-fixer", "check-yaml", "check-added-large-files", "detect-private-key"],
    },
    "secrets-scan": {
        "label": "Scan de secrets seul (Gitleaks)",
        "hooks": ["gitleaks"],
    },
    "custom": {
        "label": "Personnalise (hooks fournis manuellement)",
        "hooks": [],
    },
}


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def list_hooks():
    """Liste les IDs de hooks disponibles dans le catalogue (ordre stable)."""
    return list(HOOK_CATALOG.keys())


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
    backend = "husky" if name == "javascript" else "pre-commit"
    return {
        "preset": name,
        "backend": backend,
        "hooks": list(preset_def["hooks"]),
    }


def _resolve_hooks(config):
    preset = config.get("preset", "custom")
    if preset not in PRESETS:
        preset = "custom"
    if preset == "custom":
        return config.get("hooks", [])
    return PRESETS[preset]["hooks"]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
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

    backend = config.get("backend", "pre-commit")
    if backend not in SUPPORTED_BACKENDS:
        errors.append(
            f"Backend non supporte : '{backend}'. Disponibles : {', '.join(SUPPORTED_BACKENDS)}."
        )
        backend = "pre-commit"

    hooks = _resolve_hooks(config)

    if preset == "custom" and not hooks:
        errors.append("Preset 'custom' choisi mais aucun hook fourni (hooks).")

    unknown = [h for h in hooks if h not in HOOK_CATALOG]
    for h in unknown:
        errors.append(f"Hook inconnu : '{h}'. Disponibles : {', '.join(HOOK_CATALOG)}.")

    if not unknown and hooks:
        key = "pre_commit" if backend == "pre-commit" else "husky"
        supported = [h for h in hooks if key in HOOK_CATALOG[h]]
        if not supported:
            errors.append(
                f"Aucun des hooks selectionnes n'est disponible pour le backend '{backend}'."
            )

    return errors


# --------------------------------------------------------------------------
# Backend pre-commit : .pre-commit-config.yaml
# --------------------------------------------------------------------------
def generate_precommit_yaml(config):
    hooks = _resolve_hooks(config)
    supported = [h for h in hooks if "pre_commit" in HOOK_CATALOG[h]]

    # Regroupe les hooks par repo (un seul bloc "repo:" par depot, avec
    # plusieurs hooks dedans si plusieurs hooks viennent du meme repo).
    repos = {}
    order = []
    for hook_id in supported:
        mapping = HOOK_CATALOG[hook_id]["pre_commit"]
        key = (mapping["repo"], mapping["rev"])
        if key not in repos:
            repos[key] = []
            order.append(key)
        repos[key].append(mapping["hook_id"])

    lines = ["# Genere par OpsForge (module precommit).", "repos:"]
    for repo, rev in order:
        lines.append(f"  - repo: {repo}")
        lines.append(f"    rev: {rev}")
        lines.append("    hooks:")
        for hook_id in repos[(repo, rev)]:
            lines.append(f"      - id: {hook_id}")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Backend husky : .husky/pre-commit (script shell) + extrait lint-staged
# (a coller dans package.json).
# --------------------------------------------------------------------------
def generate_husky_files(config):
    hooks = _resolve_hooks(config)
    supported = [h for h in hooks if "husky" in HOOK_CATALOG[h]]

    lint_staged_entries = {}
    raw_commands = []
    for hook_id in supported:
        mapping = HOOK_CATALOG[hook_id]["husky"]
        if "raw_command" in mapping:
            raw_commands.append(mapping["raw_command"])
        else:
            pattern = mapping["pattern"]
            lint_staged_entries.setdefault(pattern, []).append(mapping["command"])

    # .husky/pre-commit : script shell qui lance lint-staged, puis les
    # commandes "raw" (comme gitleaks, qui scanne tout le repo, pas des
    # fichiers individuels selectionnes par un pattern).
    script_lines = ["#!/usr/bin/env sh", '. "$(dirname "$0")/_/husky.sh"', ""]
    if lint_staged_entries:
        script_lines.append("npx lint-staged")
    for cmd in raw_commands:
        script_lines.append(cmd)
    script_lines.append("")
    hook_script = "\n".join(script_lines)

    # Extrait lint-staged (format JSON, a coller dans package.json sous la
    # cle "lint-staged" — pas ecrit directement dans package.json pour ne
    # pas ecraser un fichier existant du projet).
    lint_staged_lines = ["{"]
    entries = list(lint_staged_entries.items())
    for i, (pattern, commands) in enumerate(entries):
        commands_json = ", ".join(f'"{c}"' for c in commands)
        comma = "," if i < len(entries) - 1 else ""
        lint_staged_lines.append(f'  "{pattern}": [{commands_json}]{comma}')
    lint_staged_lines.append("}")
    lint_staged_json = "\n".join(lint_staged_lines) if entries else "{}"

    return {
        ".husky/pre-commit": hook_script,
        "lint-staged.config.json": lint_staged_json,
    }


# --------------------------------------------------------------------------
# Point d'entree principal.
# --------------------------------------------------------------------------
def generate_precommit(config):
    """
    Genere le(s) fichier(s) de hooks a partir d'une config validee.
    Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)
    backend = config.get("backend", "pre-commit")

    if backend == "pre-commit":
        return {".pre-commit-config.yaml": generate_precommit_yaml(config)}
    return generate_husky_files(config)


def write_precommit(config, output_dir):
    """Ecrit le(s) fichier(s) genere(s) dans output_dir. Retourne la liste des chemins ecrits."""
    import os

    files = generate_precommit(config)
    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if filename.endswith("pre-commit") and "/" in filename:
            os.chmod(path, 0o755)
        written.append(path)

    return written
