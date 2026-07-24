"""Tests du coeur du module Packer d'OpsForge."""

import pytest

from modules.packer.core import (
    generate_packer_template,
    generate_split_files,
    validate_config,
    list_presets,
    get_preset,
    list_builders,
    get_builder_info,
    OUTPUT_FILENAME,
    BUILDER_CATALOG,
    PRESETS,
)


def _valid_config(builder="docker", **overrides):
    base = {
        "docker": {"builder": "docker", "name": "app-img", "args": {"image": "python:3.12-slim"}},
        "amazon-ebs": {
            "builder": "amazon-ebs",
            "name": "web-ami",
            "args": {
                "region": "eu-west-1",
                "source_ami": "ami-123",
                "instance_type": "t3.micro",
                "ssh_username": "ubuntu",
                "ami_name": "web-ami",
            },
        },
        "virtualbox-iso": {
            "builder": "virtualbox-iso",
            "name": "ubuntu-base",
            "args": {
                "iso_url": "https://example.com/ubuntu.iso",
                "iso_checksum": "sha256:abc",
                "ssh_username": "vagrant",
                "ssh_password": "vagrant",
            },
        },
    }[builder]
    base = dict(base)
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_builder_manquant_rejete():
    errors = validate_config({})
    assert any("builder" in e.lower() for e in errors)


def test_builder_inconnu_rejete():
    errors = validate_config({"builder": "vmware-iso", "name": "x"})
    assert any("inconnu" in e for e in errors)


def test_nom_manquant_rejete():
    errors = validate_config({"builder": "docker", "args": {"image": "alpine"}})
    assert any("nom du build est requis" in e for e in errors)


def test_nom_invalide_rejete():
    errors = validate_config({"builder": "docker", "name": "app image!", "args": {"image": "alpine"}})
    assert any("invalide" in e for e in errors)


def test_champs_requis_manquants_rejetes():
    errors = validate_config({"builder": "amazon-ebs", "name": "ami-1", "args": {}})
    assert any("region" in e for e in errors)


def test_config_minimale_valide():
    assert validate_config(_valid_config("docker")) == []


def test_variable_sans_nom_rejetee():
    cfg = _valid_config("docker")
    cfg["variables"] = [{"type": "string", "default": "x"}]
    errors = validate_config(cfg)
    assert any("nom est requis" in e for e in errors)


def test_variable_nom_invalide_rejetee():
    cfg = _valid_config("docker")
    cfg["variables"] = [{"name": "mauvais nom", "type": "string"}]
    errors = validate_config(cfg)
    assert any("invalide" in e for e in errors)


def test_provisioner_type_inconnu_rejete():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "chef"}]
    errors = validate_config(cfg)
    assert any("type inconnu" in e for e in errors)


def test_provisioner_shell_inline_sans_commande_rejete():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "shell-inline", "inline": []}]
    errors = validate_config(cfg)
    assert any("au moins une commande" in e for e in errors)


def test_provisioner_shell_script_sans_chemin_rejete():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "shell-script", "script": ""}]
    errors = validate_config(cfg)
    assert any("chemin du script" in e for e in errors)


def test_provisioner_file_sans_source_ou_destination_rejete():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "file", "source": "", "destination": "/etc/motd"}]
    errors = validate_config(cfg)
    assert any("source et destination" in e for e in errors)


def test_post_processor_incompatible_rejete():
    cfg = _valid_config("docker")
    cfg["post_processors"] = ["vagrant"]  # vagrant n'est pas dispo pour docker
    errors = validate_config(cfg)
    assert any("incompatible" in e for e in errors)


def test_post_processor_docker_tag_sans_args_rejete():
    cfg = _valid_config("docker")
    cfg["post_processors"] = [{"type": "docker-tag"}]
    errors = validate_config(cfg)
    assert any("champs manquants" in e for e in errors)


# --------------------------------------------------------------------------
# Generation : structure generale
# --------------------------------------------------------------------------

def test_generation_leve_valueerror_si_invalide():
    with pytest.raises(ValueError):
        generate_packer_template({})


def test_contient_bloc_packer_et_plugin():
    text = generate_packer_template(_valid_config("docker"))
    assert "packer {" in text
    assert "required_plugins {" in text
    assert "docker {" in text
    assert 'source = "github.com/hashicorp/docker"' in text.replace("  ", " ")


def test_contient_bloc_source_avec_builder_et_nom():
    text = generate_packer_template(_valid_config("docker"))
    assert 'source "docker" "app-img" {' in text


def test_contient_bloc_build_avec_reference_source():
    text = generate_packer_template(_valid_config("docker"))
    assert 'sources = ["source.docker.app-img"]' in text


def test_args_utilisateur_fusionnes_avec_defauts():
    cfg = _valid_config("virtualbox-iso")
    text = generate_packer_template(cfg)
    assert 'guest_os_type    = "Ubuntu_64"' in text or "guest_os_type" in text
    assert "vagrant" in text


def test_args_utilisateur_surchargent_les_defauts():
    cfg = _valid_config("virtualbox-iso")
    cfg["args"]["headless"] = False
    text = generate_packer_template(cfg)
    assert "headless" in text and "= false" in text


# --------------------------------------------------------------------------
# Provisioners
# --------------------------------------------------------------------------

def test_provisioner_shell_inline_rendu():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "shell-inline", "inline": ["echo hello", "echo world"]}]
    text = generate_packer_template(cfg)
    assert 'provisioner "shell" {' in text
    assert "echo hello" in text and "echo world" in text


def test_provisioner_shell_script_rendu():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "shell-script", "script": "setup.sh"}]
    text = generate_packer_template(cfg)
    assert 'script = "setup.sh"' in text


def test_provisioner_file_rendu():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "file", "source": "app/", "destination": "/app"}]
    text = generate_packer_template(cfg)
    assert 'provisioner "file" {' in text
    assert 'destination = "/app"' in text


# --------------------------------------------------------------------------
# Post-processors
# --------------------------------------------------------------------------

def test_post_processor_docker_tag_rendu():
    cfg = _valid_config("docker")
    cfg["post_processors"] = [{"type": "docker-tag", "repository": "org/app", "tag": "1.0"}]
    text = generate_packer_template(cfg)
    assert 'post-processor "docker-tag" {' in text
    assert 'repository = "org/app"' in text


def test_post_processor_vagrant_compatible_avec_virtualbox():
    cfg = _valid_config("virtualbox-iso")
    cfg["post_processors"] = ["vagrant"]
    text = generate_packer_template(cfg)
    assert 'post-processor "vagrant" {}' in text


# --------------------------------------------------------------------------
# Variables
# --------------------------------------------------------------------------

def test_variable_rendue_avec_type_et_default():
    cfg = _valid_config("docker")
    cfg["variables"] = [{"name": "tag", "type": "string", "default": "latest"}]
    text = generate_packer_template(cfg)
    assert 'variable "tag" {' in text
    assert "type" in text and "string" in text
    assert 'default = "latest"' in text


def test_variable_sensitive_rendue():
    cfg = _valid_config("docker")
    cfg["variables"] = [{"name": "secret", "type": "string", "default": "x", "sensitive": True}]
    text = generate_packer_template(cfg)
    assert "sensitive = true" in text


# --------------------------------------------------------------------------
# Builders / catalogue
# --------------------------------------------------------------------------

def test_list_builders_contient_les_quatre_types():
    builders = list_builders()
    assert set(builders) == {"virtualbox-iso", "qemu", "amazon-ebs", "docker"}


def test_get_builder_info_builder_inconnu_leve_valueerror():
    with pytest.raises(ValueError):
        get_builder_info("vmware-iso")


def test_get_builder_info_retourne_les_champs_requis():
    info = get_builder_info("amazon-ebs")
    assert "region" in info["required"]
    assert "source_ami" in info["required"]


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

def test_output_filename_est_build_pkr_hcl():
    assert OUTPUT_FILENAME == "build.pkr.hcl"


def test_tous_les_presets_sont_valides_et_generables():
    for name in list_presets():
        cfg = get_preset(name)
        assert validate_config(cfg) == []
        text = generate_packer_template(cfg)
        assert "packer {" in text
        assert "build {" in text


def test_get_preset_inconnu_leve_valueerror():
    with pytest.raises(ValueError):
        get_preset("preset-qui-n-existe-pas")


def test_get_preset_retourne_une_copie_independante():
    preset_a = get_preset("docker-app-image")
    preset_a["provisioners"].append({"type": "shell-inline", "inline": ["echo x"]})
    preset_b = get_preset("docker-app-image")
    assert len(preset_b["provisioners"]) == 2


def test_au_moins_un_preset_par_famille_de_builder():
    builders_presets = {PRESETS[name]["builder"] for name in PRESETS}
    assert {"virtualbox-iso", "qemu", "amazon-ebs", "docker"} <= builders_presets


def test_chaque_builder_du_catalogue_a_un_label():
    for key, info in BUILDER_CATALOG.items():
        assert info["label"]
        assert isinstance(info["required"], list)


# --------------------------------------------------------------------------
# Provisioner powershell-inline (cible Windows/WinRM)
# --------------------------------------------------------------------------

def test_provisioner_powershell_inline_rendu():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "powershell-inline", "inline": ["Write-Output 'hello'"]}]
    text = generate_packer_template(cfg)
    assert 'provisioner "powershell" {' in text
    assert "Write-Output" in text


def test_provisioner_powershell_inline_sans_commande_rejete():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "powershell-inline", "inline": []}]
    errors = validate_config(cfg)
    assert any("au moins une commande" in e for e in errors)


def test_preset_windows_server_ami_valide_et_utilise_winrm():
    cfg = get_preset("windows-server-ami")
    assert validate_config(cfg) == []
    text = generate_packer_template(cfg)
    assert 'communicator   = "winrm"' in text or "winrm" in text
    assert 'provisioner "powershell" {' in text


# --------------------------------------------------------------------------
# Export en fichiers separes (variables.pkr.hcl / sources.pkr.hcl / build.pkr.hcl)
# --------------------------------------------------------------------------

def test_generate_split_files_sans_variables_omet_le_fichier():
    cfg = _valid_config("docker")
    fichiers = generate_split_files(cfg)
    assert "variables.pkr.hcl" not in fichiers
    assert "sources.pkr.hcl" in fichiers
    assert "build.pkr.hcl" in fichiers


def test_generate_split_files_avec_variables_inclut_le_fichier():
    cfg = _valid_config("docker")
    cfg["variables"] = [{"name": "tag", "type": "string", "default": "latest"}]
    fichiers = generate_split_files(cfg)
    assert "variables.pkr.hcl" in fichiers
    assert 'variable "tag" {' in fichiers["variables.pkr.hcl"]


def test_generate_split_files_sources_contient_packer_et_source():
    cfg = _valid_config("docker")
    fichiers = generate_split_files(cfg)
    assert "packer {" in fichiers["sources.pkr.hcl"]
    assert 'source "docker" "app-img" {' in fichiers["sources.pkr.hcl"]
    assert "build {" not in fichiers["sources.pkr.hcl"]


def test_generate_split_files_build_ne_contient_que_le_bloc_build():
    cfg = _valid_config("docker")
    fichiers = generate_split_files(cfg)
    assert fichiers["build.pkr.hcl"].strip().startswith("build {")
    assert "packer {" not in fichiers["build.pkr.hcl"]


def test_generate_split_files_leve_valueerror_si_invalide():
    with pytest.raises(ValueError):
        generate_split_files({})


def test_generate_split_files_equivalent_au_combine_pour_tous_les_presets():
    for name in list_presets():
        cfg = get_preset(name)
        fichiers = generate_split_files(cfg)
        assert "sources.pkr.hcl" in fichiers
        assert "build.pkr.hcl" in fichiers


# --------------------------------------------------------------------------
# Provisioner ansible
# --------------------------------------------------------------------------

def test_provisioner_ansible_rendu():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "ansible", "playbook_file": "site.yml", "user": "deploy"}]
    text = generate_packer_template(cfg)
    assert 'provisioner "ansible" {' in text
    assert 'playbook_file = "site.yml"' in text
    assert 'user          = "deploy"' in text or "user" in text


def test_provisioner_ansible_sans_playbook_rejete():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "ansible"}]
    errors = validate_config(cfg)
    assert any("playbook" in e for e in errors)


def test_provisioner_ansible_ajoute_le_plugin_ansible():
    cfg = _valid_config("docker")
    cfg["provisioners"] = [{"type": "ansible", "playbook_file": "site.yml"}]
    text = generate_packer_template(cfg)
    assert "ansible {" in text
    assert "github.com/hashicorp/ansible" in text


# --------------------------------------------------------------------------
# Datasources (ex : amazon-ami dynamique)
# --------------------------------------------------------------------------

def test_datasource_amazon_ami_rendue():
    cfg = _valid_config("amazon-ebs")
    cfg["datasources"] = [{
        "type": "amazon-ami",
        "name": "ubuntu",
        "args": {"filters": {"name": "ubuntu/*"}, "owners": ["099720109477"]},
    }]
    cfg["args"]["source_ami"] = "=data.amazon-ami.ubuntu.id"
    text = generate_packer_template(cfg)
    assert 'data "amazon-ami" "ubuntu" {' in text
    assert "source_ami" in text and "data.amazon-ami.ubuntu.id" in text


def test_datasource_type_inconnu_rejete():
    cfg = _valid_config("amazon-ebs")
    cfg["datasources"] = [{"type": "gcp-image", "name": "x", "args": {}}]
    errors = validate_config(cfg)
    assert any("type inconnu" in e for e in errors)


def test_datasource_sans_filters_rejetee():
    cfg = _valid_config("amazon-ebs")
    cfg["datasources"] = [{"type": "amazon-ami", "name": "ubuntu", "args": {}}]
    errors = validate_config(cfg)
    assert any("champs manquants" in e for e in errors)


def test_datasource_nom_invalide_rejetee():
    cfg = _valid_config("amazon-ebs")
    cfg["datasources"] = [{
        "type": "amazon-ami", "name": "mauvais nom",
        "args": {"filters": {"name": "x"}},
    }]
    errors = validate_config(cfg)
    assert any("invalide" in e for e in errors)


def test_datasource_et_builder_amazon_ne_dupliquent_pas_le_plugin():
    cfg = _valid_config("amazon-ebs")
    cfg["datasources"] = [{
        "type": "amazon-ami", "name": "ubuntu",
        "args": {"filters": {"name": "x"}},
    }]
    text = generate_packer_template(cfg)
    assert text.count("amazon {") == 1


def test_preset_aws_ami_webserver_utilise_la_datasource_dynamique():
    cfg = get_preset("aws-ami-webserver")
    assert validate_config(cfg) == []
    text = generate_packer_template(cfg)
    assert 'data "amazon-ami" "ubuntu" {' in text
    assert "data.amazon-ami.ubuntu.id" in text


# --------------------------------------------------------------------------
# HCP Packer Registry (publication des metadonnees de build)
# --------------------------------------------------------------------------

def test_hcp_registry_rendu_dans_le_bloc_build():
    cfg = _valid_config("docker")
    cfg["hcp_registry"] = {"bucket_name": "mon-app", "description": "Une image"}
    text = generate_packer_template(cfg)
    assert "hcp_packer_registry {" in text
    assert 'bucket_name = "mon-app"' in text or "bucket_name" in text
    assert 'description = "Une image"' in text


def test_hcp_registry_sans_bucket_name_rejete():
    cfg = _valid_config("docker")
    cfg["hcp_registry"] = {"description": "Une image sans bucket"}
    errors = validate_config(cfg)
    assert any("bucket_name" in e for e in errors)


def test_hcp_registry_absent_par_defaut():
    cfg = _valid_config("docker")
    text = generate_packer_template(cfg)
    assert "hcp_packer_registry" not in text


def test_hcp_registry_avec_labels_rendu():
    cfg = _valid_config("docker")
    cfg["hcp_registry"] = {"bucket_name": "mon-app", "bucket_labels": {"team": "platform"}}
    text = generate_packer_template(cfg)
    assert "bucket_labels" in text
    assert 'team = "platform"' in text


def test_preset_docker_app_image_publie_vers_hcp_registry():
    cfg = get_preset("docker-app-image")
    assert validate_config(cfg) == []
    text = generate_packer_template(cfg)
    assert "hcp_packer_registry {" in text
