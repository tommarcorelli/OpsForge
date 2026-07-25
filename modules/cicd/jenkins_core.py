"""
jenkins_core.py
----------------
Assemble un `Jenkinsfile` complet (pipeline declaratif Groovy), sur le meme
principe que core.py (GitHub Actions), gitlab_core.py (GitLab CI) et
circleci_core.py (CircleCI), adapte a la syntaxe Jenkins.

Difference cle : Jenkins n'a pas de notion de conteneur "par job" comme les
trois autres CI. On utilise `agent none` au niveau du pipeline, puis un
`agent { docker { image '...' } }` par `stage`, ce qui permet de melanger
plusieurs langages/images dans un seul Jenkinsfile (une stage = un job).
Les dependances sont implicites : les stages s'executent dans l'ordre de
declaration (contrairement a GitHub/GitLab/CircleCI qui paralleisent par
defaut et necessitent des dependances explicites).

Usage basique :
    from modules.cicd.jenkins_core import generate_jenkinsfile

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    jenkinsfile_text = generate_jenkinsfile(stacks, jobs=["lint", "test", "build"])
"""

import os

# --------------------------------------------------------------------------
# Images Docker officielles utilisees par langage (agent docker par stage).
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

STAGE_LABELS = {"lint": "Lint", "test": "Test", "build": "Build"}

# --------------------------------------------------------------------------
# Cibles de deploiement Jenkins. Pas de "pages" natif (contrairement a
# GitHub/GitLab Pages) : identifiants geres via le Jenkins Credentials Store
# (credentials()) plutot que des secrets de plateforme.
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


def _groovy_sh_lines(commands, indent="                "):
    """Formate une liste de commandes shell en appels sh '...' Groovy."""
    lignes = []
    for cmd in commands:
        echappe = cmd.replace("\\", "\\\\").replace("'", "\\'")
        lignes.append(f"{indent}sh '{echappe}'")
    return "\n".join(lignes)


def _build_stage(stage_name, image, commands):
    return (
        f"        stage('{stage_name}') {{\n"
        "            agent {\n"
        "                docker { image '" + image + "' }\n"
        "            }\n"
        "            steps {\n"
        f"{_groovy_sh_lines(commands)}\n"
        "            }\n"
        "        }"
    )


def _build_stack_stages(stacks, jobs):
    """Construit les stages lint/test/build pour chaque stack, dans l'ordre."""
    stage_blocks = []
    last_stage_names = []

    for stack in stacks:
        language = stack["language"]
        version = stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
        package_manager = stack.get("package_manager", "")
        install_cmd = _get_install_cmd(language, package_manager)
        image = _image_for(language, version)

        stack_last_stage = None

        for job_type in ("lint", "test", "build"):
            if job_type not in jobs:
                continue

            commands_map = COMMANDS_BY_JOB[job_type].get(language)
            if commands_map is None:
                continue

            full_commands = [install_cmd] + commands_map if job_type != "lint" else commands_map
            stage_name = f"{STAGE_LABELS[job_type]} - {language}"

            stage_blocks.append(_build_stage(stage_name, image, full_commands))
            stack_last_stage = stage_name

        if stack_last_stage:
            last_stage_names.append(stack_last_stage)

    return stage_blocks, last_stage_names


def _build_deploy_stages(deploy_config, stacks, branches):
    """Construit les stages de deploiement demandes, filtrees sur la
    premiere branche declenchante via `when { branch '...' }`."""
    if not deploy_config or not deploy_config.get("targets"):
        return []

    targets = deploy_config["targets"]
    branch_filter = branches[0] if branches else "main"
    stage_blocks = []

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

        when_block = f"            when {{ branch '{branch_filter}' }}\n"

        if target == "docker_hub":
            docker_image = deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"]
            block = (
                "        stage('Deploy Docker Hub') {\n"
                "            agent any\n"
                f"{when_block}"
                "            environment {\n"
                "                DOCKERHUB_CREDS = credentials('dockerhub-credentials')\n"
                "            }\n"
                "            steps {\n"
                "                sh 'echo $DOCKERHUB_CREDS_PSW | docker login -u $DOCKERHUB_CREDS_USR --password-stdin'\n"
                f"                sh 'docker build -t {docker_image}:latest .'\n"
                f"                sh 'docker push {docker_image}:latest'\n"
                "            }\n"
                "        }"
            )

        elif target == "ssh":
            deploy_path = deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"]
            service_name = deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"]
            block = (
                "        stage('Deploy SSH') {\n"
                "            agent any\n"
                f"{when_block}"
                "            steps {\n"
                "                sshagent(credentials: ['ssh-deploy-credentials']) {\n"
                "                    sh 'ssh-keyscan -H $SSH_HOST >> ~/.ssh/known_hosts'\n"
                f"                    sh 'rsync -avzr --delete ./ $SSH_USER@$SSH_HOST:{deploy_path}'\n"
                f"                    sh 'ssh $SSH_USER@$SSH_HOST \"sudo systemctl restart {service_name}\"'\n"
                "                }\n"
                "            }\n"
                "        }"
            )

        elif target == "vercel":
            block = (
                "        stage('Deploy Vercel') {\n"
                "            agent { docker { image 'node:20-slim' } }\n"
                f"{when_block}"
                "            environment {\n"
                "                VERCEL_TOKEN = credentials('vercel-token')\n"
                "            }\n"
                "            steps {\n"
                "                sh 'npm install -g vercel'\n"
                "                sh 'vercel --token $VERCEL_TOKEN --prod --yes'\n"
                "            }\n"
                "        }"
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
                "        stage('Deploy AWS S3') {\n"
                "            agent {\n"
                "                docker { image '" + image + "' }\n"
                "            }\n"
                f"{when_block}"
                "            environment {\n"
                "                AWS_CREDS = credentials('aws-s3-credentials')\n"
                "            }\n"
                "            steps {\n"
                f"                sh '{install_cmd}'\n"
                f"                sh '{build_cmd}'\n"
                "                sh 'apt-get update -qq && apt-get install -y -qq awscli'\n"
                f"                sh 'aws s3 sync {pages_dir} s3://{s3_bucket} --delete'\n"
                "            }\n"
                "        }"
            )

        else:
            continue

        stage_blocks.append(block)

    return stage_blocks


def generate_jenkinsfile(stacks, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """
    Genere le contenu complet d'un `Jenkinsfile` (pipeline declaratif).

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        deploy (dict|None): meme structure que pour generate_workflow (core.py),
            targets parmi ["docker_hub", "ssh", "vercel", "aws_s3"].
        branches (list[str]|None): utilisee pour filtrer les stages de
            deploiement (`when { branch '...' }`) — necessite un pipeline
            multibranche ou le plugin Git renseignant BRANCH_NAME.
        schedule_cron (str|None): si fourni, ajoute un declencheur
            `triggers { cron(...) }` (syntaxe cron Jenkins, compatible
            cron standard).

    Returns:
        str: contenu du Jenkinsfile, pret a etre commite a la racine du depot.
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]
    branches = branches or ["main"]

    stack_blocks, last_stage_names = _build_stack_stages(stacks, jobs)
    deploy_blocks = _build_deploy_stages(deploy, stacks, branches)

    all_blocks = stack_blocks + deploy_blocks
    if not all_blocks:
        raise ValueError(
            "Aucun stage genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des combinaisons prises en charge."
        )

    stages_section = "\n\n".join(all_blocks)

    triggers_block = ""
    if schedule_cron:
        triggers_block = (
            "\n\n    triggers {\n"
            f"        cron('{schedule_cron}')\n"
            "    }"
        )

    content = (
        "pipeline {\n"
        "    agent none\n\n"
        "    stages {\n"
        f"{stages_section}\n"
        "    }"
        f"{triggers_block}\n"
        "}\n"
    )

    return content


def write_jenkinsfile(stacks, output_path, jobs=None, deploy=None, branches=None, schedule_cron=None):
    """Genere le Jenkinsfile et l'ecrit directement sur disque."""
    content = generate_jenkinsfile(
        stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(jenkins_url, job_name, branch="main"):
    """
    Genere un snippet Markdown de badge de statut Jenkins (plugin
    Embeddable Build Status), a coller dans le README du projet.

    Args:
        jenkins_url (str): URL de base du serveur Jenkins (ex: "https://ci.example.com")
        job_name (str): nom du job/pipeline Jenkins (ou chemin "dossier/job" pour
            un Folder, ou "job/branche" pour un pipeline multibranche)
        branch (str): branche affichee dans le lien (informative uniquement,
            Jenkins n'a pas de parametre d'URL standard pour filtrer par branche
            sur un job simple ; utile surtout pour les pipelines multibranches
            ou job_name inclut deja la branche)

    Returns:
        str: snippet Markdown pret a coller
    """
    jenkins_url = jenkins_url.strip().rstrip("/")
    job_name = job_name.strip().strip("/")
    job_path = "/job/".join(job_name.split("/"))
    badge_url = f"{jenkins_url}/job/{job_path}/badge/icon"
    link_url = f"{jenkins_url}/job/{job_path}/"
    return f"[![Jenkins]({badge_url})]({link_url})"
