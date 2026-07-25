"""
drone_core.py
--------------
Assemble un fichier `.drone.yml` complet, sur le meme principe que core.py
(GitHub Actions), gitlab_core.py (GitLab CI), circleci_core.py (CircleCI)
et jenkins_core.py (Jenkins), adapte au format Drone CI.

Difference cle : les `steps:` d'une pipeline Drone s'executent en SERIE par
defaut (contrairement a GitHub/GitLab/CircleCI qui paralleisent par
defaut), sauf si on ajoute `depends_on:` pour construire un DAG parallele.
On garde volontairement l'execution sequentielle par defaut ici : plus
simple, toujours correcte, et l'ordre lint -> test -> build -> deploy est
obtenu gratuitement sans avoir a declarer de dependances.

Les cibles de deploiement s'appuient sur des plugins officiels Drone quand
ils existent (plugins/docker, plugins/s3), et sur des secrets Drone
(`from_secret:`, configures via `drone secret add` ou l'UI) plutot que des
identifiants en dur.

Usage basique :
    from modules.cicd.drone_core import generate_drone_yaml

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["lint", "test", "build"])
"""

import os

# --------------------------------------------------------------------------
# Images Docker officielles utilisees par langage.
# --------------------------------------------------------------------------
LANG_IMAGES = {
    "python": "python:{version}-slim",
    "node": "node:{version}-slim",
    "go": "golang:{version}",
    "rust": "rust:{version}",
    "java": "eclipse-temurin:{version}-jdk",
    "php": "php:{version}-cli",
    "ruby": "ruby:{version}",
    "dotnet": "mcr.microsoft.com/dotnet/sdk:{version}",
}

DEFAULT_VERSIONS = {
    "python": "3.12",
    "node": "20",
    "go": "1.22",
    "rust": "1.75",
    "java": "17",
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
# Cibles de deploiement Drone. Pas de "pages" natif : le plus proche est
# un deploiement S3 (aws_s3, via le plugin officiel plugins/s3).
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


def _yaml_commands_block(commands, indent="      "):
    lines = "\n".join(f"{indent}- {cmd}" for cmd in commands)
    return f"{indent[:-2]}commands:\n{lines}\n"


def _build_stack_steps(stacks, jobs):
    """Construit les steps lint/test/build pour chaque stack, dans l'ordre
    (execution sequentielle par defaut, cf. docstring du module)."""
    step_blocks = []

    for stack in stacks:
        language = stack["language"]
        version = stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
        package_manager = stack.get("package_manager", "")
        install_cmd = _get_install_cmd(language, package_manager)
        image = _image_for(language, version)

        for job_type in ("lint", "test", "build"):
            if job_type not in jobs:
                continue

            commands_map = COMMANDS_BY_JOB[job_type].get(language)
            if commands_map is None:
                continue

            full_commands = [install_cmd] + commands_map if job_type != "lint" else commands_map
            step_name = f"{job_type}-{language}"

            block = (
                f"  - name: {step_name}\n"
                f"    image: {image}\n"
                f"{_yaml_commands_block(full_commands)}"
            )
            step_blocks.append(block)

    return step_blocks


def _build_deploy_steps(deploy_config, stacks, branches):
    """Construit les steps de deploiement demandes, filtres sur la
    premiere branche declenchante via `when.branch`."""
    if not deploy_config or not deploy_config.get("targets"):
        return []

    targets = deploy_config["targets"]
    branch_filter = branches[0] if branches else "main"
    step_blocks = []

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

        when_block = (
            "    when:\n"
            "      branch:\n"
            f"        - {branch_filter}\n"
        )

        if target == "docker_hub":
            docker_image = deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"]
            repo, _, tag = docker_image.partition(":")
            tag = tag or "latest"
            block = (
                "  - name: deploy-docker_hub\n"
                "    image: plugins/docker\n"
                "    settings:\n"
                f"      repo: {repo}\n"
                f"      tags: {tag}\n"
                "      username:\n"
                "        from_secret: docker_username\n"
                "      password:\n"
                "        from_secret: docker_password\n"
                f"{when_block}"
            )

        elif target == "ssh":
            deploy_path = deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"]
            service_name = deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"]
            block = (
                "  - name: deploy-ssh\n"
                "    image: appleboy/drone-ssh\n"
                "    settings:\n"
                "      host:\n"
                "        from_secret: ssh_host\n"
                "      username:\n"
                "        from_secret: ssh_user\n"
                "      key:\n"
                "        from_secret: ssh_private_key\n"
                "      script:\n"
                f"        - rsync -avzr --delete ./ $(username)@$(host):{deploy_path}\n"
                f"        - sudo systemctl restart {service_name}\n"
                f"{when_block}"
            )

        elif target == "vercel":
            block = (
                "  - name: deploy-vercel\n"
                "    image: node:20-slim\n"
                "    environment:\n"
                "      VERCEL_TOKEN:\n"
                "        from_secret: vercel_token\n"
                "    commands:\n"
                "      - npm install -g vercel\n"
                "      - vercel --token $VERCEL_TOKEN --prod --yes\n"
                f"{when_block}"
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
            aws_region = deploy_config.get("aws_region") or DEPLOY_DEFAULTS["aws_region"]
            block = (
                "  - name: build-for-s3\n"
                f"    image: {image}\n"
                "    commands:\n"
                f"      - {install_cmd}\n"
                f"      - {build_cmd}\n\n"
                "  - name: deploy-aws_s3\n"
                "    image: plugins/s3-sync\n"
                "    settings:\n"
                f"      bucket: {s3_bucket}\n"
                f"      region: {aws_region}\n"
                f"      source: {pages_dir}\n"
                "      target: /\n"
                "      delete: true\n"
                "      access_key:\n"
                "        from_secret: aws_access_key_id\n"
                "      secret_key:\n"
                "        from_secret: aws_secret_access_key\n"
                f"{when_block}"
            )

        else:
            continue

        step_blocks.append(block)

    return step_blocks


def generate_drone_yaml(stacks, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """
    Genere le contenu complet d'un fichier `.drone.yml`.

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        deploy (dict|None): meme structure que pour generate_workflow (core.py),
            targets parmi ["docker_hub", "ssh", "vercel", "aws_s3"].
        branches (list[str]|None): branches declenchant la pipeline
            (`trigger.branch`) ET filtrant les steps de deploiement.
        schedule_cron (str|None): si fourni, ajoute un commentaire
            explicatif en tete de fichier — Drone ne permet PAS de definir
            un declenchement planifie directement en YAML (contrairement a
            GitHub Actions), il faut creer un cron job separe via
            `drone cron add` (CLI) ou l'UI, qui declenche cette meme
            pipeline avec l'evenement `cron`.

    Returns:
        str: contenu YAML complet, pret a etre ecrit dans .drone.yml
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]
    branches = branches or ["main"]

    stack_blocks = _build_stack_steps(stacks, jobs)
    deploy_blocks = _build_deploy_steps(deploy, stacks, branches)

    all_blocks = stack_blocks + deploy_blocks
    if not all_blocks:
        raise ValueError(
            "Aucun step genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des combinaisons prises en charge."
        )

    steps_section = "\n\n".join(all_blocks)
    branches_yaml = "\n".join(f"    - {b}" for b in branches)

    header_comment = ""
    if schedule_cron:
        header_comment = (
            "# NOTE : Drone ne permet pas de definir un declenchement planifie\n"
            "# directement dans ce fichier (contrairement a GitHub Actions).\n"
            f"# Pour executer cette pipeline selon le planning '{schedule_cron}',\n"
            "# cree un cron job Drone qui declenche cette meme pipeline :\n"
            "#   drone cron add <repo> nightly main --branch=main\n"
            "# (voir aussi la commande 'drone cron update --schedule' et l'UI Drone)\n\n"
        )

    content = (
        f"{header_comment}"
        "kind: pipeline\n"
        "type: docker\n"
        "name: default\n\n"
        "steps:\n"
        f"{steps_section}\n\n"
        "trigger:\n"
        "  branch:\n"
        f"{branches_yaml}\n"
        "  event:\n"
        "    - push\n"
        "    - pull_request\n"
    )

    return content


def write_drone_yaml(stacks, output_path, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """Genere le fichier .drone.yml et l'ecrit directement sur disque."""
    content = generate_drone_yaml(
        stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(repo_slug, branch="main", drone_url="https://cloud.drone.io"):
    """
    Genere un snippet Markdown de badge de statut Drone, a coller dans le
    README du projet.

    Args:
        repo_slug (str): "organisation/projet" (ex: "moi/mon-projet")
        branch (str): branche a suivre pour le badge
        drone_url (str): URL de base de l'instance Drone (cloud.drone.io
            par defaut, ou l'URL de ton instance auto-hebergee)

    Returns:
        str: snippet Markdown pret a coller
    """
    repo_slug = repo_slug.strip().strip("/")
    drone_url = drone_url.strip().rstrip("/")
    badge_url = f"{drone_url}/api/badges/{repo_slug}/status.svg?branch={branch}"
    link_url = f"{drone_url}/{repo_slug}?branch={branch}"
    return f"[![Build Status]({badge_url})]({link_url})"
