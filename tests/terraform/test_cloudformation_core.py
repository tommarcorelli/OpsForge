"""
test_cloudformation_core.py
----------------------------
Tests unitaires pour modules/terraform/cloudformation_core.py.

Lancer avec : pytest tests/terraform/test_cloudformation_core.py -v
"""

import pytest
import yaml

from modules.terraform.cloudformation_core import (
    generate_cloudformation,
    valider_config,
    obtenir_preset,
    PRESETS,
    RESOURCE_CATALOG,
)


class _TagTolerantLoader(yaml.SafeLoader):
    """Loader qui accepte les tags CFN (!Ref, !GetAtt...) comme des scalaires
    / sequences / mappings ordinaires, uniquement pour verifier que le YAML
    genere est structurellement valide (safe_load seul rejette les tags
    inconnus, ce qui est le comportement normal d'un parseur YAML generique)."""


def _any_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_TagTolerantLoader.add_multi_constructor("!", _any_tag)


def _parse(yaml_text):
    return yaml.load(yaml_text, Loader=_TagTolerantLoader)


def _valid_config(**overrides):
    config = {
        "resources": [
            {"type": "AWS::S3::Bucket", "name": "SiteBucket",
             "properties": {"BucketName": "mon-bucket-123"}},
        ],
    }
    config.update(overrides)
    return config


def test_no_resources_still_generates_skeleton():
    text = generate_cloudformation({})
    parsed = _parse(text)
    assert parsed["AWSTemplateFormatVersion"] == "2010-09-09"
    assert parsed["Resources"] == {}


def test_basic_resource_generates_valid_yaml():
    config = _valid_config()
    text = generate_cloudformation(config)
    parsed = _parse(text)

    assert "SiteBucket" in parsed["Resources"]
    assert parsed["Resources"]["SiteBucket"]["Type"] == "AWS::S3::Bucket"
    assert parsed["Resources"]["SiteBucket"]["Properties"]["BucketName"] == "mon-bucket-123"


def test_missing_required_property_raises_valueerror():
    config = {
        "resources": [
            {"type": "AWS::EC2::Instance", "name": "Web", "properties": {"ImageId": "ami-123"}},
        ],
    }
    with pytest.raises(ValueError, match="InstanceType"):
        generate_cloudformation(config)


def test_missing_name_is_an_error():
    erreurs, _ = valider_config({"resources": [{"type": "AWS::S3::Bucket", "properties": {}}]})
    assert any("name" in e for e in erreurs)


def test_invalid_logical_id_is_an_error():
    erreurs, _ = valider_config({
        "resources": [{"type": "AWS::S3::Bucket", "name": "site-bucket", "properties": {}}],
    })
    assert any("identifiant logique" in e for e in erreurs)


def test_duplicate_logical_id_is_an_error():
    erreurs, _ = valider_config({
        "resources": [
            {"type": "AWS::S3::Bucket", "name": "Bucket1", "properties": {"BucketName": "a"}},
            {"type": "AWS::S3::Bucket", "name": "Bucket1", "properties": {"BucketName": "b"}},
        ],
    })
    assert any("double" in e for e in erreurs)


def test_unknown_type_is_a_warning_not_an_error():
    erreurs, avertissements = valider_config({
        "resources": [{"type": "AWS::Made::Up", "name": "Thing", "properties": {}}],
    })
    assert erreurs == []
    assert any("non catalogue" in a for a in avertissements)
    # Genere quand meme, sans lever d'exception
    text = generate_cloudformation({
        "resources": [{"type": "AWS::Made::Up", "name": "Thing", "properties": {"X": "y"}}],
    })
    assert "AWS::Made::Up" in text


def test_ref_intrinsic_rendered_unquoted():
    config = {
        "resources": [
            {"type": "AWS::EC2::VPC", "name": "MainVPC", "properties": {"CidrBlock": "10.0.0.0/16"}},
            {"type": "AWS::EC2::Subnet", "name": "SubA", "properties": {
                "VpcId": "=!Ref MainVPC", "CidrBlock": "10.0.1.0/24"}},
        ],
    }
    text = generate_cloudformation(config)
    assert "!Ref MainVPC" in text
    assert "'!Ref MainVPC'" not in text
    assert "!Ref 'MainVPC'" not in text


def test_getatt_intrinsic_in_outputs():
    config = _valid_config(outputs={"BucketArn": {"Value": "=!GetAtt SiteBucket.Arn"}})
    text = generate_cloudformation(config)
    parsed = _parse(text)

    assert "!GetAtt SiteBucket.Arn" in text
    assert parsed["Outputs"]["BucketArn"]["Value"] == "SiteBucket.Arn"


def test_parameters_section_included_when_present():
    config = _valid_config(parameters={"Env": {"Type": "String", "Default": "prod"}})
    text = generate_cloudformation(config)
    parsed = _parse(text)

    assert parsed["Parameters"]["Env"]["Default"] == "prod"


def test_parameters_section_omitted_when_absent():
    text = generate_cloudformation(_valid_config())
    assert "Parameters:" not in text


def test_nested_iam_policy_document_rendered_as_native_yaml():
    """CloudFormation accepte les policy documents en YAML natif (pas besoin
    d'un equivalent a jsonencode() comme cote Terraform)."""
    config = {
        "resources": [
            {"type": "AWS::IAM::Role", "name": "AppRole", "properties": {
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole"}],
                },
            }},
        ],
    }
    text = generate_cloudformation(config)
    parsed = _parse(text)

    doc = parsed["Resources"]["AppRole"]["Properties"]["AssumeRolePolicyDocument"]
    assert doc["Version"] == "2012-10-17"
    assert doc["Statement"][0]["Effect"] == "Allow"


def test_all_presets_generate_valid_yaml():
    for name in PRESETS:
        config = obtenir_preset(name)
        text = generate_cloudformation(config)
        parsed = _parse(text)
        assert parsed["Resources"], f"preset {name} devrait generer au moins une ressource"


def test_obtenir_preset_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        obtenir_preset("ne-existe-pas")


def test_obtenir_preset_does_not_mutate_original():
    cfg = obtenir_preset("s3-static")
    cfg["resources"].append({"type": "AWS::S3::Bucket", "name": "Extra", "properties": {}})
    cfg2 = obtenir_preset("s3-static")
    assert len(cfg2["resources"]) == 1


def test_resource_catalog_entries_have_required_keys():
    for entry in RESOURCE_CATALOG:
        assert "type" in entry
        assert "label" in entry
        assert "required" in entry
        assert "template" in entry
        assert entry["type"].startswith("AWS::")
