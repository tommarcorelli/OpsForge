"""Tests du scaffolding Molecule (module Ansible, mode 'roles')."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import yaml

from modules.ansible.core import (
    generate_role_based_project,
    generate_multi_group_roles_project,
    MOLECULE_DRIVERS,
)


def _base_config(lang="python", **overrides):
    config = {
        "hosts_group": "webservers",
        "provisioning": ["update_system", "docker", "nginx", "runtime"],
        "runtime_language": lang,
        "deployment": ["git_clone", "install_deps", "restart_service"],
        "deployment_language": lang,
        "repo_url": "git@github.com:x/y.git",
        "app_dir": "/opt/x",
        "service_name": "x",
    }
    config.update(overrides)
    return config


def test_pas_de_fichiers_molecule_sans_lactiver():
    files = generate_role_based_project(_base_config())
    assert not any("molecule" in path for path in files)
    assert "requirements-molecule.txt" not in files


def test_un_scenario_par_role_quand_active():
    config = _base_config(molecule=True)
    files = generate_role_based_project(config)

    provisioning, deployment = config["provisioning"], config["deployment"]
    # runtime => role suffixe par langage
    expected_roles = ["update_system", "docker", "nginx", "runtime_python",
                       "git_clone", "install_deps_python", "restart_service"]

    for role in expected_roles:
        assert f"roles/{role}/molecule/default/molecule.yml" in files
        assert f"roles/{role}/molecule/default/converge.yml" in files
        assert f"roles/{role}/molecule/default/verify.yml" in files

    assert "requirements-molecule.txt" in files


def test_requirements_molecule_docker():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="docker"))
    req = files["requirements-molecule.txt"]
    assert "molecule" in req
    assert "molecule-plugins[docker]" in req
    assert "ansible-core" in req


def test_requirements_molecule_delegated_sans_plugin():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="delegated"))
    req = files["requirements-molecule.txt"]
    assert "molecule" in req
    assert "ansible-core" in req
    assert "molecule-plugins" not in req


def test_requirements_molecule_vagrant():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="vagrant"))
    req = files["requirements-molecule.txt"]
    assert "molecule-plugins[vagrant]" in req


def test_driver_invalide_retombe_sur_docker_par_defaut():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="n-importe-quoi"))
    molecule_yml = files["roles/docker/molecule/default/molecule.yml"]
    assert "name: docker" in molecule_yml


@pytest.mark.parametrize("driver", MOLECULE_DRIVERS)
def test_yaml_genere_est_valide_pour_chaque_driver(driver):
    config = _base_config(molecule=True, molecule_driver=driver)
    files = generate_role_based_project(config)
    for path, content in files.items():
        if path.endswith(".yml"):
            yaml.safe_load(content)  # ne doit pas lever d'exception


def test_molecule_yml_driver_docker_contient_image_et_privileged():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="docker"))
    molecule_yml = files["roles/docker/molecule/default/molecule.yml"]
    parsed = yaml.safe_load(molecule_yml)
    assert parsed["driver"]["name"] == "docker"
    assert parsed["platforms"][0]["privileged"] is True
    assert "image" in parsed["platforms"][0]


def test_molecule_yml_driver_delegated_sans_conteneur():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="delegated"))
    molecule_yml = files["roles/docker/molecule/default/molecule.yml"]
    parsed = yaml.safe_load(molecule_yml)
    assert parsed["driver"]["name"] == "delegated"
    assert parsed["platforms"][0]["name"] == "localhost"


def test_molecule_yml_driver_vagrant_a_une_box():
    files = generate_role_based_project(_base_config(molecule=True, molecule_driver="vagrant"))
    molecule_yml = files["roles/docker/molecule/default/molecule.yml"]
    parsed = yaml.safe_load(molecule_yml)
    assert parsed["driver"]["name"] == "vagrant"
    assert "box" in parsed["platforms"][0]


def test_converge_yml_reference_le_bon_role():
    files = generate_role_based_project(_base_config(molecule=True))
    converge = files["roles/nginx/molecule/default/converge.yml"]
    parsed = yaml.safe_load(converge)
    assert parsed[0]["roles"] == ["nginx"]
    assert parsed[0]["become"] is True


def test_verify_yml_docker_contient_une_assertion_specifique():
    files = generate_role_based_project(_base_config(molecule=True))
    verify = files["roles/docker/molecule/default/verify.yml"]
    assert "docker.service" in verify
    assert "ansible.builtin.assert" in verify


def test_verify_yml_etape_sans_snippet_dedie_utilise_le_generique():
    # 'git_clone' n'a pas de snippet specifique dans MOLECULE_VERIFY_SNIPPETS
    files = generate_role_based_project(_base_config(molecule=True))
    verify = files["roles/git_clone/molecule/default/verify.yml"]
    assert "Aucune verification specifique" in verify


def test_molecule_indisponible_sans_layout_roles_est_gere_par_le_cli():
    # Le core ne bloque pas lui-meme (mode flat n'appelle jamais cette fonction) ;
    # generate_playbook (mode flat) ignore silencieusement la cle "molecule".
    from modules.ansible.core import generate_playbook
    config = _base_config(molecule=True)
    # Ne doit pas lever d'exception ni produire de reference a molecule
    playbook = generate_playbook(config)
    assert "molecule" not in playbook


def test_multi_groupes_molecule_active_uniquement_sur_un_groupe():
    groups = [
        {
            "hosts_group": "web",
            "provisioning": ["docker"],
            "deployment": [],
            "molecule": True,
            "molecule_driver": "delegated",
        },
        {
            "hosts_group": "db",
            "provisioning": ["nginx"],
            "deployment": [],
        },
    ]
    files = generate_multi_group_roles_project(groups)
    assert "roles/docker/molecule/default/molecule.yml" in files
    assert "roles/nginx/molecule/default/molecule.yml" not in files
    assert "requirements-molecule.txt" in files
    assert "delegated" in files["roles/docker/molecule/default/molecule.yml"]


def test_multi_groupes_sans_molecule_aucun_fichier():
    groups = [
        {"hosts_group": "web", "provisioning": ["docker"], "deployment": []},
    ]
    files = generate_multi_group_roles_project(groups)
    assert not any("molecule" in path for path in files)
    assert "requirements-molecule.txt" not in files
