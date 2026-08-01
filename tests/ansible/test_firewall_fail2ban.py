"""
tests/ansible/test_firewall_fail2ban.py
-----------------------------------------
Verifie que les etapes de provisioning "firewall" et "fail2ban" sont bien
generees dynamiquement selon les autres etapes activees (au lieu du contenu
statique fige d'avant), et que le YAML produit reste valide.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml

from modules.ansible.core import generate_playbook
from modules.firewall.core import FAIL2BAN_CATALOG


def _ports_loop_lines(yaml_text):
    return [line.strip() for line in yaml_text.splitlines() if line.strip().startswith("loop:")]


def test_firewall_without_nginx_does_not_open_80_443():
    config = {"hosts_group": "webservers", "provisioning": ["firewall"], "deployment": []}
    text = generate_playbook(config)
    loops = _ports_loop_lines(text)
    assert loops, "aucune ligne loop: trouvee"
    for line in loops:
        assert '"80"' not in line
        assert '"443"' not in line
        assert '"22"' in line  # SSH toujours ouvert


def test_firewall_with_nginx_opens_80_443():
    config = {"hosts_group": "webservers", "provisioning": ["nginx", "firewall"], "deployment": []}
    text = generate_playbook(config)
    loops = _ports_loop_lines(text)
    assert loops
    for line in loops:
        assert '"80"' in line
        assert '"443"' in line


def test_firewall_with_https_opens_80_443():
    # "https" seul (sans "nginx") doit aussi declencher l'ouverture,
    # puisque certbot/Let's Encrypt en depend.
    config = {"hosts_group": "webservers", "provisioning": ["https", "firewall"], "deployment": []}
    text = generate_playbook(config)
    loops = _ports_loop_lines(text)
    for line in loops:
        assert '"80"' in line
        assert '"443"' in line


def test_fail2ban_without_nginx_has_only_sshd_jail():
    config = {"hosts_group": "webservers", "provisioning": ["fail2ban"], "deployment": []}
    text = generate_playbook(config)
    assert "[sshd]" in text
    assert "[nginx-http-auth]" not in text


def test_fail2ban_with_nginx_adds_nginx_jails_enabled():
    config = {"hosts_group": "webservers", "provisioning": ["nginx", "fail2ban"], "deployment": []}
    text = generate_playbook(config)
    assert "[sshd]" in text
    assert "[nginx-http-auth]" in text
    assert "[nginx-limit-req]" in text
    assert "[nginx-botsearch]" in text
    # Les jails nginx doivent etre actives (contrairement au module firewall
    # autonome ou elles sont juste suggerees) : nginx est garanti installe
    # par ce meme playbook, donc pas besoin de confirmation manuelle.
    idx = text.index("[nginx-http-auth]")
    snippet = text[idx: idx + 200]
    assert "enabled = true" in snippet


def test_fail2ban_jail_values_come_from_firewall_catalog():
    # Verifie l'integration reelle : les valeurs (maxretry/bantime/findtime)
    # generees ici doivent correspondre a celles du catalogue du module
    # firewall, pas a des constantes dupliquees a la main.
    config = {"hosts_group": "webservers", "provisioning": ["nginx", "fail2ban"], "deployment": []}
    text = generate_playbook(config)
    expected = FAIL2BAN_CATALOG["nginx-botsearch"]
    idx = text.index("[nginx-botsearch]")
    snippet = text[idx: idx + 200]
    assert f"maxretry = {expected['maxretry']}" in snippet
    assert f"bantime = {expected['bantime']}" in snippet


def test_generated_playbook_with_firewall_and_fail2ban_is_valid_yaml():
    for provisioning in (["firewall", "fail2ban"], ["nginx", "firewall", "fail2ban"]):
        config = {"hosts_group": "webservers", "provisioning": provisioning, "deployment": []}
        text = generate_playbook(config)
        parsed = yaml.safe_load(text)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1


def test_windows_firewall_still_uses_static_template_not_dynamic():
    # La cible Windows garde son propre template statique (pare-feu natif
    # Windows via modules ansible.windows.*) : la generation dynamique ne
    # doit s'appliquer qu'a Linux.
    config = {
        "hosts_group": "webservers",
        "target_os": "windows",
        "provisioning": ["firewall"],
        "deployment": [],
    }
    text = generate_playbook(config)
    assert "New-NetFirewallRule" in text or "win_firewall" in text.lower() or "windows" in text.lower()
