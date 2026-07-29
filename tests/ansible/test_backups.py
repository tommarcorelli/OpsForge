"""Tests du role 'backups' (sauvegardes automatiques) et des moteurs de base de donnees."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import yaml

from modules.ansible.core import (
    generate_playbook,
    generate_role_based_project,
    DATABASE_ENGINES,
    PROVISIONING_STEPS,
)


def _base_config(lang="python", **overrides):
    config = {
        "hosts_group": "webservers",
        "provisioning": ["update_system", "base_packages", "runtime"],
        "runtime_language": lang,
        "deployment": ["git_clone", "install_deps", "restart_service"],
        "deployment_language": lang,
        "repo_url": "git@github.com:x/y.git",
        "app_dir": "/opt/x",
        "service_name": "x",
    }
    config.update(overrides)
    return config


def test_mongodb_est_un_moteur_supporte():
    assert "mongodb" in DATABASE_ENGINES


def test_backups_est_une_etape_de_provisioning():
    assert "backups" in PROVISIONING_STEPS
    # doit venir apres 'database' dans l'ordre logique d'execution
    assert PROVISIONING_STEPS.index("database") < PROVISIONING_STEPS.index("backups")


def test_backups_genere_un_yaml_valide():
    config = _base_config(provisioning=["update_system", "backups"], deployment=[])
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    assert isinstance(data, list)
    names = [t["name"] for t in data[0]["tasks"]]
    assert any("backups" in n.lower() for n in names)


def test_backups_contient_script_cron_et_rotation():
    config = _base_config(provisioning=["update_system", "backups"], deployment=[])
    playbook = generate_playbook(config)
    assert "opsforge-backup.sh" in playbook
    assert "cron:" in playbook
    assert "RETENTION_DAYS" in playbook
    assert "find " in playbook and "-delete" in playbook


def test_backups_variables_par_defaut():
    config = _base_config(provisioning=["update_system", "backups"], deployment=[])
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    vars_ = data[0]["vars"]
    assert vars_["backup_dir"] == "/opt/backups"
    assert vars_["backup_retention_days"] == "7"
    assert vars_["backup_hour"] == "2"


def test_backups_variables_surchargees():
    config = _base_config(
        provisioning=["update_system", "backups"],
        deployment=[],
        backup_dir="/mnt/backups",
        backup_retention_days="30",
        backup_hour="4",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    vars_ = data[0]["vars"]
    assert vars_["backup_dir"] == "/mnt/backups"
    assert vars_["backup_retention_days"] == "30"
    assert vars_["backup_hour"] == "4"


def test_backups_avec_moteur_database_expose_la_variable():
    config = _base_config(
        provisioning=["update_system", "database", "backups"],
        deployment=[],
        database_engine="postgresql",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    assert data[0]["vars"]["database_engine"] == "postgresql"


def test_backups_role_genere_en_mode_roles():
    config = _base_config(provisioning=["update_system", "backups"], deployment=[])
    files = generate_role_based_project(config)
    assert "roles/backups/tasks/main.yml" in files
    assert "opsforge-backup.sh" in files["roles/backups/tasks/main.yml"]


def test_mongodb_genere_un_yaml_valide():
    config = _base_config(
        provisioning=["update_system", "database"],
        deployment=[],
        database_engine="mongodb",
        db_name="app",
        db_user="app_user",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    names = [t["name"] for t in data[0]["tasks"]]
    assert any("database" in n.lower() for n in names)
    assert "mongod" in playbook
    assert "mongosh" in playbook


def test_mongodb_role_named_with_engine_suffix():
    config = _base_config(provisioning=["update_system", "database"], database_engine="mongodb", deployment=[])
    files = generate_role_based_project(config)
    assert "roles/database_mongodb/tasks/main.yml" in files


def test_postgresql_genere_un_yaml_valide():
    config = _base_config(
        provisioning=["update_system", "database"],
        deployment=[],
        database_engine="postgresql",
        db_name="app",
        db_user="app_user",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    names = [t["name"] for t in data[0]["tasks"]]
    assert any("database" in n.lower() for n in names)
    assert "postgresql" in playbook
    assert "createdb" in playbook
    assert "psql" in playbook


def test_mysql_genere_un_yaml_valide():
    config = _base_config(
        provisioning=["update_system", "database"],
        deployment=[],
        database_engine="mysql",
        db_name="app",
        db_user="app_user",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    names = [t["name"] for t in data[0]["tasks"]]
    assert any("database" in n.lower() for n in names)
    assert "mariadb" in playbook.lower()
    assert "CREATE DATABASE IF NOT EXISTS" in playbook
    assert "CREATE USER IF NOT EXISTS" in playbook


def test_redis_genere_un_yaml_valide():
    config = _base_config(
        provisioning=["update_system", "database"],
        deployment=[],
        database_engine="redis",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    names = [t["name"] for t in data[0]["tasks"]]
    assert any("database" in n.lower() for n in names)
    assert "redis-server" in playbook
    assert "redis" in playbook.lower()


def test_postgresql_role_named_with_engine_suffix():
    config = _base_config(provisioning=["update_system", "database"], database_engine="postgresql", deployment=[])
    files = generate_role_based_project(config)
    assert "roles/database_postgresql/tasks/main.yml" in files


def test_mysql_role_named_with_engine_suffix():
    config = _base_config(provisioning=["update_system", "database"], database_engine="mysql", deployment=[])
    files = generate_role_based_project(config)
    assert "roles/database_mysql/tasks/main.yml" in files


@pytest.mark.parametrize("engine,expected_snippet", [
    ("postgresql", "pg_dump -U"),
    ("mysql", "mysqldump -u"),
    ("redis", "redis-cli SAVE"),
    ("mongodb", "mongodump --db"),
])
def test_backup_script_case_matches_engine(engine, expected_snippet):
    """Chaque moteur doit avoir sa commande de dump dediee dans le
    case/esac du script opsforge-backup.sh (voir templates/provisioning/backups.yml)."""
    config = _base_config(
        provisioning=["update_system", "database", "backups"],
        deployment=[],
        database_engine=engine,
    )
    playbook = generate_playbook(config)
    assert expected_snippet in playbook
