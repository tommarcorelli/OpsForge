"""
teamcity_core.py
-----------------
Assemble un fichier `.teamcity/settings.kts` complet (Kotlin DSL), sur le
meme principe que core.py (GitHub Actions), gitlab_core.py (GitLab CI),
circleci_core.py (CircleCI), jenkins_core.py (Jenkins), drone_core.py
(Drone) et bitbucket_core.py (Bitbucket Pipelines), adapte au format
TeamCity.

Difference cle : TeamCity n'a pas de notion de "job" au sein d'un seul
fichier de pipeline. Chaque etape (lint/test/build/deploy) devient un
`BuildType` Kotlin distinct (une classe objet), et les dependances entre
etapes sont explicites via `dependencies { snapshot(AutreBuildType) { } }`
(equivalent au `needs:` de GitHub Actions), plutot qu'un ordre de
declaration implicite (Jenkins/Drone) ou des stages (GitLab/Bitbucket).

Le fichier genere est du Kotlin (compile par TeamCity au chargement du
projet) : les assertions de test portent donc sur la presence de motifs
textuels et l'equilibre des accolades, comme pour jenkins_core.py.

Usage basique :
    from modules.cicd.teamcity_core import generate_teamcity_kotlin_dsl

    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    kts_text = generate_teamcity_kotlin_dsl(stacks, jobs=["lint", "test", "build"])
"""

import os
import re

# --------------------------------------------------------------------------
# Images Docker officielles utilisees par langage (agent Docker par BuildType).
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
# Cibles de deploiement TeamCity. Pas de "pages" natif. Identifiants geres
# via les "Parameters" du projet TeamCity (types "Password", masques dans
# les logs), references en Kotlin par "%nom.du.parametre%".
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


def _pascal_case(*parts):
    """Construit un identifiant Kotlin valide en PascalCase a partir de
    morceaux de texte quelconques (ex: 'lint', 'python' -> 'LintPython')."""
    out = []
    for part in parts:
        cleaned = re.sub(r"[^0-9a-zA-Z]+", " ", str(part))
        out.append("".join(w.capitalize() for w in cleaned.split()))
    return "".join(out)


def _kotlin_script_lines(commands):
    """Formate une liste de commandes shell en bloc scriptContent Kotlin
    (triple-quoted string, trimIndent())."""
    body = "\n".join(f"                {cmd}" for cmd in commands)
    return (
        "            scriptContent = \"\"\"\n"
        f"{body}\n"
        "            \"\"\".trimIndent()"
    )


def _build_type_block(object_name, display_name, image, commands, snapshot_deps=None, branch_filter=None,
                       schedule_fields=None):
    """Construit un objet BuildType Kotlin complet.

    L'execution dans le conteneur voulu passe par le "Docker Wrapper" du
    step script natif (dockerImage/dockerPull), pas par un agent dedie :
    c'est le mecanisme le plus simple et le plus portable cote TeamCity
    (fonctionne sur n'importe quel agent avec Docker installe).
    """
    deps_block = ""
    if snapshot_deps:
        dep_lines = "\n".join(
            f"        snapshot({dep}) {{\n"
            "            onDependencyFailure = FailureAction.FAIL_TO_START\n"
            "        }"
            for dep in snapshot_deps
        )
        deps_block = (
            "\n\n    dependencies {\n"
            f"{dep_lines}\n"
            "    }"
        )

    triggers_block = "\n\n    triggers {\n        vcs {\n"
    if branch_filter:
        triggers_block += f"            branchFilter = \"+:refs/heads/{branch_filter}\"\n"
    triggers_block += "        }"

    if schedule_fields:
        triggers_block += (
            "\n        schedule {\n"
            "            schedulingPolicy = cron {\n"
            f"                seconds = \"{schedule_fields['seconds']}\"\n"
            f"                minutes = \"{schedule_fields['minutes']}\"\n"
            f"                hours = \"{schedule_fields['hours']}\"\n"
            f"                dayOfMonth = \"{schedule_fields['dayOfMonth']}\"\n"
            f"                month = \"{schedule_fields['month']}\"\n"
            f"                dayOfWeek = \"{schedule_fields['dayOfWeek']}\"\n"
            "            }\n"
            "            branchFilter = \"+:refs/heads/*\"\n"
            "        }"
        )

    triggers_block += "\n    }"

    docker_lines = ""
    if image:
        docker_lines = (
            f'\n            dockerImage = "{image}"\n'
            "            dockerPull = true"
        )

    return (
        f'object {object_name} : BuildType({{\n'
        f'    name = "{display_name}"\n\n'
        "    vcs {\n"
        "        root(DslContext.settingsRoot)\n"
        "    }\n\n"
        "    steps {\n"
        "        script {\n"
        f"{_kotlin_script_lines(commands)}"
        f"{docker_lines}\n"
        "        }\n"
        "    }\n"
        f"{triggers_block}"
        f"{deps_block}\n"
        "})"
    )


def _build_stack_build_types(stacks, jobs, schedule_fields=None):
    """Construit les BuildType lint/test/build pour chaque stack. Si
    `schedule_fields` est fourni, il est attache au dernier BuildType
    "utile" (build sinon test sinon lint) de la PREMIERE stack.

    Returns:
        (blocks, object_names, last_object_name_per_stack)
    """
    blocks = []
    object_names = []
    last_names = []

    # Determine a l'avance quel object_name recevra le trigger planifie,
    # pour le construire directement au bon endroit (pas de post-traitement).
    schedule_target = None
    if schedule_fields and stacks:
        first_stack = stacks[0]
        for job_type in ("build", "test", "lint"):
            if job_type in jobs and COMMANDS_BY_JOB[job_type].get(first_stack["language"]) is not None:
                schedule_target = _pascal_case(job_type, first_stack["language"])
                break

    for stack in stacks:
        language = stack["language"]
        version = stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
        package_manager = stack.get("package_manager", "")
        install_cmd = _get_install_cmd(language, package_manager)
        image = _image_for(language, version)

        created = {}

        for job_type in ("lint", "test", "build"):
            if job_type not in jobs:
                continue

            commands_map = COMMANDS_BY_JOB[job_type].get(language)
            if commands_map is None:
                continue

            full_commands = [install_cmd] + commands_map if job_type != "lint" else commands_map
            object_name = _pascal_case(job_type, language)
            display_name = f"{STAGE_LABELS[job_type]} - {language}"

            snapshot_deps = None
            if job_type == "build" and "test" in created:
                snapshot_deps = [created["test"]]

            this_schedule = schedule_fields if object_name == schedule_target else None
            blocks.append(_build_type_block(
                object_name, display_name, image, full_commands,
                snapshot_deps=snapshot_deps, schedule_fields=this_schedule,
            ))
            created[job_type] = object_name
            object_names.append(object_name)

        if created:
            last_names.append(created.get("build") or created.get("test") or created.get("lint"))

    return blocks, object_names, last_names


def _build_deploy_build_types(deploy_config, stacks, upstream_names, branches):
    if not deploy_config or not deploy_config.get("targets"):
        return [], []

    targets = deploy_config["targets"]
    branch_filter = branches[0] if branches else "main"
    blocks = []
    names = []

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

        object_name = _pascal_case("deploy", target)
        display_name = f"Deploy - {target_info['label']}"
        image = None

        if target == "docker_hub":
            docker_image = deploy_config.get("docker_image") or DEPLOY_DEFAULTS["docker_image"]
            commands = [
                "echo %dockerhub.password% | docker login -u %dockerhub.username% --password-stdin",
                f"docker build -t {docker_image}:latest .",
                f"docker push {docker_image}:latest",
            ]

        elif target == "ssh":
            deploy_path = deploy_config.get("deploy_path") or DEPLOY_DEFAULTS["deploy_path"]
            service_name = deploy_config.get("service_name") or DEPLOY_DEFAULTS["service_name"]
            commands = [
                "eval $(ssh-agent -s)",
                'echo "%ssh.private.key%" | tr -d \'\\r\' | ssh-add -',
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh",
                "ssh-keyscan -H %ssh.host% >> ~/.ssh/known_hosts",
                f"rsync -avzr --delete ./ %ssh.user%@%ssh.host%:{deploy_path}",
                f'ssh %ssh.user%@%ssh.host% "sudo systemctl restart {service_name}"',
            ]

        elif target == "vercel":
            image = "node:20-slim"
            commands = [
                "npm install -g vercel",
                "vercel --token %vercel.token% --prod --yes",
            ]

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

        else:
            continue

        blocks.append(
            _build_type_block(
                object_name, display_name, image, commands,
                snapshot_deps=upstream_names or None,
                branch_filter=branch_filter,
            )
        )
        names.append(object_name)

    return blocks, names


def generate_teamcity_kotlin_dsl(stacks, jobs=None, deploy=None, branches=None, schedule_cron=None,
                                  project_name="CI"):
    """
    Genere le contenu complet d'un fichier `.teamcity/settings.kts`.

    Args:
        stacks (list[dict]): stacks detectees ou choisies manuellement.
        jobs (list[str]): jobs a inclure parmi ["lint", "test", "build"].
        deploy (dict|None): meme structure que pour generate_workflow (core.py),
            targets parmi ["docker_hub", "ssh", "vercel", "aws_s3"].
        branches (list[str]|None): utilisee pour filtrer les BuildType de
            deploiement (`triggers.vcs.branchFilter`).
        schedule_cron (str|None): si fourni, ajoute un trigger `schedule {}`
            planifie sur le premier BuildType de test/build (conversion
            best-effort d'un cron standard 5 champs vers les champs
            seconds/minutes/hours/dayOfMonth/month/dayOfWeek de la DSL
            TeamCity — a verifier/ajuster dans l'UI si besoin).
        project_name (str): nom affiche du projet TeamCity.

    Returns:
        str: contenu Kotlin complet, pret a etre commite dans
            `.teamcity/settings.kts` a la racine du depot.
    """
    if not stacks:
        raise ValueError("Aucune stack fournie : impossible de generer un pipeline.")

    jobs = jobs or ["lint", "test", "build"]
    branches = branches or ["main"]

    schedule_fields = _cron_to_teamcity_fields(schedule_cron) if schedule_cron else None

    stack_blocks, stack_object_names, last_names = _build_stack_build_types(stacks, jobs, schedule_fields=schedule_fields)
    deploy_blocks, deploy_object_names = _build_deploy_build_types(deploy, stacks, last_names, branches)

    all_blocks = stack_blocks + deploy_blocks
    all_object_names = stack_object_names + deploy_object_names

    if not all_blocks:
        raise ValueError(
            "Aucun BuildType genere : verifie que les stacks/jobs/cibles de deploiement "
            "demandes correspondent bien a des combinaisons prises en charge."
        )

    build_types_section = "\n\n".join(all_blocks)
    build_type_refs = "\n".join(f"    buildType({name})" for name in all_object_names)

    content = (
        'import jetbrains.buildServer.configs.kotlin.*\n'
        'import jetbrains.buildServer.configs.kotlin.buildSteps.script\n'
        'import jetbrains.buildServer.configs.kotlin.triggers.vcs\n'
        'import jetbrains.buildServer.configs.kotlin.triggers.schedule\n\n'
        'version = "2024.03"\n\n'
        "project {\n"
        f"{build_type_refs}\n"
        "}\n\n"
        f"{build_types_section}\n"
    )

    return content


def _cron_to_teamcity_fields(cron_expr):
    """Convertit une expression cron standard (5 champs : minute heure
    jour-du-mois mois jour-de-semaine) vers les champs Quartz-like attendus
    par le bloc `cron {}` de la DSL Kotlin TeamCity. Retourne None si le
    format ne correspond pas a 5 champs (le trigger planifie est alors omis,
    mais le reste du pipeline reste genere)."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return None

    minute, hour, dom, month, dow = parts

    if dow == "*":
        dow_field = "*"
        dom_field = dom
    else:
        # TeamCity/Quartz : un seul de dayOfMonth/dayOfWeek peut etre
        # specifique, l'autre doit etre "?".
        dow_field = dow
        dom_field = "?"

    return {
        "seconds": "0",
        "minutes": minute,
        "hours": hour,
        "dayOfMonth": dom_field,
        "month": month,
        "dayOfWeek": dow_field,
    }


def write_teamcity_kotlin_dsl(stacks, output_path, jobs=None, deploy=None, branches=None,
                               schedule_cron=None, project_name="CI"):
    """Genere le fichier settings.kts et l'ecrit directement sur disque."""
    content = generate_teamcity_kotlin_dsl(
        stacks, jobs=jobs, deploy=deploy, branches=branches,
        schedule_cron=schedule_cron, project_name=project_name,
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_badge_markdown(teamcity_url, build_type_id):
    """
    Genere un snippet Markdown de badge de statut TeamCity, a coller dans
    le README du projet (necessite le "Guest access" active sur le serveur,
    ou un serveur public comme teamcity.jetbrains.com).

    Args:
        teamcity_url (str): URL de base du serveur TeamCity
            (ex: "https://teamcity.example.com")
        build_type_id (str): identifiant du BuildType/de la configuration
            (ex: "MonProjet_Test")

    Returns:
        str: snippet Markdown pret a coller
    """
    teamcity_url = teamcity_url.strip().rstrip("/")
    build_type_id = build_type_id.strip()
    badge_url = f"{teamcity_url}/app/rest/builds/buildType:(id:{build_type_id})/statusIcon"
    link_url = f"{teamcity_url}/viewType.html?buildTypeId={build_type_id}"
    return f"[![TeamCity]({badge_url})]({link_url})"
