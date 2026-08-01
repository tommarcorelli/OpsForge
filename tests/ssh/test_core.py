from modules.ssh.core import (
    AUTHORIZED_KEYS_NAME,
    CLIENT_CONFIG_NAME,
    SSHD_FRAGMENT_NAME,
    generate_authorized_keys,
    generate_client_config,
    generate_ssh,
    generate_sshd_config,
    get_preset,
    list_presets,
    list_presets_by_role,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "poste-de-travail" in presets
    assert "acces-bastion" in presets
    assert "serveur-durci" in presets
    assert "sftp-only" in presets
    assert "custom" in presets


def test_list_presets_by_role_splits_client_and_server():
    client_presets = list_presets_by_role("client")
    server_presets = list_presets_by_role("server")
    assert "acces-bastion" in client_presets
    assert "acces-bastion" not in server_presets
    assert "bastion" in server_presets
    assert "bastion" not in client_presets


def test_all_presets_are_valid():
    for name in list_presets():
        if name == "custom":
            continue
        assert validate_config(get_preset(name)) == [], name


def test_get_preset_returns_deep_copy():
    p1 = get_preset("acces-bastion")
    p1["hosts"].append({"alias": "ajoute", "hostname": "example.com"})
    p2 = get_preset("acces-bastion")
    assert len(p2["hosts"]) == 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_validate_rejects_unknown_role():
    errors = validate_config({"preset": "custom", "role": "proxy"})
    assert any("Role non supporte" in e for e in errors)


def test_validate_rejects_client_without_hosts():
    errors = validate_config({"preset": "custom", "role": "client", "hosts": []})
    assert any("Aucun hote" in e for e in errors)


def test_validate_rejects_host_without_hostname():
    config = {"preset": "custom", "role": "client", "hosts": [{"alias": "web"}]}
    errors = validate_config(config)
    assert any("hostname manquant" in e for e in errors)


def test_validate_rejects_invalid_alias():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "mon serveur", "hostname": "example.com"}],
    }
    errors = validate_config(config)
    assert any("alias invalide" in e for e in errors)


def test_validate_rejects_duplicate_alias():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [
            {"alias": "web", "hostname": "a.example.com"},
            {"alias": "web", "hostname": "b.example.com"},
        ],
    }
    errors = validate_config(config)
    assert any("plusieurs fois" in e for e in errors)


def test_validate_rejects_proxy_jump_to_undefined_alias():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "app", "hostname": "10.0.0.1", "proxy_jump": "bastion"}],
    }
    errors = validate_config(config)
    assert any("ne correspond a aucun alias" in e for e in errors)


def test_validate_accepts_proxy_jump_to_defined_alias():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [
            {"alias": "bastion", "hostname": "bastion.example.com"},
            {"alias": "app", "hostname": "10.0.0.1", "proxy_jump": "bastion"},
        ],
    }
    assert validate_config(config) == []


def test_validate_accepts_proxy_jump_with_user_at_host():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "app", "hostname": "10.0.0.1", "proxy_jump": "jump@bastion.example.com:2222"}],
    }
    assert validate_config(config) == []


def test_validate_rejects_bad_forward_format():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "db", "hostname": "10.0.0.1", "local_forwards": ["5432"]}],
    }
    errors = validate_config(config)
    assert any("redirection invalide" in e for e in errors)


def test_validate_rejects_out_of_range_port():
    config = {
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "web", "hostname": "example.com", "port": 70000}],
    }
    errors = validate_config(config)
    assert any("hors plage" in e for e in errors)


def test_validate_rejects_unknown_permit_root_login():
    config = {"preset": "custom", "role": "server", "permit_root_login": "peut-etre"}
    errors = validate_config(config)
    assert any("PermitRootLogin invalide" in e for e in errors)


def test_validate_rejects_no_auth_method_at_all():
    config = {
        "preset": "custom",
        "role": "server",
        "pubkey_authentication": False,
        "password_authentication": False,
    }
    errors = validate_config(config)
    assert any("plus personne ne pourrait se connecter" in e for e in errors)


def test_validate_rejects_private_key_in_authorized_keys():
    config = {
        "preset": "custom",
        "role": "server",
        "authorized_keys": [{"key": "-----BEGIN OPENSSH PRIVATE KEY-----"}],
    }
    errors = validate_config(config)
    assert any("cle PRIVEE" in e for e in errors)


def test_validate_rejects_unknown_key_type():
    config = {
        "preset": "custom",
        "role": "server",
        "authorized_keys": [{"key": "pas-une-cle AAAA"}],
    }
    errors = validate_config(config)
    assert any("type de cle non reconnu" in e.lower() for e in errors)


def test_validate_rejects_relative_chroot_dir():
    config = {
        "preset": "custom",
        "role": "server",
        "sftp_only_group": "sftponly",
        "sftp_chroot_dir": "srv/sftp",
    }
    errors = validate_config(config)
    assert any("ChrootDirectory invalide" in e for e in errors)


# ---------------------------------------------------------------------------
# Generation client
# ---------------------------------------------------------------------------
def test_client_config_declares_each_host():
    config = generate_client_config(get_preset("acces-bastion"))
    assert "Host bastion" in config
    assert "Host app-01" in config
    assert "HostName 10.0.1.11" in config


def test_client_config_puts_wildcard_block_last():
    config = generate_client_config(get_preset("poste-de-travail"))
    # OpenSSH garde la premiere valeur trouvee : 'Host *' doit venir en dernier.
    assert config.index("Host *") > config.index("Host prod-web")


def test_client_config_formats_local_forward_for_a_config_file():
    config = generate_client_config(get_preset("acces-bastion"))
    # Dans un fichier de config, LocalForward prend un espace, pas un ':'
    assert "LocalForward 5432 localhost:5432" in config


def test_client_config_handles_four_field_forward():
    config = generate_client_config({
        "preset": "custom",
        "role": "client",
        "hosts": [{
            "alias": "db",
            "hostname": "10.0.0.1",
            "local_forwards": ["127.0.0.1:5432:db.interne:5432"],
        }],
    })
    assert "LocalForward 127.0.0.1:5432 db.interne:5432" in config


def test_client_config_omits_default_port():
    config = generate_client_config({
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "web", "hostname": "example.com", "port": 22}],
    })
    assert "Port 22" not in config


def test_client_config_keeps_custom_port():
    config = generate_client_config({
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "web", "hostname": "example.com", "port": 2222}],
    })
    assert "Port 2222" in config


def test_client_config_adds_identities_only_with_identity_file():
    config = generate_client_config({
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "web", "hostname": "example.com", "identity_file": "~/.ssh/id_ed25519"}],
    })
    assert "IdentityFile ~/.ssh/id_ed25519" in config
    assert "IdentitiesOnly yes" in config


def test_client_config_dynamic_forward():
    config = generate_client_config(get_preset("tunnels"))
    assert "DynamicForward 1080" in config
    assert "ExitOnForwardFailure yes" in config


# ---------------------------------------------------------------------------
# Generation serveur
# ---------------------------------------------------------------------------
def test_sshd_config_hardening_defaults():
    conf = generate_sshd_config(get_preset("serveur-durci"))
    assert "PermitRootLogin no" in conf
    assert "PasswordAuthentication no" in conf
    assert "PubkeyAuthentication yes" in conf
    assert "MaxAuthTries 3" in conf


def test_sshd_config_lists_allowed_groups():
    conf = generate_sshd_config(get_preset("serveur-durci"))
    assert "AllowGroups ssh-users" in conf


def test_sshd_config_modern_crypto_excludes_weak_algorithms():
    conf = generate_sshd_config(get_preset("serveur-durci"))
    assert "Ciphers " in conf
    assert "cbc" not in conf
    assert "sha1" not in conf


def test_sshd_config_without_modern_crypto_omits_algorithms():
    config = get_preset("serveur-durci")
    config["modern_crypto"] = False
    conf = generate_sshd_config(config)
    assert "Ciphers " not in conf
    assert "KexAlgorithms " not in conf


def test_sshd_config_bastion_allows_forwarding():
    conf = generate_sshd_config(get_preset("bastion"))
    assert "AllowTcpForwarding yes" in conf


def test_sshd_config_sftp_match_block_is_last():
    conf = generate_sshd_config(get_preset("sftp-only"))
    assert "Match Group sftponly" in conf
    assert "ForceCommand internal-sftp" in conf
    # Tout ce qui suit un Match lui appartient : rien de global apres.
    after_match = conf.split("Match Group sftponly", 1)[1]
    for line in after_match.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert line.startswith("    "), f"directive globale apres le Match : {line}"


def test_sshd_config_banner_only_when_asked():
    with_banner = generate_sshd_config(get_preset("serveur-durci"))
    assert "Banner /etc/issue.net" in with_banner

    config = get_preset("serveur-durci")
    config["banner"] = ""
    assert "Banner " not in generate_sshd_config(config)


def test_sshd_config_custom_port():
    config = get_preset("serveur-durci")
    config["port"] = 2222
    assert "Port 2222" in generate_sshd_config(config)


# ---------------------------------------------------------------------------
# authorized_keys
# ---------------------------------------------------------------------------
def test_authorized_keys_applies_from_and_command():
    content = generate_authorized_keys([{
        "comment": "runner CI",
        "key": "ssh-ed25519 AAAAC3Nza ci@runner",
        "from": ["203.0.113.0/24", "198.51.100.7"],
        "command": "/usr/local/bin/deploy.sh",
        "restrict": True,
    }])
    assert 'from="203.0.113.0/24,198.51.100.7"' in content
    assert 'command="/usr/local/bin/deploy.sh"' in content
    assert "restrict" in content


def test_authorized_keys_restrict_replaces_individual_flags():
    content = generate_authorized_keys([{
        "key": "ssh-ed25519 AAAAC3Nza tom@laptop",
        "restrict": True,
        "no_pty": True,
    }])
    # 'restrict' couvre deja no-pty : pas de doublon.
    assert "no-pty" not in content


def test_authorized_keys_individual_flags_without_restrict():
    content = generate_authorized_keys([{
        "key": "ssh-ed25519 AAAAC3Nza tom@laptop",
        "no_agent_forwarding": True,
        "no_x11_forwarding": True,
    }])
    assert "no-agent-forwarding" in content
    assert "no-X11-forwarding" in content


def test_authorized_keys_bare_key_has_no_options():
    content = generate_authorized_keys([{"key": "ssh-ed25519 AAAAC3Nza tom@laptop"}])
    key_line = [ln for ln in content.splitlines() if ln.startswith("ssh-ed25519")][0]
    assert key_line == "ssh-ed25519 AAAAC3Nza tom@laptop"


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------
def test_generate_ssh_client_returns_single_file():
    files = generate_ssh(get_preset("poste-de-travail"))
    assert set(files) == {CLIENT_CONFIG_NAME}


def test_generate_ssh_server_returns_fragment():
    files = generate_ssh(get_preset("serveur-durci"))
    assert set(files) == {SSHD_FRAGMENT_NAME}


def test_generate_ssh_server_adds_authorized_keys_when_present():
    files = generate_ssh(get_preset("cle-restreinte"))
    assert set(files) == {SSHD_FRAGMENT_NAME, AUTHORIZED_KEYS_NAME}


def test_generate_ssh_invalid_config_raises():
    try:
        generate_ssh({"preset": "custom", "role": "client", "hosts": []})
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass


def test_sshd_fragment_name_sorts_before_distro_fragments():
    # sshd garde la PREMIERE valeur lue dans sshd_config.d/ : le fragment
    # doit passer avant les 50-*.conf des distributions.
    name = SSHD_FRAGMENT_NAME.split("/")[-1]
    assert name < "50-cloud-init.conf"
