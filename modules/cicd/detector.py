"""
detector.py
-----------
Detecte automatiquement le(s) stack(s) technique(s) present(s)
dans un dossier de projet, en se basant sur la presence de
fichiers "signature" (ex: package.json -> Node.js).

Usage basique :
    from generator.detector import detect_stack
    result = detect_stack("/chemin/vers/mon/projet")
    # result -> [{"language": "python", "package_manager": "poetry", ...}, ...]
"""

import os
import glob
import json
import re


# --------------------------------------------------------------------------
# Signatures de fichiers par langage.
# Chaque entree = fichier(s) a chercher a la racine du projet
# et le package manager associe si trouve.
# --------------------------------------------------------------------------
SIGNATURES = {
    "python": {
        "files": ["pyproject.toml", "requirements.txt", "Pipfile", "setup.py"],
        "package_managers": {
            "pyproject.toml": "poetry",
            "Pipfile": "pipenv",
            "requirements.txt": "pip",
            "setup.py": "pip",
        },
    },
    "node": {
        "files": ["package.json"],
        "package_managers": {
            "pnpm-lock.yaml": "pnpm",
            "yarn.lock": "yarn",
            "package-lock.json": "npm",
        },
    },
    "go": {
        "files": ["go.mod"],
        "package_managers": {
            "go.mod": "go modules",
        },
    },
    "rust": {
        "files": ["Cargo.toml"],
        "package_managers": {
            "Cargo.toml": "cargo",
        },
    },
    "java": {
        "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "package_managers": {
            "pom.xml": "maven",
            "build.gradle": "gradle",
            "build.gradle.kts": "gradle",
        },
    },
    "php": {
        "files": ["composer.json"],
        "package_managers": {
            "composer.json": "composer",
        },
    },
    "ruby": {
        "files": ["Gemfile", "*.gemspec"],
        "package_managers": {
            "Gemfile": "bundler",
        },
    },
    "dotnet": {
        "files": ["*.sln", "*.csproj", "*.fsproj"],
        "package_managers": {
            "*.sln": "dotnet",
            "*.csproj": "dotnet",
            "*.fsproj": "dotnet",
        },
    },
}


def _read_json_safe(path):
    """Lit un fichier JSON, retourne un dict vide en cas d'erreur."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _detect_node_version(project_path, package_json):
    """
    Essaie de deduire la version de Node a utiliser :
    1. champ 'engines.node' dans package.json
    2. fichier .nvmrc
    3. valeur par defaut : LTS actuelle
    """
    engines = package_json.get("engines", {})
    if "node" in engines:
        match = re.search(r"\d+", engines["node"])
        if match:
            return match.group(0)

    nvmrc_path = os.path.join(project_path, ".nvmrc")
    if os.path.isfile(nvmrc_path):
        with open(nvmrc_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            match = re.search(r"\d+", content)
            if match:
                return match.group(0)

    return "20"  # LTS par defaut


def _detect_python_version(project_path):
    """
    Essaie de deduire la version de Python a utiliser :
    1. fichier .python-version
    2. champ 'python' dans pyproject.toml (recherche simple, sans parser TOML complet)
    3. valeur par defaut
    """
    version_file = os.path.join(project_path, ".python-version")
    if os.path.isfile(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            match = re.search(r"\d+\.\d+", content)
            if match:
                return match.group(0)

    pyproject_path = os.path.join(project_path, "pyproject.toml")
    if os.path.isfile(pyproject_path):
        with open(pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r'python\s*=\s*"[\^~]?(\d+\.\d+)', content)
            if match:
                return match.group(1)

    return "3.12"  # valeur par defaut


def _detect_go_version(project_path):
    """
    Essaie de deduire la version de Go a utiliser :
    1. directive 'go X.Y' dans go.mod
    2. fichier .go-version
    3. valeur par defaut
    """
    go_mod_path = os.path.join(project_path, "go.mod")
    if os.path.isfile(go_mod_path):
        with open(go_mod_path, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r"^go\s+(\d+\.\d+)", content, re.MULTILINE)
            if match:
                return match.group(1)

    version_file = os.path.join(project_path, ".go-version")
    if os.path.isfile(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            match = re.search(r"\d+\.\d+", content)
            if match:
                return match.group(0)

    return "1.22"  # valeur par defaut


def _detect_rust_version(project_path):
    """
    Essaie de deduire la version/toolchain Rust a utiliser :
    1. fichier rust-toolchain.toml (champ 'channel')
    2. fichier rust-toolchain (format legacy, une seule ligne)
    3. valeur par defaut : 'stable'
    """
    toml_path = os.path.join(project_path, "rust-toolchain.toml")
    if os.path.isfile(toml_path):
        with open(toml_path, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r'channel\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)

    legacy_path = os.path.join(project_path, "rust-toolchain")
    if os.path.isfile(legacy_path):
        with open(legacy_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content

    return "stable"  # valeur par defaut


def _detect_java_version(project_path):
    """
    Essaie de deduire la version de Java a utiliser :
    1. fichier .java-version (convention jenv)
    2. balise <maven.compiler.release> ou <java.version> dans pom.xml
    3. 'sourceCompatibility' dans build.gradle / build.gradle.kts
    4. valeur par defaut
    """
    version_file = os.path.join(project_path, ".java-version")
    if os.path.isfile(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            match = re.search(r"\d+", content)
            if match:
                return match.group(0)

    pom_path = os.path.join(project_path, "pom.xml")
    if os.path.isfile(pom_path):
        with open(pom_path, "r", encoding="utf-8") as f:
            content = f.read()
            for tag in ("maven.compiler.release", "maven.compiler.source", "java.version"):
                match = re.search(rf"<{tag}>\s*(\d+)\s*</{tag}>", content)
                if match:
                    return match.group(1)

    for gradle_file in ("build.gradle", "build.gradle.kts"):
        gradle_path = os.path.join(project_path, gradle_file)
        if os.path.isfile(gradle_path):
            with open(gradle_path, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r"sourceCompatibility\s*=?\s*['\"]?(\d+)", content)
                if match:
                    return match.group(1)

    return "17"  # valeur par defaut


def _detect_php_version(project_path):
    """
    Essaie de deduire la version de PHP a utiliser :
    1. fichier .php-version
    2. contrainte 'require.php' dans composer.json
    3. valeur par defaut
    """
    version_file = os.path.join(project_path, ".php-version")
    if os.path.isfile(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            match = re.search(r"\d+\.\d+", content)
            if match:
                return match.group(0)

    composer_json = _read_json_safe(os.path.join(project_path, "composer.json"))
    php_constraint = composer_json.get("require", {}).get("php", "")
    if php_constraint:
        match = re.search(r"\d+\.\d+", php_constraint)
        if match:
            return match.group(0)

    return "8.3"  # valeur par defaut


def _detect_ruby_version(project_path):
    """
    Essaie de deduire la version de Ruby :
    1. fichier .ruby-version
    2. directive 'ruby "x.y"' dans le Gemfile
    3. valeur par defaut
    """
    version_file = os.path.join(project_path, ".ruby-version")
    if os.path.isfile(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            match = re.search(r"\d+\.\d+", f.read())
            if match:
                return match.group(0)

    gemfile = os.path.join(project_path, "Gemfile")
    if os.path.isfile(gemfile):
        with open(gemfile, "r", encoding="utf-8") as f:
            match = re.search(r"ruby\s+['\"](\d+\.\d+)", f.read())
            if match:
                return match.group(1)

    return "3.3"  # valeur par defaut


def _detect_dotnet_version(project_path):
    """
    Essaie de deduire la version du SDK .NET :
    1. champ 'sdk.version' dans global.json
    2. TargetFramework (netX.Y) dans le premier .csproj/.fsproj
    3. valeur par defaut
    """
    global_json = _read_json_safe(os.path.join(project_path, "global.json"))
    sdk_version = global_json.get("sdk", {}).get("version", "")
    if sdk_version:
        match = re.search(r"\d+\.\d+", sdk_version)
        if match:
            return match.group(0)

    for proj in glob.glob(os.path.join(project_path, "*.csproj")) + glob.glob(os.path.join(project_path, "*.fsproj")):
        with open(proj, "r", encoding="utf-8") as f:
            match = re.search(r"<TargetFramework>net(\d+\.\d+)", f.read())
            if match:
                return match.group(1)

    return "8.0"  # LTS actuelle


def _find_package_manager(project_path, managers_map, default_file):
    """
    Parcourt les fichiers presents dans le dossier pour determiner
    quel package manager est utilise, en se basant sur les fichiers
    de lock ou de config specifiques.
    """
    for filename, manager in managers_map.items():
        if os.path.isfile(os.path.join(project_path, filename)):
            return manager
    return managers_map.get(default_file, "inconnu")


def detect_stack(project_path):
    """
    Analyse le dossier fourni et retourne la liste des stacks detectees.

    Retourne une liste de dicts, ex :
    [
        {
            "language": "python",
            "package_manager": "poetry",
            "version": "3.12",
        },
        {
            "language": "node",
            "package_manager": "npm",
            "version": "20",
        },
    ]

    Un projet peut avoir plusieurs stacks (ex: backend Python + front Node).
    """
    if not os.path.isdir(project_path):
        raise ValueError(f"Le chemin '{project_path}' n'est pas un dossier valide.")

    detected = []

    for language, config in SIGNATURES.items():
        signature_files = config["files"]
        found_file = None

        for filename in signature_files:
            target = os.path.join(project_path, filename)
            matched = glob.glob(target) if "*" in filename else (
                [target] if os.path.isfile(target) else []
            )
            if matched:
                found_file = filename
                break

        if found_file is None:
            continue

        package_manager = _find_package_manager(
            project_path, config["package_managers"], found_file
        )

        if language == "node":
            package_json = _read_json_safe(os.path.join(project_path, "package.json"))
            version = _detect_node_version(project_path, package_json)
        elif language == "python":
            version = _detect_python_version(project_path)
        elif language == "go":
            version = _detect_go_version(project_path)
        elif language == "rust":
            version = _detect_rust_version(project_path)
        elif language == "java":
            version = _detect_java_version(project_path)
        elif language == "php":
            version = _detect_php_version(project_path)
        elif language == "ruby":
            version = _detect_ruby_version(project_path)
        elif language == "dotnet":
            version = _detect_dotnet_version(project_path)
        else:
            version = None

        detected.append({
            "language": language,
            "package_manager": package_manager,
            "version": version,
        })

    return detected


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    stacks = detect_stack(target)

    if not stacks:
        print("Aucun stack detecte dans ce dossier.")
    else:
        print(f"Stack(s) detecte(s) dans '{target}' :")
        for stack in stacks:
            print(f"  - {stack['language']} "
                  f"(package manager: {stack['package_manager']}, "
                  f"version: {stack['version']})")
