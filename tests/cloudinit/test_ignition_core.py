"""Tests du générateur Ignition (module cloud-init) d'OpsForge."""

import base64
import json

import pytest

from modules.cloudinit.ignition_core import (
    generate_ignition,
    generate_files,
    write_files,
    OUTPUT_FILENAME,
    IGNITION_VERSION,
    FIRSTBOOT_UNIT_NAME,
)
from modules.cloudinit.core import get_preset


def _parse(text):
    return json.loads(text)


def _decode_source(source):
    prefix = "base64,"
    assert prefix in source
    encoded = source.split(prefix, 1)[1]
    return base64.b64decode(encoded).decode("utf-8")


def test_config_vide_leve_une_erreur():
    with pytest.raises(ValueError):
        generate_ignition({})


def test_version_ignition_presente():
    doc = _parse(generate_ignition({"hostname": "srv-01"}))
    assert doc["ignition"]["version"] == IGNITION_VERSION


def test_hostname_ecrit_dans_storage_files():
    doc = _parse(generate_ignition({"hostname": "web-01"}))
    files = doc["storage"]["files"]
    hostname_file = next(f for f in files if f["path"] == "/etc/hostname")
    assert _decode_source(hostname_file["contents"]["source"]) == "web-01\n"
    assert hostname_file["mode"] == 420


def test_utilisateur_avec_cles_ssh_et_groupes():
    config = {
        "hostname": "srv-01",
        "users": [{
            "name": "core",
            "groups": "wheel, docker",
            "ssh_authorized_keys": ["ssh-ed25519 AAAA...test"],
        }],
    }
    doc = _parse(generate_ignition(config))
    user = doc["passwd"]["users"][0]
    assert user["name"] == "core"
    assert user["sshAuthorizedKeys"] == ["ssh-ed25519 AAAA...test"]
    assert user["groups"] == ["wheel", "docker"]


def test_pas_de_section_passwd_sans_utilisateur():
    doc = _parse(generate_ignition({"hostname": "srv-01"}))
    assert "passwd" not in doc


def test_write_files_encodes_en_base64():
    config = {
        "hostname": "srv-01",
        "write_files": [{"path": "/etc/motd", "content": "bienvenue\n", "permissions": "0600"}],
    }
    doc = _parse(generate_ignition(config))
    files = doc["storage"]["files"]
    motd = next(f for f in files if f["path"] == "/etc/motd")
    assert _decode_source(motd["contents"]["source"]) == "bienvenue\n"
    assert motd["mode"] == 0o600


def test_runcmd_devient_unite_systemd_oneshot():
    config = {"hostname": "srv-01", "runcmd": ["systemctl enable --now nginx"]}
    doc = _parse(generate_ignition(config))
    units = doc["systemd"]["units"]
    assert len(units) == 1
    unit = units[0]
    assert unit["name"] == FIRSTBOOT_UNIT_NAME
    assert unit["enabled"] is True
    assert "Type=oneshot" in unit["contents"]
    assert 'ExecStart=/bin/bash -c "systemctl enable --now nginx"' in unit["contents"]
    assert "ExecStartPost" not in unit["contents"]  # pas de paquets => pas de reboot


def test_packages_installes_via_rpm_ostree_et_reboot():
    config = {"hostname": "srv-01", "packages": ["nginx", "htop"]}
    doc = _parse(generate_ignition(config))
    unit = doc["systemd"]["units"][0]
    assert "rpm-ostree install -y --idempotent --allow-inactive nginx htop" in unit["contents"]
    assert "ExecStartPost=/bin/systemctl reboot" in unit["contents"]


def test_pas_d_unite_systemd_sans_packages_ni_runcmd():
    doc = _parse(generate_ignition({"hostname": "srv-01"}))
    assert "systemd" not in doc


def test_generate_files_retourne_config_ign():
    files = generate_files({"hostname": "srv-01"})
    assert list(files.keys()) == [OUTPUT_FILENAME]
    _parse(files[OUTPUT_FILENAME])  # doit rester du JSON valide


def test_write_files_cree_le_fichier(tmp_path):
    paths = write_files({"hostname": "srv-01"}, str(tmp_path))
    assert len(paths) == 1
    content = open(paths[0], encoding="utf-8").read()
    _parse(content)


@pytest.mark.parametrize("preset_name", ["docker-host", "web-server", "secure-baseline", "minimal"])
def test_tous_les_presets_cloudinit_produisent_un_ignition_valide(preset_name):
    config = get_preset(preset_name)
    doc = _parse(generate_ignition(config))
    assert doc["ignition"]["version"] == IGNITION_VERSION
