"""
core.py
-------
Assemble un fichier GitHub Actions (.yml) complet a partir :
- des stacks detectees/choisies (langage, version, package manager)
- des jobs demandes (lint, test, build)
- des cibles de deploiement demandees (github_pages, docker_hub, ssh)
- des declencheurs (branches, PR, manuel)

Usage basique :
    from generator.core import generate_workflow

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    jobs = ["lint", "test", "build"]
    yaml_text = generate_workflow(stacks, jobs)

Avec deploiement :
    yaml_text = generate_workflow(
        stacks, jobs,
        deploy={
            "targets": ["docker_hub"],
            "docker_image": "monusername/monapp",
        },
    )
"""

import os

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# --------------------------------------------------------------------------
# Commandes d'installation par langage / package manager.
# --------------------------------------------------------------------------
INSTALL_COMMANDS = {
    "python": {
        "pip": "pip install -r requirements.txt",
        "poetry": "pip install poetry && poetry install",
        "pipenv": "pip install pipenv && pipenv install --dev",
    },
    "node": {
        "npm": "npm ci",
        "yarn": "yarn install --frozen-lockfile",
        "pnpm": "npm install -g pnpm && pnpm install --frozen-lockfile",
    },
    "go": {
        "go modules": "go mod download",
    },
    "java": {
        "maven": "mvn install -DskipTests",
        "gradle": "./gradlew build -x test",
    },
    "php": {
        "composer": "composer install --no-interaction",
    },
}

# Valeurs par defaut si aucune version n'est detectee automatiquement
DEFAULT_VERSIONS = {
    "python": "3.12",
    "node": "20",
    "go": "1.22",
    "rust": "stable",
    "java": "17",
    "php": "8.3",
}

# Jobs disponibles par langage
AVAILABLE_JOBS = {
    "python": ["lint", "test", "build"],
    "node": ["lint", "test", "build"],
    "go": ["lint", "test", "build"],
    "rust": ["lint", "test", "build"],
    "java": ["lint", "test", "build"],
    "php": ["lint", "test", "build"],
}

# Nom de la cle utilisee dans 'strategy.matrix' pour chaque langage
# (matrix builds : tester plusieurs versions du langage dans le job test)
MATRIX_KEYS = {
    "python": "python-version",
    "node": "node-version",
    "go": "go-version",
    "rust": "rust-version",
    "java": "java-version",
    "php": "php-version",
}

# --------------------------------------------------------------------------
# Cibles de deploiement disponibles.
# "requires_language" : si defini, la cible n'est utilisable que si une
# stack de ce langage est presente (ex: GitHub Pages -> Node uniquement
# pour l'instant, car il faut un build de site statique).
# --------------------------------------------------------------------------
DEPLOY_TARGETS = {
    "github_pages": {
        "template": "deploy/github_pages.yml",
        "requires_language": "node",
        "label": "GitHub Pages",
    },
    "docker_hub": {
        "template": "deploy/docker_hub.yml",
        "requires_language": None,
        "label": "Docker Hub",
    },
    "ssh": {
        "template": "deploy/ssh.yml",
        "requires_language": None,
        "label": "Serveur via SSH",
    },
    "vercel": {
        "template": "deploy/vercel.yml",
        "requires_language": None,
        "label": "Vercel",
    },
    "aws_s3": {
        "template": "deploy/aws_s3.yml",
        "requires_language": "node",
        "label": "AWS S3",
    },
}

DEPLOY_DEFAULTS = {
    "pages_dir": "dist",
    "pages_build_cmd": "npm run build",
    "docker_image": "monusername/monapp",
    "deploy_path": "/var/www/monapp",
    "service_name": "monapp",
    "aws_region": "us-east-1",
    "s3_bucket": "mon-bucket-s3",
}


def _load_template(relative_path):
    """Charge le contenu brut d'un template .yml, ou None si absent."""
    path = os.path.join(TEMPLATES_DIR, relative_path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _get_install_cmd(language, package_manager):
    """Retourne la commande d'installation adaptee, ou une valeur par defaut."""
    lang_commands = INSTALL_COMMANDS.get(language, {})
    if package_manager in lang_commands:
        return lang_commands[package_manager]
    if lang_commands:
        return next(iter(lang_commands.values()))
    return "echo 'Aucune commande d-installation definie pour ce langage'"


def _replace_placeholders(template_text, values):
    """
    Remplace les placeholders {xxx} listes dans `values` par leur valeur,
    via de simples remplacements de sous-chaines (PAS .format()).

    C'est volontaire : les templates contiennent aussi de la syntaxe
    GitHub Actions comme ${{ secrets.MON_SECRET }}, qui utilise des
    doubles-accolades. .format() interpreterait ces accolades comme des
    echappements et casserait la syntaxe. Un simple .replace() cible
    uniquement nos propres placeholders et laisse le reste intact.
    """
    result = template_text
    for key, value in values.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def _fill_stack_template(template_text, stack, version_override=None):
    """Remplace les placeholders lies a une stack (version, install_cmd, cache_key).

    version_override permet d'injecter l'expression GitHub Actions
    '${{ matrix.python-version }}' a la place d'une version litterale,
    utilise pour les matrix builds.
    """
    language = stack["language"]
    version = version_override or stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
    package_manager = stack.get("package_manager", "")
    install_cmd = _get_install_cmd(language, package_manager)
    cache_key = package_manager if package_manager in ("npm", "yarn", "pnpm") else "npm"

    return _replace_placeholders(template_text, {
        "version": version,
        "install_cmd": install_cmd,
        "cache_key": cache_key,
    })


def _build_job_block(job_name, steps_text, needs=None, matrix=None):
    """
    Construit le bloc YAML d'un job complet (indentation correcte).

    Args:
        job_name (str): nom du job (cle YAML)
        steps_text (str): steps deja indentes (6 espaces pour "- name:")
        needs (list[str]|None): jobs dont depend celui-ci (section 'needs:')
        matrix (dict|None): ex {"python-version": ["3.10", "3.11", "3.12"]}
            genere une section 'strategy.matrix' (matrix build).
    """
    needs_line = ""
    if needs:
        needs_yaml = ", ".join(needs)
        needs_line = f"    needs: [{needs_yaml}]\n"

    strategy_lines = ""
    if matrix:
        strategy_lines = "    strategy:\n      matrix:\n"
        for key, values in matrix.items():
            values_yaml = ", ".join(f'"{v}"' for v in values)
            strategy_lines += f"        {key}: [{values_yaml}]\n"

    return (
        f"  {job_name}:\n"
        f"{needs_line}"
        f"{strategy_lines}"
        f"    runs-on: ubuntu-latest\n"
        f"    steps:\n"
        f"{steps_text}"
    )


def _build_triggers_block(triggers):
    """Construit la section 'on:' du workflow a partir des options choisies."""
    triggers = triggers or {}
    branches = triggers.get("branches", ["main"])
    pull_request = triggers.get("pull_request", True)
    workflow_dispatch = triggers.get("workflow_dispatch", True)
    schedule_cron = triggers.get("schedule_cron")

    branches_yaml = ", ".join(branches)
    # "on" entre guillemets : YAML 1.1 interprete le mot nu comme un booleen
    lines = ['"on":']
    lines.append(f"  push:\n    branches: [{branches_yaml}]")
    if pull_request:
        lines.append(f"  pull_request:\n    branches: [{branches_yaml}]")
    if workflow_dispatch:
        lines.append("  workflow_dispatch:")
    if schedule_cron:
        lines.append(f"  schedule:\n    - cron: '{schedule_cron}'")

    return "\n".join(lines)


def _build_stack_jobs(stacks, jobs):
    """
    Construit les jobs lint/test/build pour chaque stack, avec dependances
    logiques : si test ET build sont tous les deux demandes pour une meme
    stack, le job build attend que le job test reussisse (needs: test-xxx).
    Le job lint reste independant (feedback le plus rapide possible).

    Returns:
        (job_blocks, test_job_names, build_job_names)
        - job_blocks: liste des blocs YAML des jobs
        - test_job_names: noms des jobs de test crees (utile pour le deploiement)
        - build_job_names: noms des jobs de build crees (utile pour le deploiement)
    """
    job_blocks = []
    test_job_names = []
    build_job_names = []

    for stack in stacks:
        language = stack["language"]
        available_for_lang = AVAILABLE_JOBS.get(language, [])
        created_jobs = {}  # job_type -> job_name, pour cette stack

        # On traite dans un ordre fixe pour que 'test' existe avant 'build'
        # au moment de calculer les dependances.
        for job_type in ("lint", "test", "build"):
            if job_type not in jobs or job_type not in available_for_lang:
                continue

            raw_template = _load_template(f"{language}/{job_type}.yml")
            if raw_template is None:
                continue

            # Matrix build : uniquement pour 'test', et seulement si
            # plusieurs versions sont demandees pour cette stack.
            matrix_versions = stack.get("matrix_versions") or []
            matrix = None
            version_override = None
            if job_type == "test" and len(matrix_versions) > 1:
                matrix_key = MATRIX_KEYS.get(language, "version")
                matrix = {matrix_key: matrix_versions}
                version_override = "${{ matrix.%s }}" % matrix_key

            filled_steps = _fill_stack_template(raw_template, stack, version_override=version_override)
            job_name = f"{job_type}-{language}"

            needs = None
            if job_type == "build" and "test" in created_jobs:
                needs = [created_jobs["test"]]

            job_blocks.append(_build_job_block(job_name, filled_steps, needs=needs, matrix=matrix))
            created_jobs[job_type] = job_name

            if job_type == "test":
                test_job_names.append(job_name)
            elif job_type == "build":
                build_job_names.append(job_name)

    return job_blocks, test_job_names, build_job_names


def _build_deploy_jobs(deploy_config, stacks, test_job_names, build_job_names):
    """
    Construit les jobs de deploiement demandes.

    Chaque job de deploiement depend des jobs de build s'il y en a,
    sinon des jobs de test s'il y en a, sinon il ne depend de rien
    (deploiement direct, deconseille mais possible).
    """
    if not deploy_config or not deploy_config.get("targets"):
        return []

    targets = deploy_config["targets"]
    needs = build_job_names or test_job_names or None

    job_blocks = []

    for target in targets:
        target_info = DEPLOY_TARGETS.get(target)
        if target_info is None:
            continue

        required_lang = target_info["requires_language"]
        stack_for_target = None
        if required_lang:
            stack_for_target = next(
                (s for s in stacks if s["language"] == required_lang), None
            )
            if stack_for_target is None:
                # Cible ignoree silencieusement : pas de stack compatible.
                # (ex: github_pages demande mais pas de stack Node fournie)
                continue

        raw_template = _load_template(target_info["template"])
        if raw_template is None:
            continue

        values = {
            "pages_dir": deploy_config.get("pages_dir") or DEPLOY_DEFAULTS["pages_dir"],
            "build_cmd": deploy_config.get("pages_build_cmd") or DEPLOY_DEFAULTS["pages_build_cmd"],
            "docker_image": deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"],
            "deploy_path": deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"],
            "service_name": deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"],
            "aws_region": deploy_config.get("aws_region") or DEPLOY_DEFAULTS["aws_region"],
            "s3_bucket": deploy_config.get("s3_bucket") or DEPLOY_DEFAULTS["s3_bucket"],
        }

        if stack_for_target:
            language = stack_for_target["language"]
            version = stack_for_target.get("version") or DEFAULT_VERSIONS.get(language, "latest")
            package_manager = stack_for_target.get("package_manager", "")
            values["version"] = version
            values["install_cmd"] = _get_install_cmd(language, package_manager)
            values["cache_key"] = package_manager if package_manager in ("npm", "yarn", "pnpm") else "npm"

        filled_steps = _replace_placeholders(raw_template, values)
        job_name = f"deploy-{target}"
        job_blocks.append(_build_job_block(job_name, filled_steps, needs=needs))

    return job_blocks


def generate_workflow(stacks, jobs=None, triggers=None, deploy=None, workflow_name="CI"):
    """
    Genere le contenu complet d'un fichier GitHub Actions.

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        triggers (dict): configuration des declencheurs.
        deploy (dict|None): configuration du deploiement, ex:
            {
                "targets": ["docker_hub", "ssh"],
                "docker_image": "monusername/monapp",
                "deploy_path": "/var/www/monapp",
                "service_name": "monapp",
            }
        workflow_name (str): nom affiche du workflow dans GitHub Actions.

    Returns:
        str: contenu YAML complet, pret a etre ecrit dans .github/workflows/ci.yml
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]

    stack_job_blocks, test_job_names, build_job_names = _build_stack_jobs(stacks, jobs)
    deploy_job_blocks = _build_deploy_jobs(deploy, stacks, test_job_names, build_job_names)

    all_job_blocks = stack_job_blocks + deploy_job_blocks

    if not all_job_blocks:
        raise ValueError(
            "Aucun job genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des templates existants."
        )

    triggers_block = _build_triggers_block(triggers)
    jobs_section = "\n\n".join(all_job_blocks)

    workflow = (
        f"name: {workflow_name}\n\n"
        f"{triggers_block}\n\n"
        f"jobs:\n"
        f"{jobs_section}\n"
    )

    return workflow


def write_workflow(stacks, output_path, jobs=None, triggers=None, deploy=None, workflow_name="CI"):
    """Genere le workflow et l'ecrit directement dans un fichier."""
    content = generate_workflow(
        stacks, jobs=jobs, triggers=triggers, deploy=deploy, workflow_name=workflow_name
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(repo_slug, branch="main", workflow_filename="ci.yml", workflow_name="CI"):
    """
    Genere un snippet Markdown de badge de statut, a coller dans le
    README du projet.

    Args:
        repo_slug (str): "utilisateur/repo" (ex: "octocat/hello-world")
        branch (str): branche a suivre pour le badge
        workflow_filename (str): nom du fichier .yml dans .github/workflows/
        workflow_name (str): nom affiche au survol du badge

    Returns:
        str: snippet Markdown pret a coller
    """
    repo_slug = repo_slug.strip().strip("/")
    badge_url = f"https://github.com/{repo_slug}/actions/workflows/{workflow_filename}/badge.svg?branch={branch}"
    link_url = f"https://github.com/{repo_slug}/actions/workflows/{workflow_filename}"
    return f"[![{workflow_name}]({badge_url})]({link_url})"
