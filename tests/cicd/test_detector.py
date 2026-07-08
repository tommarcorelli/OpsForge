"""
test_detector.py
-----------------
Tests unitaires pour generator/detector.py.

Lancer avec : pytest tests/test_detector.py -v
"""

import pytest

from modules.cicd.detector import detect_stack


def test_no_stack_detected_on_empty_folder(tmp_path):
    """Un dossier vide ne doit detecter aucune stack."""
    result = detect_stack(str(tmp_path))
    assert result == []


def test_invalid_path_raises_value_error():
    """Un chemin qui n'existe pas doit lever une ValueError explicite."""
    with pytest.raises(ValueError):
        detect_stack("/chemin/qui/nexiste/vraiment/pas")


def test_detect_ruby_gemfile(tmp_path):
    (tmp_path / "Gemfile").write_text('ruby "3.2.1"\ngem "rails"\n')
    result = detect_stack(str(tmp_path))
    ruby = [s for s in result if s["language"] == "ruby"]
    assert ruby and ruby[0]["package_manager"] == "bundler"
    assert ruby[0]["version"] == "3.2"


def test_detect_dotnet_csproj_glob(tmp_path):
    # Detection par glob : un fichier *.csproj (nom arbitraire)
    (tmp_path / "MonApp.csproj").write_text(
        "<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>"
    )
    result = detect_stack(str(tmp_path))
    dn = [s for s in result if s["language"] == "dotnet"]
    assert dn and dn[0]["package_manager"] == "dotnet"
    assert dn[0]["version"] == "8.0"


def test_detect_python_pip(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask==3.0\n")
    result = detect_stack(str(tmp_path))
    assert len(result) == 1
    assert result[0]["language"] == "python"
    assert result[0]["package_manager"] == "pip"


def test_detect_python_poetry(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "test"\n\n'
        '[tool.poetry.dependencies]\npython = "^3.11"\n'
    )
    result = detect_stack(str(tmp_path))
    assert result[0]["package_manager"] == "poetry"
    assert result[0]["version"] == "3.11"


def test_detect_python_version_file(tmp_path):
    (tmp_path / "requirements.txt").write_text("")
    (tmp_path / ".python-version").write_text("3.10.4\n")
    result = detect_stack(str(tmp_path))
    assert result[0]["version"] == "3.10"


def test_detect_node_npm(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "test"}')
    (tmp_path / "package-lock.json").write_text("{}")
    result = detect_stack(str(tmp_path))
    assert result[0]["language"] == "node"
    assert result[0]["package_manager"] == "npm"


def test_detect_node_yarn_with_engines(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name": "test", "engines": {"node": ">=18.0.0"}}'
    )
    (tmp_path / "yarn.lock").write_text("")
    result = detect_stack(str(tmp_path))
    assert result[0]["package_manager"] == "yarn"
    assert result[0]["version"] == "18"


def test_detect_node_nvmrc(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "test"}')
    (tmp_path / ".nvmrc").write_text("20.9.0\n")
    result = detect_stack(str(tmp_path))
    assert result[0]["version"] == "20"


def test_detect_go_version_from_gomod(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
    result = detect_stack(str(tmp_path))
    assert result[0]["language"] == "go"
    assert result[0]["version"] == "1.21"


def test_detect_rust_toolchain_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\n')
    (tmp_path / "rust-toolchain.toml").write_text(
        '[toolchain]\nchannel = "1.75.0"\n'
    )
    result = detect_stack(str(tmp_path))
    assert result[0]["language"] == "rust"
    assert result[0]["version"] == "1.75.0"


def test_detect_rust_default_stable(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\n')
    result = detect_stack(str(tmp_path))
    assert result[0]["version"] == "stable"


def test_detect_java_maven_version(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project><properties>"
        "<maven.compiler.release>21</maven.compiler.release>"
        "</properties></project>"
    )
    result = detect_stack(str(tmp_path))
    assert result[0]["language"] == "java"
    assert result[0]["package_manager"] == "maven"
    assert result[0]["version"] == "21"


def test_detect_java_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text("sourceCompatibility = '17'\n")
    result = detect_stack(str(tmp_path))
    assert result[0]["package_manager"] == "gradle"
    assert result[0]["version"] == "17"


def test_detect_php_composer_constraint(tmp_path):
    (tmp_path / "composer.json").write_text('{"require": {"php": "^8.2"}}')
    result = detect_stack(str(tmp_path))
    assert result[0]["language"] == "php"
    assert result[0]["version"] == "8.2"


def test_detect_multiple_stacks_in_same_project(tmp_path):
    """Un projet full-stack (ex: backend Python + frontend Node) doit
    detecter les deux stacks."""
    (tmp_path / "requirements.txt").write_text("")
    (tmp_path / "package.json").write_text('{"name": "front"}')
    result = detect_stack(str(tmp_path))
    languages = {s["language"] for s in result}
    assert languages == {"python", "node"}
