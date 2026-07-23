"""Tests de la cible Windows/WinRM du module Ansible d'OpsForge."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import yaml

from modules.ansible.core import (
    generate_playbook,
    generate_inventory,
    generate_multi_group_inventory,
    generate_role_based_project,
    generate_multi_group_roles_project,
    TARGET_OSES,
    WINDOWS_SUPPORTED_PROVISIONING,
    WINDOWS_SUPPORTED_DEPLOYMENT,
    WINDOWS_SUPPORTED_LANGUAGES,
)


def _windows_config(**overrides):
    config = {
        "hosts_group": "winservers",
        "provisioning": ["update_system", "base_packages", "users", "firewall", "runtime"],
        "runtime_language": "node",
        "deployment": ["backup_previous", "git_clone", "install_deps", "build", "restart_service", "health_check", "notify"],
        "deployment_language": "node",
        "repo_url": "git@github.com:x/y.git",
        "app_dir": r"C:\apps\myapp",
        "service_name": "myapp",
        "target_os": "windows",
    }
    config.update(overrides)
    return config


def test_target_oses():
    assert set(TARGET_OSES) == {"linux", "windows"}


# ---------------------------------------------------------------------------
# Validation : etapes/langages non supportes sur Windows
# ---------------------------------------------------------------------------
def test_etape_provisioning_non_supportee_leve_erreur():
    config = _windows_config(provisioning=["update_system", "docker"], deployment=[])
    with pytest.raises(ValueError):
        generate_playbook(config)


def test_etape_deploiement_non_supportee_leve_erreur():
    config = _windows_config(provisioning=[], deployment=["git_clone", "reload_nginx"])
    with pytest.raises(ValueError):
        generate_playbook(config)


def test_langage_runtime_non_supporte_leve_erreur():
    config = _windows_config(provisioning=["runtime"], deployment=[], runtime_language="php")
    with pytest.raises(ValueError):
        generate_playbook(config)


def test_langage_install_deps_non_supporte_leve_erreur():
    config = _windows_config(provisioning=[], deployment=["install_deps"], deployment_language="ruby")
    with pytest.raises(ValueError):
        generate_playbook(config)


def test_message_erreur_liste_les_etapes_disponibles():
    config = _windows_config(provisioning=["monitoring"], deployment=[])
    with pytest.raises(ValueError) as exc_info:
        generate_playbook(config)
    msg = str(exc_info.value)
    for step in WINDOWS_SUPPORTED_PROVISIONING:
        assert step in msg


# ---------------------------------------------------------------------------
# Generation reussie pour toutes les etapes/langages supportes
# ---------------------------------------------------------------------------
def test_toutes_les_etapes_windows_generent_un_yaml_valide():
    config = _windows_config()
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    assert isinstance(data, list)
    assert len(data[0]["tasks"]) == len(config["provisioning"]) + len(config["deployment"])


@pytest.mark.parametrize("lang", WINDOWS_SUPPORTED_LANGUAGES)
def test_chaque_langage_supporte_windows(lang):
    config = _windows_config(
        provisioning=["runtime"], runtime_language=lang,
        deployment=["install_deps"], deployment_language=lang,
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    assert len(data[0]["tasks"]) == 2


def test_playbook_windows_utilise_les_modules_ansible_windows():
    config = _windows_config()
    playbook = generate_playbook(config)
    assert "ansible.windows.win_updates" in playbook
    assert "chocolatey.chocolatey.win_chocolatey" in playbook
    assert "ansible.windows.win_user" in playbook
    assert "community.windows.win_firewall_rule" in playbook
    assert "ansible.windows.win_service" in playbook
    # Aucune trace de logique Linux (apt/systemd/become) ne doit fuiter.
    assert "apt:" not in playbook
    assert "systemd:" not in playbook


def test_notify_reste_identique_quelle_que_soit_la_cible():
    linux_playbook = generate_playbook(_windows_config(
        target_os="linux", provisioning=[], deployment=["notify"]
    ))
    windows_playbook = generate_playbook(_windows_config(
        target_os="windows", provisioning=[], deployment=["notify"]
    ))
    linux_task = linux_playbook.split('name: "Étape : notify"')[1]
    windows_task = windows_playbook.split('name: "Étape : notify"')[1]
    assert linux_task == windows_task


# ---------------------------------------------------------------------------
# Chemins Windows (antislash) : regression sur l'echappement YAML
# ---------------------------------------------------------------------------
def test_chemin_windows_avec_antislash_reste_un_yaml_valide():
    config = _windows_config(app_dir=r"C:\Apps\MonApp\v2")
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)  # leve une exception si le YAML est invalide
    assert data[0]["vars"]["app_dir"] == r"C:\Apps\MonApp\v2"


def test_chemin_windows_dans_les_vars_dun_projet_en_roles():
    config = _windows_config(app_dir=r"C:\Apps\MonApp")
    files = generate_role_based_project(config)
    data = yaml.safe_load(files["vars.yml"])
    assert data["app_dir"] == r"C:\Apps\MonApp"


# ---------------------------------------------------------------------------
# Mode "roles" : suffixe _windows pour eviter les collisions
# ---------------------------------------------------------------------------
def test_roles_windows_ont_un_suffixe_dedie():
    config = _windows_config()
    files = generate_role_based_project(config)
    assert "roles/update_system_windows/tasks/main.yml" in files
    assert "roles/runtime_node_windows/tasks/main.yml" in files
    assert "roles/install_deps_node_windows/tasks/main.yml" in files
    # 'notify' delegue a localhost : role partage, pas de suffixe.
    assert "roles/notify/tasks/main.yml" in files
    assert "roles/notify_windows/tasks/main.yml" not in files


def test_pas_de_collision_multi_groupe_linux_et_windows():
    groups = [
        {
            "hosts_group": "linux_web",
            "hosts": ["10.0.0.1"],
            "provisioning": ["update_system"],
            "runtime_language": "node",
            "deployment": [],
            "deployment_language": "node",
            "repo_url": "git@github.com:x/y.git",
            "target_os": "linux",
        },
        {
            "hosts_group": "windows_web",
            "hosts": ["10.0.0.2"],
            "provisioning": ["update_system"],
            "runtime_language": "node",
            "deployment": [],
            "deployment_language": "node",
            "repo_url": "git@github.com:x/y.git",
            "target_os": "windows",
        },
    ]
    files = generate_multi_group_roles_project(groups)
    assert "roles/update_system/tasks/main.yml" in files
    assert "roles/update_system_windows/tasks/main.yml" in files
    # Les deux roles doivent avoir un contenu different (Linux vs Windows).
    assert files["roles/update_system/tasks/main.yml"] != files["roles/update_system_windows/tasks/main.yml"]


# ---------------------------------------------------------------------------
# Inventaire WinRM
# ---------------------------------------------------------------------------
def test_inventaire_winrm_par_defaut():
    inv = generate_inventory("winservers", "10.0.0.5", "Administrator", target_os="windows")
    assert "ansible_connection=winrm" in inv
    assert "ansible_winrm_transport=ntlm" in inv
    assert "ansible_port=5986" in inv
    assert "ansible_winrm_server_cert_validation=ignore" in inv


def test_inventaire_winrm_avec_mot_de_passe():
    inv = generate_inventory("winservers", "10.0.0.5", "Administrator", target_os="windows", winrm_password="S3cret!")
    assert "ansible_password=S3cret!" in inv


def test_inventaire_winrm_transport_basic_port_5985():
    inv = generate_inventory("winservers", "10.0.0.5", "Administrator", target_os="windows", winrm_transport="basic")
    assert "ansible_port=5985" in inv
    assert "ansible_winrm_server_cert_validation=ignore" not in inv


def test_inventaire_winrm_port_personnalise():
    inv = generate_inventory("winservers", "10.0.0.5", "Administrator", target_os="windows", winrm_port=5987)
    assert "ansible_port=5987" in inv


def test_inventaire_linux_inchange_sans_target_os():
    inv = generate_inventory("webservers", "10.0.0.5", "deploy")
    assert "ansible_connection=winrm" not in inv
    assert "10.0.0.5 ansible_user=deploy" in inv


def test_inventaire_multi_groupe_mixte_linux_windows():
    groups = [
        {"hosts_group": "linux_web", "hosts": ["10.0.0.1"], "ssh_user": "deploy"},
        {"hosts_group": "windows_web", "hosts": ["10.0.0.2"], "ssh_user": "Administrator",
         "target_os": "windows", "winrm_password": "S3cret!"},
    ]
    inv = generate_multi_group_inventory(groups)
    assert "[linux_web]" in inv
    assert "10.0.0.1 ansible_user=deploy" in inv
    assert "ansible_connection=winrm" not in inv.split("[windows_web]")[0]
    assert "[windows_web]" in inv
    windows_section = inv.split("[windows_web]")[1]
    assert "ansible_connection=winrm" in windows_section
    assert "ansible_password=S3cret!" in windows_section
