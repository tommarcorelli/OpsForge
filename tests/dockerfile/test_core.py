"""Tests du cœur du module Dockerfile d'OpsForge."""

import pytest

from modules.dockerfile.core import (
    generate_dockerfile,
    generate_dockerignore,
    write_dockerfile,
    write_dockerignore,
    SUPPORTED_LANGUAGES,
    DEFAULT_PORTS,
    DEFAULT_ENTRYPOINTS,
)

PLACEHOLDERS = ["{version}", "{port}", "{entrypoint}", "{workdir}", "{install_cmd}"]


def _stack(language, version=None, package_manager=""):
    return {"language": language, "version": version, "package_manager": package_manager}


# --------------------------------------------------------------------------
# Generation de base : tous les langages supportes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_generation_tous_langages_sans_placeholder_residuel(language):
    dockerfile = generate_dockerfile(_stack(language))
    for placeholder in PLACEHOLDERS:
        assert placeholder not in dockerfile, f"{placeholder} non remplace pour {language}"
    assert dockerfile.startswith("# syntax=docker/dockerfile:1")
    assert "FROM" in dockerfile


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_generation_est_multi_stage(language):
    """Chaque Dockerfile genere doit avoir au moins 2 instructions FROM (multi-stage)."""
    dockerfile = generate_dockerfile(_stack(language))
    assert dockerfile.count("\nFROM ") + dockerfile.count("FROM ") >= 2


def test_langage_non_supporte_leve_value_error():
    with pytest.raises(ValueError):
        generate_dockerfile(_stack("cobol"))


# --------------------------------------------------------------------------
# Options : port, entrypoint, workdir
# --------------------------------------------------------------------------

def test_port_par_defaut_par_langage():
    for lang, expected_port in DEFAULT_PORTS.items():
        dockerfile = generate_dockerfile(_stack(lang))
        assert f"EXPOSE {expected_port}" in dockerfile


def test_port_personnalise_prioritaire_sur_le_defaut():
    dockerfile = generate_dockerfile(_stack("python"), port=9999)
    assert "EXPOSE 9999" in dockerfile
    assert f"EXPOSE {DEFAULT_PORTS['python']}" not in dockerfile


def test_entrypoint_personnalise_python():
    dockerfile = generate_dockerfile(_stack("python"), entrypoint="main.py")
    assert 'CMD ["python", "main.py"]' in dockerfile


def test_entrypoint_par_defaut_node():
    dockerfile = generate_dockerfile(_stack("node"))
    assert f'CMD ["node", "{DEFAULT_ENTRYPOINTS["node"]}"]' in dockerfile


def test_workdir_personnalise_applique_partout():
    dockerfile = generate_dockerfile(_stack("python"), workdir="/srv/app")
    assert "WORKDIR /srv/app" in dockerfile
    assert "WORKDIR /app" not in dockerfile


def test_workdir_par_defaut():
    dockerfile = generate_dockerfile(_stack("python"))
    assert "WORKDIR /app" in dockerfile


# --------------------------------------------------------------------------
# Cas particuliers par langage
# --------------------------------------------------------------------------

def test_java_maven_par_defaut():
    dockerfile = generate_dockerfile(_stack("java", version="17", package_manager="maven"))
    assert "maven:3.9-eclipse-temurin-17" in dockerfile
    assert "target/*.jar" in dockerfile
    assert "ENTRYPOINT" in dockerfile


def test_java_gradle_utilise_le_bon_template():
    dockerfile = generate_dockerfile(_stack("java", version="17", package_manager="gradle"))
    assert "gradle:8-jdk17" in dockerfile
    assert "build/libs/*.jar" in dockerfile
    assert "gradlew" in dockerfile


def test_java_sans_package_manager_retombe_sur_maven():
    dockerfile = generate_dockerfile(_stack("java", version="21"))
    assert "maven:3.9-eclipse-temurin-21" in dockerfile


def test_php_sert_via_apache_port_80():
    dockerfile = generate_dockerfile(_stack("php", version="8.3"))
    assert "php:8.3-apache" in dockerfile
    assert "EXPOSE 80" in dockerfile
    assert "composer" in dockerfile.lower()


def test_python_poetry_configure_le_venv_systeme():
    dockerfile = generate_dockerfile(_stack("python", package_manager="poetry"))
    assert "poetry config virtualenvs.create false" in dockerfile
    assert "poetry install" in dockerfile


def test_python_pipenv_utilise_le_flag_system():
    dockerfile = generate_dockerfile(_stack("python", package_manager="pipenv"))
    assert "pipenv install --deploy --system" in dockerfile


def test_node_pnpm_active_corepack():
    dockerfile = generate_dockerfile(_stack("node", package_manager="pnpm"))
    assert "corepack enable" in dockerfile
    assert "pnpm install" in dockerfile


def test_node_yarn():
    dockerfile = generate_dockerfile(_stack("node", package_manager="yarn"))
    assert "yarn install --frozen-lockfile" in dockerfile


def test_rust_utilise_lentrypoint_comme_nom_de_binaire():
    dockerfile = generate_dockerfile(_stack("rust"), entrypoint="mon_service")
    assert "target/release/mon_service" in dockerfile
    assert 'CMD ["./mon_service"]' in dockerfile


def test_go_binaire_nomme_par_entrypoint():
    dockerfile = generate_dockerfile(_stack("go"), entrypoint="serveur")
    assert "-o /out/serveur" in dockerfile
    assert 'CMD ["./serveur"]' in dockerfile


def test_dotnet_utilise_lentrypoint_comme_nom_de_dll():
    dockerfile = generate_dockerfile(_stack("dotnet"), entrypoint="MonApi.dll")
    assert 'ENTRYPOINT ["dotnet", "MonApi.dll"]' in dockerfile


def test_version_par_defaut_si_absente():
    dockerfile = generate_dockerfile(_stack("python", version=None))
    assert "python:3.12-slim" in dockerfile  # DEFAULT_VERSIONS du module cicd


# --------------------------------------------------------------------------
# .dockerignore
# --------------------------------------------------------------------------

@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_dockerignore_genere_pour_tous_les_langages(language):
    content = generate_dockerignore(language)
    assert "Dockerfile" in content
    assert ".git/" in content


def test_dockerignore_langage_non_supporte():
    with pytest.raises(ValueError):
        generate_dockerignore("cobol")


# --------------------------------------------------------------------------
# Ecriture sur disque
# --------------------------------------------------------------------------

def test_write_dockerfile_cree_le_fichier(tmp_path):
    output = tmp_path / "sub" / "Dockerfile"
    write_dockerfile(_stack("python"), str(output))
    assert output.is_file()
    content = output.read_text(encoding="utf-8")
    assert "FROM python" in content


def test_write_dockerignore_cree_le_fichier(tmp_path):
    output = tmp_path / "sub" / ".dockerignore"
    write_dockerignore("node", str(output))
    assert output.is_file()
    content = output.read_text(encoding="utf-8")
    assert "node_modules" in content
