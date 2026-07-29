"""
bitbucket_core.py
------------------
Assemble un fichier `bitbucket-pipelines.yml` complet, sur le meme principe
que core.py (GitHub Actions), gitlab_core.py (GitLab CI), circleci_core.py
(CircleCI), jenkins_core.py (Jenkins) et drone_core.py (Drone), adapte au
format Bitbucket Pipelines.

Difference cle : les `step:` d'un meme pipeline Bitbucket s'executent en
SERIE par defaut (comme Drone), dans l'ordre de declaration. Les steps de
deploiement sont places sous `pipelines.branches.<branche>` plutot que sous
`pipelines.default`, pour ne se declencher QUE sur la branche filtree (pas
d'equivalent direct a `when.branch` step-par-step comme sur Drone).

Identifiants geres via les "Repository variables" Bitbucket (Settings >
Pipelines > Repository variables), marquees "Secured" pour les secrets,
plutot que des identifiants en dur.

Usage basique :
    from modules.cicd.bitbucket_core import generate_bitbucket_pipelines

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["lint", "test", "build"])
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
# Cibles de deploiement Bitbucket. Pas de "pages" natif (contrairement a
# GitHub/GitLab Pages).
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


def _yaml_script_block(commands, key_indent="        "):
    lines = "\n".join(f"{key_indent}  - {cmd}" for cmd in commands)
    return f"{key_indent}script:\n{lines}\n"


def _build_step(step_name, image, commands, extra_lines=""):
    return (
        "    - step:\n"
        f"        name: {step_name}\n"
        f"        image: {image}\n"
        f"{extra_lines}"
        f"{_yaml_script_block(commands)}"
    )


def _build_stack_steps(stacks, jobs):
    """Construit les steps lint/test/build pour chaque stack, dans l'ordre
    (execution sequentielle par defaut dans une meme liste de steps)."""
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
            step_blocks.append(_build_step(step_name, image, full_commands))

    return step_blocks


def _build_deploy_steps(deploy_config, stacks):
    """Construit les steps de deploiement demandes (destines a la section
    'branches' du pipeline, filtres par branche)."""
    if not deploy_config or not deploy_config.get("targets"):
        return []

    targets = deploy_config["targets"]
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

        if target == "docker_hub":
            docker_image = deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"]
            commands = [
                "echo $DOCKERHUB_PASSWORD | docker login -u $DOCKERHUB_USERNAME --password-stdin",
                f"docker build -t {docker_image}:latest .",
                f"docker push {docker_image}:latest",
            ]
            block = _build_step(
                "deploy-docker_hub", "atlassian/default-image:4", commands,
                extra_lines="        services:\n          - docker\n",
            )
            # NOTE : "services:" est deja au meme niveau d'indentation que
            # "name:"/"image:" (8 espaces), donc bien un frere dans le meme
            # mapping "step:" — pas une cle separee au niveau de la liste.

        elif target == "ssh":
            deploy_path = deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"]
            service_name = deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"]
            commands = [
                "apt-get update -qq && apt-get install -y -qq openssh-client rsync",
                "eval $(ssh-agent -s)",
                "echo \"$SSH_PRIVATE_KEY\" | tr -d '\\r' | ssh-add -",
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh",
                "ssh-keyscan -H $SSH_HOST >> ~/.ssh/known_hosts",
                f"rsync -avzr --delete ./ $SSH_USER@$SSH_HOST:{deploy_path}",
                f'ssh $SSH_USER@$SSH_HOST "sudo systemctl restart {service_name}"',
            ]
            block = _build_step("deploy-ssh", "atlassian/default-image:4", commands)

        elif target == "vercel":
            commands = [
                "npm install -g vercel",
                "vercel --token $VERCEL_TOKEN --prod --yes",
            ]
            block = _build_step("deploy-vercel", "node:20-slim", commands)

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
            commands = [
                install_cmd,
                build_cmd,
                "pip install awscli",
                f"aws s3 sync {pages_dir} s3://{s3_bucket} --delete --region {aws_region}",
            ]
            block = _build_step("deploy-aws_s3", image, commands)

        else:
            continue

        step_blocks.append(block)

    return step_blocks


def generate_bitbucket_pipelines(stacks, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """
    Genere le contenu complet d'un fichier `bitbucket-pipelines.yml`.

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        deploy (dict|None): meme structure que pour generate_workflow (core.py),
            targets parmi ["docker_hub", "ssh", "vercel", "aws_s3"].
        branches (list[str]|None): branches sur lesquelles les steps de
            deploiement sont declenches (`pipelines.branches.<branche>`).
            Les steps lint/test/build restent dans `pipelines.default`
            (declenches sur TOUTES les branches, comportement natif
            Bitbucket sans configuration de `pipelines.branches` dediee).
        schedule_cron (str|None): si fourni, ajoute un commentaire
            explicatif en tete de fichier — Bitbucket ne permet PAS de
            definir un declenchement planifie directement dans ce fichier,
            il faut le faire via Repository Settings > Pipelines >
            Schedules dans l'interface.

    Returns:
        str: contenu YAML complet, pret a etre ecrit a la racine du depot
            sous le nom `bitbucket-pipelines.yml`.
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]
    branches = branches or ["main"]

    stack_blocks = _build_stack_steps(stacks, jobs)
    deploy_blocks = _build_deploy_steps(deploy, stacks)

    if not stack_blocks and not deploy_blocks:
        raise ValueError(
            "Aucun step genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des combinaisons prises en charge."
        )

    default_language = stacks[0]["language"]
    default_version = stacks[0].get("version") or DEFAULT_VERSIONS.get(default_language, "latest")
    default_image = _image_for(default_language, default_version)

    header_comment = ""
    if schedule_cron:
        header_comment = (
            "# NOTE : Bitbucket ne permet pas de definir un declenchement planifie\n"
            "# directement dans ce fichier (contrairement a GitHub Actions).\n"
            f"# Pour executer ce pipeline selon le planning '{schedule_cron}',\n"
            "# configure-le manuellement : Repository Settings > Pipelines > Schedules.\n\n"
        )

    lines = [
        f"{header_comment}image: {default_image}\n\npipelines:\n"
    ]

    if stack_blocks:
        lines.append("  default:\n" + "\n".join(stack_blocks) + "\n")

    if deploy_blocks:
        branch_name = branches[0]
        lines.append(
            "  branches:\n"
            f"    {branch_name}:\n"
            + "\n".join(stack_blocks + deploy_blocks) + "\n"
        )

    content = "\n".join(lines)
    return content


def write_bitbucket_pipelines(stacks, output_path, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """Genere le fichier bitbucket-pipelines.yml et l'ecrit directement sur disque."""
    content = generate_bitbucket_pipelines(
        stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(workspace, repo_slug, branch="main"):
    """
    Genere un snippet Markdown de badge de statut Bitbucket Pipelines,
    a coller dans le README du projet.

    Args:
        workspace (str): workspace Bitbucket (ex: "monequipe")
        repo_slug (str): nom du depot (ex: "mon-projet")
        branch (str): branche a suivre pour le badge

    Returns:
        str: snippet Markdown pret a coller
    """
    workspace = workspace.strip().strip("/")
    repo_slug = repo_slug.strip().strip("/")
    badge_url = f"https://img.shields.io/bitbucket/pipelines/{workspace}/{repo_slug}/{branch}"
    link_url = f"https://bitbucket.org/{workspace}/{repo_slug}/addon/pipelines/home#!/results/branch/{branch}/page/1"
    return f"[![Build Status]({badge_url})]({link_url})"
