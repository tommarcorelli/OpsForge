from modules.firewall.core import (
    generate_fail2ban_jail,
    generate_firewall,
    generate_nftables_conf,
    generate_ufw_script,
    get_preset,
    list_fail2ban_jails,
    list_presets,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "web-public" in presets
    assert "db-private" in presets
    assert "ssh-bastion" in presets
    assert "custom" in presets


def test_validate_config_rejects_unknown_backend():
    errors = validate_config({"preset": "web-public", "backend": "bogus"})
    assert any("Backend non supporte" in e for e in errors)


def test_validate_config_rejects_bad_port_in_custom():
    config = {
        "preset": "custom",
        "backend": "ufw",
        "rules": [{"port": 99999, "proto": "tcp", "action": "allow"}],
    }
    errors = validate_config(config)
    assert any("port invalide" in e for e in errors)


def test_generate_ufw_script_web_public():
    script = generate_ufw_script({"preset": "web-public"})
    assert "ufw allow 22/tcp" in script
    assert "ufw allow 80/tcp" in script
    assert "ufw allow 443/tcp" in script
    assert "ufw default deny incoming" in script


def test_generate_ufw_script_limit_action():
    script = generate_ufw_script({"preset": "ssh-bastion"})
    assert "ufw limit 22/tcp" in script


def test_generate_nftables_conf_has_policy_drop_by_default():
    conf = generate_nftables_conf({"preset": "db-private"})
    assert "policy drop" in conf
    assert "5432" in conf
    assert "10.0.0.0/8" in conf


def test_generate_fail2ban_jail_default():
    jail = generate_fail2ban_jail({})
    assert "[sshd]" in jail
    assert "enabled = true" in jail


def test_generate_firewall_ufw_plus_fail2ban():
    files = generate_firewall({"preset": "web-public", "backend": "ufw", "fail2ban": True})
    assert set(files.keys()) == {"setup-firewall.sh", "jail.local"}


def test_generate_firewall_nftables_no_fail2ban():
    files = generate_firewall({"preset": "web-public", "backend": "nftables"})
    assert set(files.keys()) == {"nftables.conf"}


def test_generate_firewall_invalid_config_raises():
    try:
        generate_firewall({"preset": "unknown-preset"})
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass


def test_get_preset_returns_deep_copy():
    p1 = get_preset("web-public")
    p1["rules"].append({"port": 9999, "proto": "tcp", "action": "allow"})
    p2 = get_preset("web-public")
    assert len(p2["rules"]) == 3  # inchange, pas affecte par la mutation de p1


def test_get_preset_includes_suggested_fail2ban_jails():
    p = get_preset("web-public")
    assert "sshd" in p["fail2ban_jails"]
    assert p["fail2ban_jails"]["sshd"]["enabled"] is True
    assert "nginx-http-auth" in p["fail2ban_jails"]
    assert p["fail2ban_jails"]["nginx-http-auth"]["enabled"] is False  # opt-in


def test_get_preset_db_private_has_no_suggested_jails_beyond_sshd():
    p = get_preset("db-private")
    assert list(p["fail2ban_jails"].keys()) == ["sshd"]


def test_validate_config_accepts_ipv6_source():
    config = {
        "preset": "custom",
        "backend": "nftables",
        "rules": [{"port": 443, "proto": "tcp", "source": "2001:db8::/32", "action": "allow"}],
    }
    assert validate_config(config) == []


def test_validate_config_rejects_invalid_source():
    config = {
        "preset": "custom",
        "backend": "ufw",
        "rules": [{"port": 80, "proto": "tcp", "source": "pas-une-ip", "action": "allow"}],
    }
    errors = validate_config(config)
    assert any("source invalide" in e for e in errors)


def test_validate_config_rejects_unknown_fail2ban_jail():
    config = {
        "preset": "web-public",
        "backend": "ufw",
        "fail2ban": True,
        "fail2ban_jails": {"jail-qui-nexiste-pas": {"enabled": True}},
    }
    errors = validate_config(config)
    assert any("Jail fail2ban inconnue" in e for e in errors)


def test_generate_nftables_conf_uses_ip6_saddr_for_ipv6_source():
    conf = generate_nftables_conf({
        "preset": "custom",
        "rules": [{"port": 443, "proto": "tcp", "source": "2001:db8::/32", "action": "allow"}],
    })
    assert "ip6 saddr 2001:db8::/32" in conf


def test_generate_nftables_conf_uses_ip_saddr_for_ipv4_source():
    conf = generate_nftables_conf({
        "preset": "custom",
        "rules": [{"port": 443, "proto": "tcp", "source": "10.0.0.0/8", "action": "allow"}],
    })
    assert "ip saddr 10.0.0.0/8" in conf


def test_generate_nftables_conf_always_includes_icmpv6_essentials():
    # Sans ces regles, policy drop casse IPv6 meme sans regle IPv6 explicite.
    conf = generate_nftables_conf({"preset": "web-public"})
    assert "icmpv6 type" in conf
    assert "nd-neighbor-solicit" in conf


def test_generate_ufw_script_enables_ipv6():
    script = generate_ufw_script({"preset": "web-public"})
    assert "IPV6=yes" in script


def test_generate_fail2ban_jail_with_extra_jails():
    jail = generate_fail2ban_jail({
        "fail2ban_jails": {
            "sshd": {"enabled": True, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
            "nginx-http-auth": {"enabled": True, "maxretry": 5, "bantime": "1h", "findtime": "10m"},
        }
    })
    assert "[nginx-http-auth]" in jail
    assert "[sshd]" in jail
