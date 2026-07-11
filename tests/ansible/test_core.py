"""
tests/test_core.py
-------------------
Suite de tests automatises pour generator/core.py.

Lancement :
    pip install pytest --break-system-packages
    pytest tests/ -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import yaml

from modules.ansible.core import (
    generate_playbook,
    generate_role_based_project,
    generate_inventory,
    generate_vault_vars_yaml,
    generate_vault_file,
    encrypt_vault_content,
    generate_multi_group_playbook,
    generate_multi_group_roles_project,
    generate_multi_group_inventory,
    SUPPORTED_LANGUAGES,
    DEPLOYMENT_STEPS,
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


def test_nouvelles_etapes_provisioning():
    """timezone / swap / unattended_upgrades genèrent bien leurs taches + variables."""
    config = _base_config(
        provisioning=["update_system", "base_packages", "timezone", "swap", "unattended_upgrades"],
        server_timezone="Europe/Paris",
        swap_size="4G",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)  # doit rester un YAML valide
    assert isinstance(data, list)
    assert 'Étape : timezone' in playbook
    assert "server_timezone" in playbook and "Europe/Paris" in playbook
    assert "/swapfile" in playbook and "4G" in playbook
    assert "unattended-upgrades" in playbook


def test_etape_users_cree_utilisateur_et_cle():
    config = _base_config(
        provisioning=["users"],
        ssh_user="deployer",
        deploy_user="deployer",
        ssh_public_key="ssh-ed25519 AAAATESTKEY toi@machine",
    )
    playbook = generate_playbook(config)
    data = yaml.safe_load(playbook)
    assert isinstance(data, list)
    assert "deployer" in playbook
    assert "NOPASSWD:ALL" in playbook
    assert "authorized_key" in playbook
    assert "ssh-ed25519 AAAATESTKEY" in playbook


# ------------------------------------------------------------------------
# generate_playbook (mode "flat")
# ------------------------------------------------------------------------
class TestGeneratePlaybook:

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_valid_yaml_for_every_language(self, lang):
        playbook = generate_playbook(_base_config(lang))
        data = yaml.safe_load(playbook)
        assert isinstance(data, list)
        assert data[0]["hosts"] == "webservers"

    def test_raises_when_no_steps_selected(self):
        config = _base_config()
        config["provisioning"] = []
        config["deployment"] = []
        with pytest.raises(ValueError):
            generate_playbook(config)

    def test_vars_include_all_expected_keys(self):
        playbook = generate_playbook(_base_config())
        data = yaml.safe_load(playbook)
        expected_keys = {
            "app_dir", "branch", "service_name", "repo_url",
            "build_cmd", "runtime_version", "health_check_port",
        }
        assert expected_keys.issubset(set(data[0]["vars"].keys()))

    def test_vault_vars_add_vars_files(self):
        config = _base_config(vault_vars={"db_password": "x"})
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        assert data[0]["vars_files"] == ["vault.yml"]

    def test_no_vault_means_no_vars_files(self):
        playbook = generate_playbook(_base_config())
        data = yaml.safe_load(playbook)
        assert "vars_files" not in data[0]

    def test_tasks_are_tagged(self):
        playbook = generate_playbook(_base_config())
        data = yaml.safe_load(playbook)
        for task in data[0]["tasks"]:
            assert "tags" in task
            assert isinstance(task["tags"], list)
            assert len(task["tags"]) > 0

    def test_runtime_language_specific_tag_present(self):
        playbook = generate_playbook(_base_config(lang="node"))
        data = yaml.safe_load(playbook)
        runtime_task = next(t for t in data[0]["tasks"] if "runtime" in t["name"])
        assert "runtime_node" in runtime_task["tags"]

    def test_new_deployment_steps_included_in_order(self):
        config = _base_config(deployment=["backup_previous", "git_clone", "restart_service", "health_check"])
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        names = [t["name"] for t in data[0]["tasks"]]
        backup_idx = next(i for i, n in enumerate(names) if "backup_previous" in n)
        clone_idx = next(i for i, n in enumerate(names) if "git_clone" in n)
        health_idx = next(i for i, n in enumerate(names) if "health_check" in n)
        assert backup_idx < clone_idx < health_idx

    def test_unselected_steps_excluded(self):
        config = _base_config(provisioning=["update_system"], deployment=["git_clone"])
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        names = [t["name"] for t in data[0]["tasks"]]
        assert not any("docker" in n.lower() for n in names)
        assert not any("nginx" in n.lower() for n in names)

    def test_https_step_uses_domain_and_email_vars(self):
        config = _base_config(
            provisioning=["update_system", "nginx", "https"],
            domain_name="monsite.fr",
            letsencrypt_email="moi@monsite.fr",
        )
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        assert data[0]["vars"]["domain_name"] == "monsite.fr"
        assert data[0]["vars"]["letsencrypt_email"] == "moi@monsite.fr"

    @pytest.mark.parametrize("engine", ["postgresql", "mysql", "redis"])
    def test_database_step_for_each_engine(self, engine):
        config = _base_config(provisioning=["update_system", "database"], database_engine=engine, deployment=[])
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        names = [t["name"] for t in data[0]["tasks"]]
        assert any("database" in n.lower() for n in names)

    def test_database_role_named_with_engine_suffix(self):
        config = _base_config(provisioning=["update_system", "database"], database_engine="redis", deployment=[])
        files = generate_role_based_project(config)
        assert "roles/database_redis/tasks/main.yml" in files

    def test_health_check_includes_rollback_logic(self):
        config = _base_config(deployment=["backup_previous", "git_clone", "health_check"])
        playbook = generate_playbook(config)
        assert "Rollback" in playbook
        assert "find:" in playbook

    @pytest.mark.parametrize("step", ["firewall", "ssh_hardening", "fail2ban", "monitoring"])
    def test_security_monitoring_steps_generate_valid_yaml(self, step):
        config = _base_config(provisioning=["update_system", step], deployment=[])
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        names = [t["name"] for t in data[0]["tasks"]]
        assert any(step in n for n in names)

    def test_firewall_opens_health_check_port(self):
        config = _base_config(provisioning=["update_system", "firewall"], deployment=[], health_check_port="3000")
        playbook = generate_playbook(config)
        assert "3000" in playbook or "health_check_port" in playbook

    def test_notify_step_uses_webhook_var(self):
        config = _base_config(deployment=["notify"], notify_webhook_url="https://hooks.slack.com/x")
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        assert data[0]["vars"]["notify_webhook_url"] == "https://hooks.slack.com/x"

    def test_zero_downtime_deploy_generates_valid_yaml(self):
        config = _base_config(deployment=["zero_downtime_deploy", "restart_service"])
        playbook = generate_playbook(config)
        data = yaml.safe_load(playbook)
        names = [t["name"] for t in data[0]["tasks"]]
        assert any("zero_downtime_deploy" in n for n in names)


# ------------------------------------------------------------------------
# generate_role_based_project (mode "roles")
# ------------------------------------------------------------------------
class TestGenerateRoleBasedProject:

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_produces_expected_files(self, lang):
        files = generate_role_based_project(_base_config(lang))
        assert "playbook.yml" in files
        assert "vars.yml" in files
        assert "ansible.cfg" in files
        assert any(k.startswith("roles/") for k in files)

    def test_runtime_role_named_with_language_suffix(self):
        files = generate_role_based_project(_base_config(lang="go"))
        assert "roles/runtime_go/tasks/main.yml" in files
        assert "roles/runtime_go/meta/main.yml" in files

    def test_raises_when_no_steps_selected(self):
        config = _base_config()
        config["provisioning"] = []
        config["deployment"] = []
        with pytest.raises(ValueError):
            generate_role_based_project(config)

    def test_playbook_references_roles_with_tags(self):
        files = generate_role_based_project(_base_config())
        data = yaml.safe_load(files["playbook.yml"])
        for role_entry in data[0]["roles"]:
            assert "role" in role_entry
            assert "tags" in role_entry

    def test_vault_adds_vars_files_entry(self):
        files = generate_role_based_project(_base_config(vault_vars={"a": "b"}))
        data = yaml.safe_load(files["playbook.yml"])
        assert "vault.yml" in data[0]["vars_files"]


# ------------------------------------------------------------------------
# generate_inventory
# ------------------------------------------------------------------------
class TestGenerateInventory:

    def test_basic_inventory_format(self):
        inv = generate_inventory("webservers", "203.0.113.10", "deploy")
        assert "[webservers]" in inv
        assert "203.0.113.10 ansible_user=deploy" in inv

    def test_with_ssh_key_path(self):
        inv = generate_inventory("webservers", "1.2.3.4", "deploy", ssh_key_path="/home/x/.ssh/id_rsa")
        assert "ansible_ssh_private_key_file=/home/x/.ssh/id_rsa" in inv


# ------------------------------------------------------------------------
# Vault (chiffrement Ansible Vault reel, AES256)
# ------------------------------------------------------------------------
# Le chiffrement Vault s'appuie sur ansible-core, qui importe `fcntl` :
# ce module n'existe pas sous Windows natif (seulement Unix/WSL). On saute
# donc proprement les tests qui chiffrent reellement, sans faire echouer la suite.
try:
    import fcntl  # noqa: F401

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

requires_vault = pytest.mark.skipif(
    not _HAS_FCNTL,
    reason="Ansible Vault necessite le module fcntl (Unix/WSL), absent sous Windows natif",
)


class TestVault:

    def test_vault_vars_yaml_format(self):
        yaml_text = generate_vault_vars_yaml({"db_password": "hunter2"})
        assert 'db_password: "hunter2"' in yaml_text

    def test_empty_secrets_returns_empty_string(self):
        assert generate_vault_vars_yaml({}) == ""

    @requires_vault
    def test_encrypt_produces_ansible_vault_header(self):
        encrypted = generate_vault_file({"a": "b"}, "mypassword")
        assert encrypted.startswith("$ANSIBLE_VAULT;1.1;AES256")

    def test_encrypt_without_password_raises(self):
        with pytest.raises(ValueError):
            encrypt_vault_content("a: b\n", "")

    @requires_vault
    def test_decrypt_roundtrip(self):
        from ansible.parsing.vault import VaultLib, VaultSecret
        from ansible.constants import DEFAULT_VAULT_ID_MATCH

        secrets = {"db_password": "hunter2", "api_key": "abc123"}
        encrypted = generate_vault_file(secrets, "testpass")

        vault = VaultLib(secrets=[(DEFAULT_VAULT_ID_MATCH, VaultSecret(b"testpass"))])
        decrypted = vault.decrypt(encrypted.encode("utf-8")).decode("utf-8")
        parsed = yaml.safe_load(decrypted)
        assert parsed == secrets

    @requires_vault
    def test_wrong_password_fails_to_decrypt(self):
        from ansible.parsing.vault import VaultLib, VaultSecret
        from ansible.constants import DEFAULT_VAULT_ID_MATCH

        encrypted = generate_vault_file({"a": "b"}, "correctpassword")
        vault = VaultLib(secrets=[(DEFAULT_VAULT_ID_MATCH, VaultSecret(b"wrongpassword"))])
        with pytest.raises(Exception):
            vault.decrypt(encrypted.encode("utf-8"))


# ------------------------------------------------------------------------
# Mode multi-serveurs
# ------------------------------------------------------------------------
class TestMultiGroup:

    def _groups(self):
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

    def test_flat_multi_group_produces_one_play_per_group(self):
        playbook = generate_multi_group_playbook(self._groups())
        data = yaml.safe_load(playbook)
        assert len(data) == 2
        assert {p["hosts"] for p in data} == {"web", "db"}

    def test_roles_deduplicated_across_groups(self):
        files = generate_multi_group_roles_project(self._groups())
        assert list(files.keys()).count("roles/update_system/tasks/main.yml") <= 1
        # update_system present exactly once, even though used by 2 groups
        matching = [k for k in files if k == "roles/update_system/tasks/main.yml"]
        assert len(matching) == 1

    def test_runtime_role_suffixed_per_group_language(self):
        files = generate_multi_group_roles_project(self._groups())
        assert "roles/runtime_node/tasks/main.yml" in files

    def test_each_group_has_its_own_vars_file(self):
        files = generate_multi_group_roles_project(self._groups())
        assert "vars_web.yml" in files
        assert "vars_db.yml" in files

    def test_duplicate_group_names_raise(self):
        groups = self._groups()
        groups[1]["hosts_group"] = "web"
        with pytest.raises(ValueError):
            generate_multi_group_playbook(groups)

    def test_empty_groups_raises(self):
        with pytest.raises(ValueError):
            generate_multi_group_playbook([])

    def test_group_without_any_step_raises(self):
        groups = [{"hosts_group": "empty", "provisioning": [], "deployment": [], "hosts": ["1.1.1.1"]}]
        with pytest.raises(ValueError):
            generate_multi_group_playbook(groups)

    def test_multi_group_inventory_sections(self):
        inv = generate_multi_group_inventory(self._groups())
        assert "[web]" in inv
        assert "[db]" in inv
        assert "10.0.0.1 ansible_user=deploy" in inv
        assert "10.0.0.2 ansible_user=deploy" in inv


# ------------------------------------------------------------------------
# Coherence des constantes du module
# ------------------------------------------------------------------------
class TestModuleConstants:

    def test_all_provisioning_steps_have_templates_or_are_language_dependent(self):
        assert "runtime" in PROVISIONING_STEPS  # cas special (depend du langage)

    def test_all_deployment_steps_have_templates_or_are_language_dependent(self):
        assert "install_deps" in DEPLOYMENT_STEPS  # cas special
        assert "backup_previous" in DEPLOYMENT_STEPS
        assert "health_check" in DEPLOYMENT_STEPS
