"""
deps_core.py
------------
Mises a jour automatiques des dependances : genere un `.github/dependabot.yml`
(Dependabot) ou un `renovate.json` (Renovate).

C'est une extension du module CI/CD, pas un module a part : le fichier produit
se depose dans le meme depot que le pipeline, se deduit des memes stacks
detectees, et tient en une trentaine de lignes. Un module complet avec sa page
et sa CLI dediees pour un seul petit fichier de config n'aurait pas eu de sens.

Les deux outils font la meme chose (ouvrir des PR quand une dependance sort en
nouvelle version) avec deux perimetres :
  - Dependabot : natif GitHub, zero installation, un bloc par ecosysteme.
  - Renovate   : plus configurable (regroupement, plages horaires, automerge),
                 disponible en app GitHub, sur GitLab, Bitbucket ou auto-heberge.

Usage basique :
    from modules.cicd.deps_core import generate_deps_config

    stacks = [{"language": "python", "package_manager": "pip"}]
    filename, content = generate_deps_config(stacks, tool="dependabot")
"""

import json
import os

SUPPORTED_TOOLS = ["dependabot", "renovate"]
SCHEDULES = ["daily", "weekly", "monthly"]

FILENAMES = {
    "dependabot": ".github/dependabot.yml",
    "renovate": "renovate.json",
}

TOOL_LABELS = {
    "dependabot": "Dependabot (natif GitHub)",
    "renovate": "Renovate (GitHub / GitLab / Bitbucket, auto-hebergeable)",
}

# Correspondance langage -> ecosysteme, dans le vocabulaire de chaque outil.
# 'by_package_manager' gere les langages ou le gestionnaire change
# l'ecosysteme (Java : Maven ou Gradle, deux formats de fichier differents).
ECOSYSTEMS = {
    "python": {"dependabot": "pip", "renovate": ["pip_requirements", "poetry", "pep621"]},
    "node": {"dependabot": "npm", "renovate": ["npm"]},
    "go": {"dependabot": "gomod", "renovate": ["gomod"]},
    "rust": {"dependabot": "cargo", "renovate": ["cargo"]},
    "java": {
        "dependabot": "maven",
        "renovate": ["maven"],
        "by_package_manager": {
            "gradle": {"dependabot": "gradle", "renovate": ["gradle"]},
        },
    },
    "php": {"dependabot": "composer", "renovate": ["composer"]},
    "ruby": {"dependabot": "bundler", "renovate": ["bundler"]},
    "dotnet": {"dependabot": "nuget", "renovate": ["nuget"]},
}

# Ecosystemes qui ne viennent pas d'un langage detecte mais du depot lui-meme.
EXTRA_ECOSYSTEMS = {
    "github_actions": {"dependabot": "github-actions", "renovate": ["github-actions"]},
    "docker": {"dependabot": "docker", "renovate": ["dockerfile", "docker-compose"]},
}

# Plage horaire Renovate par frequence. Renovate n'a pas d'"interval" comme
# Dependabot : il travaille en continu et se bride via un creneau exprime en
# langage naturel.
RENOVATE_SCHEDULES = {
    "daily": ["before 5am"],
    "weekly": ["before 5am on monday"],
    "monthly": ["before 5am on the first day of the month"],
}

DEFAULTS = {
    "schedule": "weekly",
    "open_pr_limit": 5,
    "directory": "/",
    "group_minor_patch": True,
    "include_github_actions": True,
    "include_docker": False,
}


def list_tools():
    """Liste les outils disponibles (dans un ordre stable)."""
    return list(SUPPORTED_TOOLS)


def list_schedules():
    """Liste les frequences de mise a jour disponibles."""
    return list(SCHEDULES)


def _ecosystem_for(stack, tool):
    """Retourne l'ecosysteme (str pour dependabot, liste pour renovate), ou None."""
    language = stack.get("language")
    entry = ECOSYSTEMS.get(language)
    if entry is None:
        return None

    package_manager = (stack.get("package_manager") or "").lower()
    override = (entry.get("by_package_manager") or {}).get(package_manager)
    if override:
        return override[tool]

    return entry[tool]


def resolve_ecosystems(stacks, tool, include_github_actions=True, include_docker=False):
    """
    Traduit les stacks detectees en ecosystemes, sans doublon et dans
    l'ordre des stacks. Les langages inconnus sont ignores silencieusement
    (meme logique que les cibles de deploiement du generateur de pipeline).
    """
    resolved = []

    def _add(value):
        for item in value if isinstance(value, list) else [value]:
            if item not in resolved:
                resolved.append(item)

    for stack in stacks or []:
        ecosystem = _ecosystem_for(stack, tool)
        if ecosystem:
            _add(ecosystem)

    if include_github_actions:
        _add(EXTRA_ECOSYSTEMS["github_actions"][tool])
    if include_docker:
        _add(EXTRA_ECOSYSTEMS["docker"][tool])

    return resolved


def _validate(tool, schedule, ecosystems):
    if tool not in SUPPORTED_TOOLS:
        raise ValueError(
            f"Outil de mise a jour inconnu : '{tool}'. Disponibles : {', '.join(SUPPORTED_TOOLS)}."
        )
    if schedule not in SCHEDULES:
        raise ValueError(
            f"Frequence inconnue : '{schedule}'. Disponibles : {', '.join(SCHEDULES)}."
        )
    if not ecosystems:
        raise ValueError(
            "Aucun ecosysteme a surveiller : aucune stack reconnue et aucune "
            "option supplementaire (GitHub Actions, Docker) activee."
        )


# --------------------------------------------------------------------------
# Dependabot : .github/dependabot.yml
# --------------------------------------------------------------------------
def generate_dependabot_yaml(stacks, schedule=None, open_pr_limit=None, target_branch=None,
                             directory=None, include_github_actions=None, include_docker=None,
                             group_minor_patch=None):
    """Genere le contenu d'un fichier .github/dependabot.yml (version 2)."""
    schedule = schedule or DEFAULTS["schedule"]
    open_pr_limit = int(open_pr_limit or DEFAULTS["open_pr_limit"])
    directory = directory or DEFAULTS["directory"]
    if include_github_actions is None:
        include_github_actions = DEFAULTS["include_github_actions"]
    if include_docker is None:
        include_docker = DEFAULTS["include_docker"]
    if group_minor_patch is None:
        group_minor_patch = DEFAULTS["group_minor_patch"]

    ecosystems = resolve_ecosystems(
        stacks, "dependabot",
        include_github_actions=include_github_actions,
        include_docker=include_docker,
    )
    _validate("dependabot", schedule, ecosystems)

    lines = [
        "# Genere par OpsForge (module cicd, extension mises a jour de dependances).",
        "# A placer dans .github/dependabot.yml — GitHub le prend en compte sans",
        "# rien installer : Settings > Code security doit juste avoir Dependabot actif.",
        "version: 2",
        "updates:",
    ]

    for ecosystem in ecosystems:
        # GitHub Actions se declare toujours sur '/' : Dependabot y cherche
        # .github/workflows/, pas le dossier du code.
        ecosystem_dir = "/" if ecosystem == "github-actions" else directory
        lines.append(f'  - package-ecosystem: "{ecosystem}"')
        lines.append(f'    directory: "{ecosystem_dir}"')
        lines.append("    schedule:")
        lines.append(f'      interval: "{schedule}"')
        lines.append(f"    open-pull-requests-limit: {open_pr_limit}")
        if target_branch:
            lines.append(f'    target-branch: "{target_branch}"')
        lines.append("    labels:")
        lines.append('      - "dependances"')
        if group_minor_patch:
            # Sans groupe, une PR par dependance et par semaine : le depot
            # est vite noye. Les majeures restent seules, elles cassent.
            lines.append("    groups:")
            lines.append(f"      {ecosystem}-mineures:")
            lines.append("        update-types:")
            lines.append('          - "minor"')
            lines.append('          - "patch"')
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# Renovate : renovate.json
# --------------------------------------------------------------------------
def generate_renovate_json(stacks, schedule=None, open_pr_limit=None, target_branch=None,
                           include_github_actions=None, include_docker=None,
                           group_minor_patch=None):
    """Genere le contenu d'un fichier renovate.json."""
    schedule = schedule or DEFAULTS["schedule"]
    open_pr_limit = int(open_pr_limit or DEFAULTS["open_pr_limit"])
    if include_github_actions is None:
        include_github_actions = DEFAULTS["include_github_actions"]
    if include_docker is None:
        include_docker = DEFAULTS["include_docker"]
    if group_minor_patch is None:
        group_minor_patch = DEFAULTS["group_minor_patch"]

    managers = resolve_ecosystems(
        stacks, "renovate",
        include_github_actions=include_github_actions,
        include_docker=include_docker,
    )
    _validate("renovate", schedule, managers)

    config = {
        "$schema": "https://docs.renovatebot.com/renovate-schema.json",
        "extends": ["config:recommended", ":dependencyDashboard"],
        "enabledManagers": managers,
        "schedule": RENOVATE_SCHEDULES[schedule],
        "timezone": "Europe/Paris",
        "prConcurrentLimit": open_pr_limit,
        "labels": ["dependances"],
    }

    if target_branch:
        config["baseBranches"] = [target_branch]

    package_rules = []
    if group_minor_patch:
        package_rules.append({
            "matchUpdateTypes": ["minor", "patch"],
            "groupName": "dependances mineures",
        })
    package_rules.append({
        "description": "Les majeures restent seules : c'est la ou ca casse.",
        "matchUpdateTypes": ["major"],
        "labels": ["dependances", "breaking"],
    })
    config["packageRules"] = package_rules

    # Les failles de securite ne doivent pas attendre le creneau hebdo.
    config["vulnerabilityAlerts"] = {
        "labels": ["securite"],
        "schedule": ["at any time"],
    }

    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# Point d'entree commun
# --------------------------------------------------------------------------
def generate_deps_config(stacks, tool="dependabot", **options):
    """
    Genere le fichier de mise a jour des dependances.
    Retourne (nom_de_fichier, contenu).
    """
    if tool not in SUPPORTED_TOOLS:
        raise ValueError(
            f"Outil de mise a jour inconnu : '{tool}'. Disponibles : {', '.join(SUPPORTED_TOOLS)}."
        )

    if tool == "dependabot":
        content = generate_dependabot_yaml(stacks, **options)
    else:
        # 'directory' n'existe pas cote Renovate : il balaie tout le depot.
        options.pop("directory", None)
        content = generate_renovate_json(stacks, **options)

    return FILENAMES[tool], content


def write_deps_config(stacks, output_path, tool="dependabot", **options):
    """Genere le fichier et l'ecrit directement sur disque."""
    _, content = generate_deps_config(stacks, tool=tool, **options)
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
