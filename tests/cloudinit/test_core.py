"""Tests du coeur du module cloud-init d'OpsForge."""

import pytest
import yaml

from modules.cloudinit.core import (
    generate_cloud_config,
    validate_config,
    list_presets,
    get_preset,
    OUTPUT_FILENAME,
    PRESETS,
)


def _parse(text):
    """Retire la ligne #cloud-config et parse le YAML."""
    assert text.startswith("#cloud-config\n")
    return yaml.safe_load(text.split("\n", 1)[1])


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_config_vide_rejetee():
    errors = validate_config({})
    assert any("vide" in e for e in errors)


def test_user_sans_nom_rejete():
    errors = validate_config({"users": [{"groups": "sudo"}]})
    assert any("nom est requis" in e for e in errors)


def test_user_nom_invalide_rejete():
    errors = validate_config({"users": [{"name": "Jean Dupont"}]})
    assert any("invalide" in e for e in errors)


def test_write_file_sans_path_rejete():
    errors = validate_config({"write_files": [{"content": "x"}]})
    assert any("chemin" in e for e in errors)


def test_write_file_sans_contenu_rejete():
    errors = validate_config({"write_files": [{"path": "/etc/motd"}]})
    assert any("contenu" in e for e in errors)


def test_write_file_permissions_invalides_rejetees():
    errors = validate_config({"write_files": [{"path": "/x", "content": "y", "permissions": "999x"}]})
    assert any("permissions invalides" in e for e in errors)


def test_config_minimale_valide():
    assert validate_config({"hostname": "web-01"}) == []
    assert validate_config({"packages": ["nginx"]}) == []


# --------------------------------------------------------------------------
# Generation : structure + entete obligatoire
# --------------------------------------------------------------------------

def test_commence_par_cloud_config():
    text = generate_cloud_config({"hostname": "web-01"})
    assert text.startswith("#cloud-config\n")


def test_hostname_et_timezone():
    data = _parse(generate_cloud_config({"hostname": "web-01", "timezone": "Europe/Paris"}))
    assert data["hostname"] == "web-01"
    assert data["timezone"] == "Europe/Paris"


def test_toggles_paquets():
    data = _parse(generate_cloud_config({
        "hostname": "x", "package_update": True, "package_upgrade": True,
    }))
    assert data["package_update"] is True
    assert data["package_upgrade"] is True


def test_sections_vides_omises():
    data = _parse(generate_cloud_config({"hostname": "x"}))
    assert "users" not in data
    assert "packages" not in data
    assert "runcmd" not in data


# --------------------------------------------------------------------------
# Utilisateurs
# --------------------------------------------------------------------------

def test_user_sudo_devient_nopasswd():
    data = _parse(generate_cloud_config({"users": [{"name": "deploy", "sudo": True}]}))
    user = data["users"][0]
    assert user["name"] == "deploy"
    assert user["sudo"] == "ALL=(ALL) NOPASSWD:ALL"
    assert user["shell"] == "/bin/bash"


def test_user_groups_en_liste():
    data = _parse(generate_cloud_config({"users": [{"name": "d", "groups": "sudo, docker"}]}))
    assert data["users"][0]["groups"] == ["sudo", "docker"]


def test_user_avec_cle_ssh_verrouille_le_password():
    data = _parse(generate_cloud_config({
        "users": [{"name": "d", "ssh_authorized_keys": ["ssh-ed25519 AAAA"]}],
    }))
    user = data["users"][0]
    assert user["ssh_authorized_keys"] == ["ssh-ed25519 AAAA"]
    assert user["lock_passwd"] is True


def test_user_sans_sudo_omet_la_cle():
    data = _parse(generate_cloud_config({"users": [{"name": "d"}]}))
    assert "sudo" not in data["users"][0]


# --------------------------------------------------------------------------
# Paquets / commandes / fichiers
# --------------------------------------------------------------------------

def test_packages_depuis_liste():
    data = _parse(generate_cloud_config({"packages": ["nginx", "git"]}))
    assert data["packages"] == ["nginx", "git"]


def test_packages_depuis_chaine_multiligne():
    data = _parse(generate_cloud_config({"packages": "nginx\ngit\ncurl"}))
    assert data["packages"] == ["nginx", "git", "curl"]


def test_runcmd_present():
    data = _parse(generate_cloud_config({"runcmd": ["systemctl enable nginx"]}))
    assert data["runcmd"] == ["systemctl enable nginx"]


def test_write_files_normalise_permissions():
    data = _parse(generate_cloud_config({
        "write_files": [{"path": "/etc/motd", "content": "hello", "permissions": "644"}],
    }))
    wf = data["write_files"][0]
    assert wf["path"] == "/etc/motd"
    assert wf["content"] == "hello"
    assert wf["permissions"] == "0644"  # prefixe par un zero


def test_ssh_pwauth_et_disable_root():
    data = _parse(generate_cloud_config({"hostname": "x", "ssh_pwauth": False, "disable_root": True}))
    assert data["ssh_pwauth"] is False
    assert data["disable_root"] is True


# --------------------------------------------------------------------------
# Config invalide -> exception
# --------------------------------------------------------------------------

def test_generate_leve_valueerror_si_invalide():
    with pytest.raises(ValueError):
        generate_cloud_config({})


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

def test_output_filename_est_user_data():
    assert OUTPUT_FILENAME == "user-data"


def test_tous_les_presets_sont_valides_et_parsables():
    for name in list_presets():
        cfg = get_preset(name)
        assert validate_config(cfg) == []
        _parse(generate_cloud_config(cfg))  # doit parser sans lever


def test_get_preset_inconnu_leve_valueerror():
    with pytest.raises(ValueError):
        get_preset("preset-qui-n-existe-pas")


def test_get_preset_retourne_une_copie_independante():
    preset_a = get_preset("docker-host")
    preset_a["packages"].append("vim")
    preset_b = get_preset("docker-host")
    assert "vim" not in preset_b["packages"]


def test_preset_secure_baseline_durci():
    data = _parse(generate_cloud_config(get_preset("secure-baseline")))
    assert data["disable_root"] is True
    assert data["ssh_pwauth"] is False


def test_au_moins_un_preset_par_famille():
    assert "docker-host" in PRESETS
    assert "minimal" in PRESETS
