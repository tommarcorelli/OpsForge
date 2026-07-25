"""
circleci_core.py
-----------------
Assemble un fichier .circleci/config.yml complet, sur le meme principe que
core.py (GitHub Actions) et gitlab_core.py (GitLab CI), adapte au format
CircleCI (config version 2.1).

Difference cle avec GitHub Actions/GitLab CI : CircleCI n'a ni "stages"
(GitLab) ni ordre implicite par job (GitHub) : TOUS les jobs sont declares
dans `jobs:`, puis assembles explicitement dans `workflows:` avec des
`requires:` pour exprimer les dependances. Le parallelisme est donc total
par defaut, sauf ou on ajoute un `requires:`.

Usage basique :
    from modules.cicd.circleci_core import generate_circleci_config

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["lint", "test", "build"])
"""

import os

# --------------------------------------------------------------------------
# Images Docker officielles "convenience" CircleCI (cimg/*) utilisees par
# langage. {version} est remplace dynamiquement par la version detectee/choisie.
# --------------------------------------------------------------------------
LANG_IMAGES = {
    "python": "cimg/python:{version}",
    "node": "cimg/node:{version}",
    "go": "cimg/go:{version}",
    "rust": "cimg/rust:{version}",
    "java": "cimg/openjdk:{version}",
    "php": "cimg/php:{version}",
    "ruby": "cimg/ruby:{version}",
    "dotnet": "mcr.microsoft.com/dotnet/sdk:{version}",
}

DEFAULT_VERSIONS = {
    "python": "3.12",
    "node": "20.11",
    "go": "1.22",
    "rust": "1.75",
    "java": "17.0",
    "php": "8.3",
    "ruby": "3.3",
    "dotnet": "8.0",
}

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
    "go": {"go modules": "go mod download"},
    "rust": {"cargo": "cargo fetch"},
    "java": {
        "maven": "mvn install -DskipTests",
        "gradle": "./gradlew build -x test",
    },
    "php": {"composer": "composer install --no-interaction"},
    "ruby": {"bundler": "bundle install"},
    "dotnet": {"dotnet": "dotnet restore"},
}

LINT_COMMANDS = {
    "python": ["pip install flake8", "flake8 . --max-line-length=100 --extend-exclude=.venv"],
    "node": ["npm run lint --if-present"],
    "go": ["go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest", "golangci-lint run"],
    "rust": ["rustup component add clippy", "cargo clippy --all-targets --all-features -- -D warnings"],
    "java": ["echo 'Lint minimal : ajoute checkstyle ou spotbugs a ton pom.xml/build.gradle pour aller plus loin'"],
    "php": ["find . -name '*.php' -not -path './vendor/*' -exec php -l {} \\;"],
    "ruby": ["gem install rubocop", "rubocop"],
    "dotnet": ["dotnet format --verify-no-changes"],
}

TEST_COMMANDS = {
    "python": ["pip install pytest", "pytest --maxfail=1 --disable-warnings -q"],
    "node": ["npm test --if-present"],
    "go": ["go test ./... -v"],
    "rust": ["cargo test --all-features"],
    "java": ["mvn test"],
    "php": ["vendor/bin/phpunit"],
    "ruby": ["bundle exec rspec || bundle exec rake test"],
    "dotnet": ["dotnet test --verbosity normal"],
}

BUILD_COMMANDS = {
    "python": ["pip install build", "python -m build"],
    "node": ["npm run build --if-present"],
    "go": ["go build -v ./..."],
    "rust": ["cargo build --release"],
    "java": ["mvn package -DskipTests"],
    "php": ["composer install --no-interaction --no-dev --optimize-autoloader"],
    "ruby": ["gem build *.gemspec"],
    "dotnet": ["dotnet build --configuration Release"],
}

COMMANDS_BY_JOB = {"lint": LINT_COMMANDS, "test": TEST_COMMANDS, "build": BUILD_COMMANDS}

# --------------------------------------------------------------------------
# Cibles de deploiement CircleCI. Pas d'equivalent "pages" natif (contrairement
# a GitHub/GitLab Pages) : le plus proche est un deploiement S3 (aws_s3).
# --------------------------------------------------------------------------
DEPLOY_TARGETS = {
    "docker_hub": {"requires_language": None, "label": "Docker Hub"},
    "ssh": {"requires_language": None, "label": "Serveur via SSH"},
    "vercel": {"requires_language": None, "label": "Vercel"},
    "aws_s3": {"requires_language": "node", "label": "AWS S3"},
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


def _get_install_cmd(language, package_manager):
    lang_commands = INSTALL_COMMANDS.get(language, {})
    if package_manager in lang_commands:
        return lang_commands[package_manager]
    if lang_commands:
        return next(iter(lang_commands.values()))
    return "echo 'Aucune commande d-installation definie pour ce langage'"


def _image_for(language, version):
    template = LANG_IMAGES.get(language, "{version}")
    return template.replace("{version}", str(version))


def _yaml_steps_block(commands):
    """Formate une liste de commandes shell en section YAML 'steps:' (avec checkout)."""
    lines = ["    steps:", "      - checkout"]
    for cmd in commands:
        echappe = cmd.replace('"', '\\"')
        lines.append(f'      - run: "{echappe}"')
    return "\n".join(lines) + "\n"


def _build_stack_jobs(stacks, jobs):
    """
    Construit les jobs lint/test/build pour chaque stack.

    Returns:
        (job_blocks, job_names_by_type, last_job_names)
        - job_blocks: liste de blocs YAML (a placer sous 'jobs:')
        - job_names_by_type: {job_name: (job_type, requires_matrix, param_name)}
          utilise pour construire la section workflows correspondante
        - last_job_names: dernier job "utile" (build sinon test) par stack,
          utilise pour les dependances de deploiement
    """
    job_blocks = []
    workflow_entries = []  # (job_name, requires:list[str]|None, matrix_versions:list|None, param_name:str|None)
    last_job_names = []

    for stack in stacks:
        language = stack["language"]
        version = stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
        package_manager = stack.get("package_manager", "")
        install_cmd = _get_install_cmd(language, package_manager)
        matrix_versions = stack.get("matrix_versions") or []

        created_jobs = {}  # job_type -> job_name

        for job_type in ("lint", "test", "build"):
            if job_type not in jobs:
                continue

            commands_map = COMMANDS_BY_JOB[job_type].get(language)
            if commands_map is None:
                continue

            full_commands = [install_cmd] + commands_map if job_type != "lint" else commands_map
            job_name = f"{job_type}-{language}"

            use_matrix = job_type == "test" and len(matrix_versions) > 1
            param_name = None
            if use_matrix:
                param_name = "version"
                image = _image_for(language, "<< parameters.version >>")
                params_block = (
                    "    parameters:\n"
                    "      version:\n"
                    "        type: string\n"
                )
            else:
                image = _image_for(language, version)
                params_block = ""

            block = (
                f"  {job_name}:\n"
                f"{params_block}"
                "    docker:\n"
                f"      - image: {image}\n"
                f"{_yaml_steps_block(full_commands)}"
            )
            job_blocks.append(block)
            created_jobs[job_type] = job_name

            requires = None
            if job_type == "build" and "test" in created_jobs:
                requires = [created_jobs["test"]]

            workflow_entries.append((job_name, requires, matrix_versions if use_matrix else None, param_name))

        if "build" in created_jobs:
            last_job_names.append(created_jobs["build"])
        elif "test" in created_jobs:
            last_job_names.append(created_jobs["test"])

    return job_blocks, workflow_entries, last_job_names


def _build_deploy_jobs(deploy_config, stacks, last_job_names):
    """Construit les jobs de deploiement demandes."""
    if not deploy_config or not deploy_config.get("targets"):
        return [], []

    targets = deploy_config["targets"]
    job_blocks = []
    workflow_entries = []
    requires = last_job_names or None

    for target in targets:
        target_info = DEPLOY_TARGETS.get(target)
        if target_info is None:
            continue

        required_lang = target_info["requires_language"]
        stack_for_target = None
        if required_lang:
            stack_for_target = next((s for s in stacks if s["language"] == required_lang), None)
            if stack_for_target is None:
                continue  # cible ignoree silencieusement, pas de stack compatible

        job_name = f"deploy-{target}"

        if target == "docker_hub":
            docker_image = deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"]
            commands = [
                "docker login -u $DOCKERHUB_USERNAME -p $DOCKERHUB_TOKEN",
                f"docker build -t {docker_image}:latest .",
                f"docker push {docker_image}:latest",
            ]
            block = (
                f"  {job_name}:\n"
                "    docker:\n"
                "      - image: cimg/base:current\n"
                "    steps:\n"
                "      - checkout\n"
                "      - setup_remote_docker\n"
                + "".join(f'      - run: "{c}"\n' for c in commands)
            )

        elif target == "ssh":
            deploy_path = deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"]
            service_name = deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"]
            commands = [
                "add_ssh_keys",
                "rsync -avzr --delete ./ $SSH_USER@$SSH_HOST:" + deploy_path,
                'ssh $SSH_USER@$SSH_HOST "sudo systemctl restart ' + service_name + '"',
            ]
            block = (
                f"  {job_name}:\n"
                "    docker:\n"
                "      - image: cimg/base:current\n"
                "    steps:\n"
                "      - checkout\n"
                "      - add_ssh_keys\n"
                '      - run: "ssh-keyscan -H $SSH_HOST >> ~/.ssh/known_hosts"\n'
                f'      - run: "rsync -avzr --delete ./ $SSH_USER@$SSH_HOST:{deploy_path}"\n'
                f'      - run: "ssh $SSH_USER@$SSH_HOST \\"sudo systemctl restart {service_name}\\""\n'
            )

        elif target == "vercel":
            block = (
                f"  {job_name}:\n"
                "    docker:\n"
                "      - image: cimg/node:20.11\n"
                "    steps:\n"
                "      - checkout\n"
                '      - run: "npm install -g vercel"\n'
                '      - run: "vercel --token $VERCEL_TOKEN --prod --yes"\n'
            )

        elif target == "aws_s3":
            language = stack_for_target["language"]
            version = stack_for_target.get("version") or DEFAULT_VERSIONS.get(language, "latest")
            package_manager = stack_for_target.get("package_manager", "")
            install_cmd = _get_install_cmd(language, package_manager)
            image = _image_for(language, version)
            build_cmd = deploy_config.get("pages_build_cmd") or DEPLOY_DEFAULTS["pages_build_cmd"]
            pages_dir = deploy_config.get("pages_dir") or DEPLOY_DEFAULTS["pages_dir"]
            s3_bucket = deploy_config.get("s3_bucket") or DEPLOY_DEFAULTS["s3_bucket"]
            block = (
                f"  {job_name}:\n"
                f"    docker:\n"
                f"      - image: {image}\n"
                "    steps:\n"
                "      - checkout\n"
                f'      - run: "{install_cmd}"\n'
                f'      - run: "{build_cmd}"\n'
                '      - run: "sudo apt-get update -qq && sudo apt-get install -y -qq awscli"\n'
                f'      - run: "aws s3 sync {pages_dir} s3://{s3_bucket} --delete"\n'
            )

        else:
            continue

        job_blocks.append(block)
        workflow_entries.append((job_name, requires, None, None))

    return job_blocks, workflow_entries


def _render_workflow_job(job_name, requires, matrix_versions, param_name, branch_filter=None):
    """Rend l'entree d'un job dans la section 'workflows:'."""
    needs_requires = bool(requires)
    needs_matrix = bool(matrix_versions)
    needs_filter = bool(branch_filter)

    if not needs_requires and not needs_matrix and not needs_filter:
        return f"      - {job_name}"

    lines = [f"      - {job_name}:"]
    if needs_requires:
        req_yaml = ", ".join(requires)
        lines.append(f"          requires: [{req_yaml}]")
    if needs_matrix:
        versions_yaml = ", ".join(f'"{v}"' for v in matrix_versions)
        lines.append("          matrix:")
        lines.append("            parameters:")
        lines.append(f"              {param_name}: [{versions_yaml}]")
    if needs_filter:
        lines.append("          filters:")
        lines.append("            branches:")
        lines.append(f"              only: {branch_filter}")
    return "\n".join(lines)


def generate_circleci_config(stacks, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """
    Genere le contenu complet d'un fichier .circleci/config.yml.

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        deploy (dict|None): meme structure que pour generate_workflow (core.py),
            targets parmi ["docker_hub", "ssh", "vercel", "aws_s3"].
        branches (list[str]|None): branches sur lesquelles le deploiement
            est autorise (le workflow principal se declenche lui sur toutes
            les branches par defaut, CircleCI ne filtrant pas 'on: push' comme
            GitHub Actions ; le filtrage se fait au niveau des jobs de deploiement).
        schedule_cron (str|None): si fourni, ajoute un second workflow
            declenche par un `schedule:` (cron CircleCI natif), qui rejoue
            les memes jobs sur la branche principale.

    Returns:
        str: contenu YAML complet, pret a etre ecrit dans .circleci/config.yml
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]
    branches = branches or ["main"]

    stack_blocks, stack_entries, last_job_names = _build_stack_jobs(stacks, jobs)
    deploy_blocks, deploy_entries = _build_deploy_jobs(deploy, stacks, last_job_names)

    all_blocks = stack_blocks + deploy_blocks
    if not all_blocks:
        raise ValueError(
            "Aucun job genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des combinaisons prises en charge."
        )

    jobs_section = "jobs:\n" + "\n\n".join(all_blocks)

    branch_filter = branches[0] if len(branches) == 1 else None
    workflow_jobs_lines = []
    for job_name, requires, matrix, param in stack_entries:
        workflow_jobs_lines.append(_render_workflow_job(job_name, requires, matrix, param))
    for job_name, requires, matrix, param in deploy_entries:
        workflow_jobs_lines.append(_render_workflow_job(job_name, requires, matrix, param, branch_filter=branch_filter))

    workflows_section = (
        "workflows:\n"
        "  build-and-test:\n"
        "    jobs:\n" + "\n".join(workflow_jobs_lines) + "\n"
    )

    if schedule_cron:
        nightly_jobs_lines = [
            _render_workflow_job(job_name, requires, matrix, param)
            for (job_name, requires, matrix, param) in stack_entries
        ]
        only_branch = branches[0]
        workflows_section += (
            "\n  nightly:\n"
            "    triggers:\n"
            "      - schedule:\n"
            f'          cron: "{_cron_to_circleci(schedule_cron)}"\n'
            "          filters:\n"
            "            branches:\n"
            f"              only:\n                - {only_branch}\n"
            "    jobs:\n" + "\n".join(nightly_jobs_lines) + "\n"
        )

    content = (
        "version: 2.1\n\n"
        f"{jobs_section}\n\n"
        f"{workflows_section}"
    )

    return content


def _cron_to_circleci(schedule_cron):
    """CircleCI utilise une syntaxe cron standard (5 champs), identique a
    celle deja utilisee par GitHub Actions/GitLab : passe-plat direct."""
    return schedule_cron


def write_circleci_config(stacks, output_path, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """Genere le fichier .circleci/config.yml et l'ecrit directement sur disque."""
    content = generate_circleci_config(
        stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(project_slug, branch="main", vcs="gh"):
    """
    Genere un snippet Markdown de badge de statut de pipeline CircleCI,
    a coller dans le README du projet.

    Args:
        project_slug (str): "organisation/projet" (ex: "moi/mon-projet")
        branch (str): branche a suivre pour le badge
        vcs (str): plateforme de code source ("gh" pour GitHub, "bb" pour Bitbucket)

    Returns:
        str: snippet Markdown pret a coller
    """
    project_slug = project_slug.strip().strip("/")
    badge_url = f"https://dl.circleci.com/status-badge/img/{vcs}/{project_slug}/tree/{branch}.svg?style=svg"
    link_url = f"https://dl.circleci.com/status-badge/redirect/{vcs}/{project_slug}/tree/{branch}"
    return f"[![CircleCI]({badge_url})]({link_url})"
