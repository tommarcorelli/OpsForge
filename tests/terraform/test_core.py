"""Tests du cœur du module Terraform d'OpsForge."""

import pytest

from modules.terraform.core import (
    generate_terraform,
    valider_config,
    obtenir_preset,
    PRESETS,
    RESOURCE_CATALOG,
    SUPPORTED_PROVIDERS,
)


def _cfg(**over):
    base = {
        "provider": "aws",
        "provider_config": {"region": "eu-west-1"},
        "resources": [
            {"type": "aws_instance", "name": "web",
             "args": {"ami": "ami-0abc", "instance_type": "t3.micro"}}
        ],
    }
    base.update(over)
    return base


def test_generation_blocs_de_base():
    tf = generate_terraform(_cfg())
    assert "terraform {" in tf
    assert 'source  = "hashicorp/aws"' in tf
    assert 'provider "aws" {' in tf
    assert 'resource "aws_instance" "web" {' in tf
    assert tf.endswith("\n")


def test_alignement_des_egal():
    # Les '=' d'un même bloc doivent être alignés (façon terraform fmt).
    tf = generate_terraform(_cfg(resources=[
        {"type": "aws_instance", "name": "web",
         "args": {"ami": "ami-0abc", "instance_type": "t3.micro"}}
    ]))
    # 'ami' (3) est padué à la largeur de 'instance_type' (13)
    assert "ami           = " in tf
    assert "instance_type = " in tf


def test_reference_brute_sans_guillemets():
    tf = generate_terraform(_cfg(resources=[
        {"type": "aws_instance", "name": "web",
         "args": {"ami": "ami-0abc", "instance_type": "t3.micro",
                  "subnet_id": "=aws_subnet.a.id"}}
    ]))
    assert "subnet_id     = aws_subnet.a.id" in tf   # pas de guillemets
    assert 'ami           = "ami-0abc"' in tf         # chaîne normale : guillemets


def test_bloc_imbrique_tags():
    tf = generate_terraform(_cfg(resources=[
        {"type": "aws_instance", "name": "web",
         "args": {"ami": "a", "instance_type": "t", "tags": {"Name": "web"}}}
    ]))
    assert "tags          = {" in tf
    assert 'Name = "web"' in tf


def test_variables_et_outputs():
    tf = generate_terraform(_cfg(
        variables={"region": {"type": "=string", "default": "eu-west-1"}},
        outputs={"ip": {"value": "=aws_instance.web.public_ip"}},
    ))
    assert 'variable "region" {' in tf
    assert "type    = string" in tf
    assert 'output "ip" {' in tf
    assert "value = aws_instance.web.public_ip" in tf


def test_validation_argument_requis_manquant():
    erreurs, _ = valider_config(_cfg(resources=[
        {"type": "aws_instance", "name": "web", "args": {"ami": "a"}}  # manque instance_type
    ]))
    assert any("instance_type" in e for e in erreurs)


def test_validation_nom_manquant():
    erreurs, _ = valider_config(_cfg(resources=[
        {"type": "aws_instance", "args": {"ami": "a", "instance_type": "t"}}
    ]))
    assert any("name" in e.lower() for e in erreurs)


def test_validation_provider_manquant():
    erreurs, _ = valider_config({"resources": []})
    assert any("provider" in e.lower() for e in erreurs)


def test_provider_inconnu_avertit():
    _, avert = valider_config({"provider": "scaleway", "resources": []})
    assert any("scaleway" in a for a in avert)


def test_generation_leve_si_invalide():
    with pytest.raises(ValueError):
        generate_terraform({"provider": "aws", "resources": [
            {"type": "aws_instance", "name": "web", "args": {}}  # args requis manquants
        ]})


def test_tous_les_presets_generent():
    for nom in PRESETS:
        config = obtenir_preset(nom)
        erreurs, _ = valider_config(config)
        assert erreurs == [], f"Preset {nom} invalide : {erreurs}"
        tf = generate_terraform(config)
        assert "terraform {" in tf


def test_catalogue_coherent_avec_providers():
    for provider in RESOURCE_CATALOG:
        assert provider in SUPPORTED_PROVIDERS


def test_backend_distant_dans_bloc_terraform():
    tf = generate_terraform(_cfg(backend={
        "type": "s3",
        "config": {"bucket": "mon-tfstate", "key": "prod/terraform.tfstate", "region": "eu-west-1"},
    }))
    # Le bloc backend doit être DANS le bloc terraform {}
    debut = tf.index("terraform {")
    fin = tf.index("\n}", debut)
    bloc_terraform = tf[debut:fin]
    assert 'backend "s3" {' in bloc_terraform
    assert 'bucket = "mon-tfstate"' in tf


def test_nouveaux_types_aws_valides():
    for rtype in ("aws_vpc", "aws_subnet", "aws_db_instance"):
        entry = next(e for e in RESOURCE_CATALOG["aws"] if e["type"] == rtype)
        cfg = _cfg(resources=[{"type": rtype, "name": "x", "args": entry["template"]}])
        erreurs, _ = valider_config(cfg)
        assert erreurs == [], f"{rtype} : {erreurs}"
