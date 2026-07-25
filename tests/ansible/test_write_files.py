"""Tests des fonctions write_* du module Ansible — non couvertes jusqu'ici.

Ces fonctions sont de fines enveloppes autour des generate_* equivalentes,
qui ecrivent le resultat sur disque (playbook flat, projet en roles, projet
multi-groupes, vault chiffre). Utilise le fixture pytest `tmp_path`.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import yaml

from modules.ansible.core import (
    write_playbook,
    write_role_based_project,
    write_multi_group_project,
    write_vault_file,
    generate_playbook,
)

# Le chiffrement Vault s'appuie sur ansible-core, qui importe `fcntl` : ce
# module n'existe pas sous Windows natif (seulement Unix/WSL). On saute donc
# proprement les tests qui chiffrent reellement, sans faire echouer la suite
# (meme garde que tests/ansible/test_core.py).
try:
    import fcntl  # noqa: F401

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

requires_vault = pytest.mark.skipif(
    not _HAS_FCNTL,
    reason="Ansible Vault necessite le module fcntl (Unix/WSL), absent sous Windows natif",
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


def _groupes():
    return [
        {
            "hosts_group": "web",
            "provisioning": ["update_system", "nginx", "runtime"],
            "runtime_language": "node",
            "deployment": ["git_clone", "install_deps", "restart_service"],
            "deployment_language": "node",
            "repo_url": "git@github.com:x/web.git",
            "app_dir": "/opt/web",
            "service_name": "web",
            "hosts": ["10.0.0.1"],
        },
        {
            "hosts_group": "db",
            "provisioning": ["update_system", "base_packages"],
            "deployment": [],
            "hosts": ["10.0.0.2"],
        },
    ]


# --------------------------------------------------------------------------
# write_playbook
# --------------------------------------------------------------------------

def test_write_playbook_ecrit_le_fichier(tmp_path):
    output_path = tmp_path / "site.yml"
    resultat = write_playbook(_base_config(), str(output_path))

    assert resultat == str(output_path)
    assert output_path.exists()

    contenu_disque = output_path.read_text(encoding="utf-8")
    assert contenu_disque == generate_playbook(_base_config())
    assert yaml.safe_load(contenu_disque) is not None  # reste un YAML valide


def test_write_playbook_cree_les_dossiers_manquants(tmp_path):
    output_path = tmp_path / "sous" / "dossier" / "site.yml"
    write_playbook(_base_config(), str(output_path))
    assert output_path.exists()


# --------------------------------------------------------------------------
# write_role_based_project
# --------------------------------------------------------------------------

def test_write_role_based_project_ecrit_tous_les_fichiers(tmp_path):
    chemins = write_role_based_project(_base_config(), str(tmp_path))

    assert len(chemins) > 0
    for chemin in chemins:
        assert os.path.isfile(chemin)

    noms_relatifs = {os.path.relpath(c, str(tmp_path)) for c in chemins}
    assert "playbook.yml" in noms_relatifs
    assert any(n.startswith("roles" + os.sep) for n in noms_relatifs)


def test_write_role_based_project_retourne_des_chemins_absolus(tmp_path):
    chemins = write_role_based_project(_base_config(), str(tmp_path))
    for chemin in chemins:
        assert os.path.isabs(chemin)


# --------------------------------------------------------------------------
# write_multi_group_project
# --------------------------------------------------------------------------

def test_write_multi_group_project_ecrit_tous_les_fichiers(tmp_path):
    chemins = write_multi_group_project(_groupes(), str(tmp_path))

    assert len(chemins) > 0
    for chemin in chemins:
        assert os.path.isfile(chemin)

    noms_relatifs = {os.path.relpath(c, str(tmp_path)) for c in chemins}
    assert any("update_system" in n for n in noms_relatifs)


@requires_vault
def test_write_multi_group_project_avec_vault_ecrit_vault_yml(tmp_path):
    secrets = {"db_password": "hunter2"}
    chemins = write_multi_group_project(
        _groupes(), str(tmp_path), vault_vars=secrets, vault_password="motdepasse"
    )

    noms_relatifs = {os.path.relpath(c, str(tmp_path)) for c in chemins}
    assert "vault.yml" in noms_relatifs

    vault_path = tmp_path / "vault.yml"
    contenu = vault_path.read_text(encoding="utf-8")
    assert contenu.startswith("$ANSIBLE_VAULT;1.1;AES256")


def test_write_multi_group_project_sans_vault_naugmente_pas_vault_yml(tmp_path):
    chemins = write_multi_group_project(_groupes(), str(tmp_path))
    noms_relatifs = {os.path.relpath(c, str(tmp_path)) for c in chemins}
    assert "vault.yml" not in noms_relatifs


# --------------------------------------------------------------------------
# write_vault_file
# --------------------------------------------------------------------------

@requires_vault
def test_write_vault_file_ecrit_un_vault_chiffre(tmp_path):
    output_path = tmp_path / "secrets" / "vault.yml"
    secrets = {"api_key": "abc123"}

    resultat = write_vault_file(secrets, "monmotdepasse", str(output_path))

    assert resultat == str(output_path)
    assert output_path.exists()

    contenu = output_path.read_text(encoding="utf-8")
    assert contenu.startswith("$ANSIBLE_VAULT;1.1;AES256")
    # Le chiffrement utilise un sel aleatoire : deux appels produisent des
    # sorties differentes meme avec le meme mot de passe, on ne peut donc
    # pas comparer le contenu a un second appel de generate_vault_file().
    lignes_hex = contenu.strip().split("\n")[1:]
    assert all(re.fullmatch(r"[0-9a-f]+", ligne) for ligne in lignes_hex)


@requires_vault
def test_write_vault_file_cree_les_dossiers_manquants(tmp_path):
    output_path = tmp_path / "a" / "b" / "c" / "vault.yml"
    write_vault_file({"x": "y"}, "pass", str(output_path))
    assert output_path.exists()
