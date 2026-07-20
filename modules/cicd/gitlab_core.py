"""
gitlab_core.py
--------------
Assemble un fichier .gitlab-ci.yml complet, sur le meme principe que
core.py (qui genere pour GitHub Actions), mais adapte au format GitLab CI.

Difference cle avec GitHub Actions : GitLab CI execute les jobs d'un
meme "stage" en parallele, mais attend qu'un stage soit termine avant
de passer au suivant. Du coup, l'ordre lint -> test -> build -> deploy
est obtenu simplement en placant chaque job dans le bon stage, SANS
avoir besoin d'un equivalent explicite a "needs:" comme sur GitHub
Actions (meme si GitLab supporte aussi needs: pour paralleliser
davantage, on ne s'en sert pas ici pour rester simple et lisible).

Usage basique :
    from generator.gitlab_core import generate_gitlab_ci

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["lint", "test", "build"])
"""

import os

# --------------------------------------------------------------------------
# Images Docker officielles utilisees par langage. {version} est remplace
# dynamiquement par la version detectee/choisie.
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

# --------------------------------------------------------------------------
# Commandes de lint/test/build par langage. Chaque valeur est une LISTE
# de commandes shell (correspond directement a la section 'script:').
# L'install_cmd est insere automatiquement en premiere position quand
# necessaire (pas la peine de le repeter partout).
# --------------------------------------------------------------------------
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

STAGE_ORDER = ["lint", "test", "build", "deploy"]

# Nom de la variable CI utilisee pour les matrix builds (parallel:matrix:)
MATRIX_VAR_NAMES = {
    "python": "PYTHON_VERSION",
    "node": "NODE_VERSION",
    "go": "GO_VERSION",
    "rust": "RUST_VERSION",
    "java": "JAVA_VERSION",
    "php": "PHP_VERSION",
    "ruby": "RUBY_VERSION",
    "dotnet": "DOTNET_VERSION",
}

# --------------------------------------------------------------------------
# Cibles de deploiement GitLab.
# "gitlab_pages" utilise le mecanisme natif de GitLab Pages : un job
# nomme EXACTEMENT "pages" qui publie un dossier "public/".
# --------------------------------------------------------------------------
DEPLOY_TARGETS = {
    "gitlab_pages": {"requires_language": "node", "label": "GitLab Pages"},
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


def _yaml_script_block(commands):
    """Formate une liste de commandes shell en section YAML 'script:'."""
    lines = "\n".join(f"    - {cmd}" for cmd in commands)
    return f"  script:\n{lines}\n"


def _build_stack_jobs(stacks, jobs):
    """
    Construit les jobs lint/test/build pour chaque stack.
    Retourne (job_blocks, used_stages, build_or_test_job_names) ou
    build_or_test_job_names sert a determiner les dependances du deploiement.
    """
    job_blocks = []
    used_stages = set()
    last_job_names = []  # dernier job "utile" (build sinon test) par stack

    for stack in stacks:
        language = stack["language"]
        version = stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
        package_manager = stack.get("package_manager", "")
        install_cmd = _get_install_cmd(language, package_manager)
        image = _image_for(language, version)
        matrix_versions = stack.get("matrix_versions") or []

        stack_last_job = None

        for job_type in ("lint", "test", "build"):
            if job_type not in jobs:
                continue

            commands_map = COMMANDS_BY_JOB[job_type].get(language)
            if commands_map is None:
                continue

            # Les jobs test/build ont besoin des dependances installees
            # d'abord ; le lint peut parfois s'en passer mais on l'inclut
            # aussi pour eviter les faux positifs d'imports manquants.
            full_commands = [install_cmd] + commands_map if job_type != "lint" else commands_map

            job_name = f"{job_type}-{language}"
            used_stages.add(job_type)

            # Matrix build : uniquement pour 'test', et seulement si
            # plusieurs versions sont demandees pour cette stack.
            parallel_block = ""
            job_image = image
            if job_type == "test" and len(matrix_versions) > 1:
                var_name = MATRIX_VAR_NAMES.get(language, "VERSION")
                versions_yaml = ", ".join(f'"{v}"' for v in matrix_versions)
                parallel_block = f"  parallel:\n    matrix:\n      - {var_name}: [{versions_yaml}]\n"
                job_image = _image_for(language, f"${var_name}")

            block = (
                f"{job_name}:\n"
                f"  stage: {job_type}\n"
                f"  image: {job_image}\n"
                f"{parallel_block}"
                f"{_yaml_script_block(full_commands)}"
            )
            job_blocks.append(block)
            stack_last_job = job_name

        if stack_last_job:
            last_job_names.append(stack_last_job)

    return job_blocks, used_stages, last_job_names


def _build_deploy_jobs(deploy_config, stacks):
    """Construit les jobs de deploiement demandes (stage 'deploy')."""
    if not deploy_config or not deploy_config.get("targets"):
        return [], set()

    targets = deploy_config["targets"]
    job_blocks = []
    used_stages = set()

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

        used_stages.add("deploy")

        if target == "gitlab_pages":
            language = stack_for_target["language"]
            version = stack_for_target.get("version") or DEFAULT_VERSIONS.get(language, "latest")
            package_manager = stack_for_target.get("package_manager", "")
            install_cmd = _get_install_cmd(language, package_manager)
            image = _image_for(language, version)
            build_cmd = deploy_config.get("pages_build_cmd") or DEPLOY_DEFAULTS["pages_build_cmd"]
            pages_dir = deploy_config.get("pages_dir") or DEPLOY_DEFAULTS["pages_dir"]

            block = (
                "pages:\n"
                "  stage: deploy\n"
                f"  image: {image}\n"
                f"{_yaml_script_block([install_cmd, build_cmd, f'rm -rf public && mv {pages_dir} public'])}"
                "  artifacts:\n"
                "    paths:\n"
                "      - public\n"
                "  rules:\n"
                "    - if: '$CI_COMMIT_BRANCH == \"main\"'\n"
            )
            job_blocks.append(block)
            continue

        if target == "docker_hub":
            docker_image = deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"]
            script_lines = [
                'docker login -u $DOCKERHUB_USERNAME -p $DOCKERHUB_TOKEN',
                'docker build -t ' + docker_image + ':latest .',
                'docker push ' + docker_image + ':latest',
            ]
            block = (
                "deploy-docker_hub:\n"
                "  stage: deploy\n"
                "  image: docker:24\n"
                "  services:\n"
                "    - docker:24-dind\n"
                f"{_yaml_script_block(script_lines)}"
            )
            job_blocks.append(block)
            continue

        if target == "ssh":
            deploy_path = deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"]
            service_name = deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"]
            script_lines = [
                'apk add --no-cache openssh-client rsync',
                'eval $(ssh-agent -s)',
                'echo \"$SSH_PRIVATE_KEY\" | tr -d \'\\r\' | ssh-add -',
                'mkdir -p ~/.ssh && chmod 700 ~/.ssh',
                'ssh-keyscan -H $SSH_HOST >> ~/.ssh/known_hosts',
                'rsync -avzr --delete ./ $SSH_USER@$SSH_HOST:' + deploy_path,
                'ssh $SSH_USER@$SSH_HOST "sudo systemctl restart ' + service_name + '"',
            ]
            block = (
                "deploy-ssh:\n"
                "  stage: deploy\n"
                "  image: alpine:latest\n"
                f"{_yaml_script_block(script_lines)}"
            )
            job_blocks.append(block)
            continue

        if target == "vercel":
            script_lines = [
                'npm install -g vercel',
                'vercel --token $VERCEL_TOKEN --prod --yes',
            ]
            block = (
                "deploy-vercel:\n"
                "  stage: deploy\n"
                "  image: node:20-slim\n"
                f"{_yaml_script_block(script_lines)}"
            )
            job_blocks.append(block)
            continue

        if target == "aws_s3":
            language = stack_for_target["language"]
            version = stack_for_target.get("version") or DEFAULT_VERSIONS.get(language, "latest")
            package_manager = stack_for_target.get("package_manager", "")
            install_cmd = _get_install_cmd(language, package_manager)
            image = _image_for(language, version)
            build_cmd = deploy_config.get("pages_build_cmd") or DEPLOY_DEFAULTS["pages_build_cmd"]
            pages_dir = deploy_config.get("pages_dir") or DEPLOY_DEFAULTS["pages_dir"]
            s3_bucket = deploy_config.get("s3_bucket") or DEPLOY_DEFAULTS["s3_bucket"]

            script_lines = [
                install_cmd,
                build_cmd,
                'apt-get update -qq && apt-get install -y -qq awscli',
                f'aws s3 sync {pages_dir} s3://{s3_bucket} --delete',
            ]
            block = (
                "deploy-aws_s3:\n"
                "  stage: deploy\n"
                f"  image: {image}\n"
                f"{_yaml_script_block(script_lines)}"
            )
            job_blocks.append(block)
            continue

    return job_blocks, used_stages


def generate_gitlab_ci(stacks, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """
    Genere le contenu complet d'un fichier .gitlab-ci.yml.

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        deploy (dict|None): meme structure que pour generate_workflow
            (core.py), avec des cibles adaptees a GitLab :
            targets parmi ["gitlab_pages", "docker_hub", "ssh", "vercel", "aws_s3"].
        branches (list[str]|None): non utilise directement (GitLab
            declenche sur toutes les branches par defaut ; le filtrage
            se fait via les 'rules:' des jobs de deploiement).
        schedule_cron (str|None): si fourni, ajoute un commentaire
            explicatif en tete de fichier — GitLab ne permet PAS de
            definir un pipeline planifie directement en YAML (contrairement
            a GitHub Actions), il faut le faire via Settings > CI/CD >
            Schedules dans l'interface GitLab, avec cette expression cron.

    Returns:
        str: contenu YAML complet, pret a etre ecrit dans .gitlab-ci.yml
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]

    stack_blocks, stack_stages, _ = _build_stack_jobs(stacks, jobs)
    deploy_blocks, deploy_stages = _build_deploy_jobs(deploy, stacks)

    all_blocks = stack_blocks + deploy_blocks
    if not all_blocks:
        raise ValueError(
            "Aucun job genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des combinaisons prises en charge."
        )

    used_stages = stack_stages | deploy_stages
    stages_list = [s for s in STAGE_ORDER if s in used_stages]
    stages_yaml = "\n".join(f"  - {s}" for s in stages_list)

    header_comment = ""
    if schedule_cron:
        header_comment = (
            "# NOTE : GitLab ne permet pas de definir un declenchement planifie\n"
            "# directement dans ce fichier (contrairement a GitHub Actions).\n"
            f"# Pour executer ce pipeline selon le planning '{schedule_cron}',\n"
            "# configure-le manuellement dans GitLab :\n"
            "# Settings > CI/CD > Schedules > New schedule\n\n"
        )

    content = (
        f"{header_comment}"
        "stages:\n"
        f"{stages_yaml}\n\n"
        + "\n\n".join(all_blocks)
        + "\n"
    )

    return content


def write_gitlab_ci(stacks, output_path, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """Genere le fichier .gitlab-ci.yml et l'ecrit directement sur disque."""
    content = generate_gitlab_ci(
        stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(project_slug, branch="main", gitlab_host="gitlab.com"):
    """
    Genere un snippet Markdown de badge de statut de pipeline GitLab,
    a coller dans le README du projet.

    Args:
        project_slug (str): "namespace/projet" (ex: "moi/mon-projet")
        branch (str): branche a suivre pour le badge
        gitlab_host (str): domaine GitLab (gitlab.com, ou une instance auto-hebergee)

    Returns:
        str: snippet Markdown pret a coller
    """
    project_slug = project_slug.strip().strip("/")
    badge_url = f"https://{gitlab_host}/{project_slug}/badges/{branch}/pipeline.svg"
    link_url = f"https://{gitlab_host}/{project_slug}/-/commits/{branch}"
    return f"[![pipeline status]({badge_url})]({link_url})"
