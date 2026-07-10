"""
core.py
-------
Assemble un Dockerfile multi-stage (et son .dockerignore) a partir
d'une stack detectee (langage, version, package manager) — reutilise
le detecteur du module CI/CD (modules.cicd.detector.detect_stack).

Usage basique :
    from modules.dockerfile.core import generate_dockerfile

    stack = {"language": "python", "version": "3.12", "package_manager": "pip"}
    dockerfile_text = generate_dockerfile(stack)

Avec options :
    dockerfile_text = generate_dockerfile(
        stack, port=8000, entrypoint="app.py", workdir="/app"
    )
"""

import os

from modules.cicd.core import DEFAULT_VERSIONS

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

SUPPORTED_LANGUAGES = ["python", "node", "go", "rust", "java", "php", "ruby", "dotnet"]

# --------------------------------------------------------------------------
# Ports par defaut, par langage (convention la plus courante).
# --------------------------------------------------------------------------
DEFAULT_PORTS = {
    "python": 8000,
    "node": 3000,
    "go": 8080,
    "rust": 8080,
    "java": 8080,
    "php": 80,
    "ruby": 3000,
    "dotnet": 8080,
}

# --------------------------------------------------------------------------
# Point d'entree par defaut, par langage. A adapter au projet reel :
# le champ est expose et modifiable dans le formulaire web / CLI.
# --------------------------------------------------------------------------
DEFAULT_ENTRYPOINTS = {
    "python": "app.py",
    "node": "index.js",
    "go": "app",
    "rust": "app",
    "java": None,  # non utilise : COPY target/*.jar / build/libs/*.jar
    "php": None,   # non utilise : sert via Apache
    "ruby": "app.rb",
    "dotnet": "App.dll",
}

# --------------------------------------------------------------------------
# Commandes d'installation adaptees a un contexte Docker (differentes de
# celles du module CI/CD : pas de venv, installation "systeme" dans l'image).
# --------------------------------------------------------------------------
DOCKER_INSTALL_COMMANDS = {
    "python": {
        "pip": "pip install --no-cache-dir -r requirements.txt",
        "poetry": (
            "pip install --no-cache-dir poetry "
            "&& poetry config virtualenvs.create false "
            "&& poetry install --no-interaction --no-ansi --no-root"
        ),
        "pipenv": "pip install --no-cache-dir pipenv && pipenv install --deploy --system",
    },
    "node": {
        "npm": "npm ci",
        "yarn": "yarn install --frozen-lockfile",
        "pnpm": "corepack enable && pnpm install --frozen-lockfile",
    },
    "ruby": {
        "bundler": "bundle install --without development test",
    },
}

# Template a utiliser par langage. Java a deux variantes selon le
# package manager detecte (maven par defaut).
TEMPLATE_FILES = {
    "python": "python.dockerfile",
    "node": "node.dockerfile",
    "go": "go.dockerfile",
    "rust": "rust.dockerfile",
    "php": "php.dockerfile",
    "ruby": "ruby.dockerfile",
    "dotnet": "dotnet.dockerfile",
}


def _load_template(relative_path):
    """Charge le contenu brut d'un template, ou None si absent."""
    path = os.path.join(TEMPLATES_DIR, relative_path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _replace_placeholders(template_text, values):
    """
    Remplace les placeholders {xxx} par leur valeur, via de simples
    remplacements de sous-chaines (PAS .format()).

    Volontaire : un Dockerfile contient des instructions shell qui
    peuvent elles-memes utiliser des accolades (ex: heredocs, JSON
    inline dans certaines images). .format() les interpreterait a tort
    comme des placeholders et casserait la generation.
    """
    result = template_text
    for key, value in values.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def _get_docker_install_cmd(language, package_manager):
    """Commande d'installation adaptee au contexte Docker, avec repli raisonnable."""
    lang_commands = DOCKER_INSTALL_COMMANDS.get(language, {})
    if package_manager in lang_commands:
        return lang_commands[package_manager]
    if lang_commands:
        return next(iter(lang_commands.values()))
    return "echo 'Aucune commande d-installation definie pour ce langage'"


def _template_filename_for(language, package_manager):
    """Determine quel fichier de template utiliser (cas particulier : Java)."""
    if language == "java":
        return "java_gradle.dockerfile" if package_manager == "gradle" else "java_maven.dockerfile"
    filename = TEMPLATE_FILES.get(language)
    if not filename:
        raise ValueError(
            f"Langage non supporte : '{language}'. "
            f"Langages disponibles : {', '.join(SUPPORTED_LANGUAGES)}."
        )
    return filename


def generate_dockerfile(stack, port=None, entrypoint=None, workdir="/app"):
    """
    Genere le contenu complet d'un Dockerfile multi-stage pour la stack fournie.

    Args:
        stack (dict): {"language": str, "version": str|None, "package_manager": str}
        port (int|None): port expose (defaut : convention du langage)
        entrypoint (str|None): fichier/binaire/DLL de demarrage
            (defaut : convention du langage, non utilise pour java/php)
        workdir (str): dossier de travail dans le conteneur (defaut "/app")

    Returns:
        str: contenu du Dockerfile, pret a etre ecrit dans "Dockerfile"
    """
    language = stack.get("language")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Langage non supporte : '{language}'. "
            f"Langages disponibles : {', '.join(SUPPORTED_LANGUAGES)}."
        )

    package_manager = stack.get("package_manager", "")
    version = stack.get("version") or DEFAULT_VERSIONS.get(language, "latest")
    resolved_port = port or DEFAULT_PORTS.get(language, 8080)
    resolved_entrypoint = entrypoint or DEFAULT_ENTRYPOINTS.get(language) or ""

    template_filename = _template_filename_for(language, package_manager)
    template_text = _load_template(template_filename)
    if template_text is None:
        raise ValueError(f"Template introuvable pour '{language}' ({template_filename}).")

    values = {
        "version": version,
        "port": resolved_port,
        "entrypoint": resolved_entrypoint,
        "workdir": workdir,
        "install_cmd": _get_docker_install_cmd(language, package_manager),
    }

    return _replace_placeholders(template_text, values)


def generate_dockerignore(language):
    """Genere le contenu d'un .dockerignore adapte au langage."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Langage non supporte : '{language}'. "
            f"Langages disponibles : {', '.join(SUPPORTED_LANGUAGES)}."
        )
    content = _load_template(os.path.join("dockerignore", f"{language}.dockerignore"))
    if content is None:
        raise ValueError(f".dockerignore introuvable pour '{language}'.")
    return content


def write_dockerfile(stack, output_path, port=None, entrypoint=None, workdir="/app"):
    """Genere le Dockerfile et l'ecrit directement dans un fichier."""
    content = generate_dockerfile(stack, port=port, entrypoint=entrypoint, workdir=workdir)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def write_dockerignore(language, output_path):
    """Genere le .dockerignore et l'ecrit directement dans un fichier."""
    content = generate_dockerignore(language)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
