"""
test_pulumi_core.py
--------------------
Tests unitaires pour modules/terraform/pulumi_core.py.

Lancer avec : pytest tests/terraform/test_pulumi_core.py -v
"""

import ast

import pytest

from modules.terraform.pulumi_core import (
    generate_pulumi,
    valider_config,
    obtenir_preset,
    list_presets,
    PRESETS,
    RESOURCE_TYPE_MAP,
    PULUMI_PROVIDERS,
)


def _valid_config(**overrides):
    config = {
        "provider": "aws",
        "resources": [
            {"type": "aws_s3_bucket", "name": "site", "args": {"bucket": "mon-bucket-123"}},
        ],
    }
    config.update(overrides)
    return config


def test_no_provider_is_an_error():
    erreurs, _ = valider_config({"resources": []})
    assert any("provider" in e.lower() for e in erreurs)


def test_local_provider_explicitly_rejected():
    erreurs, _ = valider_config({"provider": "local", "resources": []})
    assert any("local" in e for e in erreurs)


def test_unknown_provider_is_an_error():
    erreurs, _ = valider_config({"provider": "made-up-cloud", "resources": []})
    assert any("made-up-cloud" in e for e in erreurs)


def test_no_resources_is_a_warning_not_an_error():
    erreurs, avertissements = valider_config({"provider": "aws", "resources": []})
    assert erreurs == []
    assert avertissements


def test_missing_name_is_an_error():
    erreurs, _ = valider_config({
        "provider": "aws",
        "resources": [{"type": "aws_s3_bucket", "args": {}}],
    })
    assert any("name" in e for e in erreurs)


def test_duplicate_type_and_name_is_an_error():
    erreurs, _ = valider_config({
        "provider": "aws",
        "resources": [
            {"type": "aws_s3_bucket", "name": "site", "args": {"bucket": "a"}},
            {"type": "aws_s3_bucket", "name": "site", "args": {"bucket": "b"}},
        ],
    })
    assert any("double" in e for e in erreurs)


def test_unmapped_resource_type_is_an_error():
    erreurs, _ = valider_config({
        "provider": "aws",
        "resources": [{"type": "aws_totally_unmapped_thing", "name": "x", "args": {}}],
    })
    assert any("aws_totally_unmapped_thing" in e for e in erreurs)


def test_generate_raises_on_invalid_config():
    with pytest.raises(ValueError):
        generate_pulumi({"provider": "local", "resources": []})


def test_basic_resource_generates_valid_python():
    config = _valid_config()
    text = generate_pulumi(config)
    ast.parse(text)  # leve SyntaxError si invalide

    assert "import pulumi_aws as aws" in text
    assert "aws_s3_bucket_site = aws.s3.Bucket(\"site\"," in text
    assert 'bucket=\'mon-bucket-123\'' in text


def test_var_name_avoids_collision_between_types_sharing_a_name():
    """Deux ressources de types differents peuvent partager le meme 'name'
    (valide cote builder partage) : les variables Python generees ne
    doivent pas entrer en collision."""
    config = {
        "provider": "aws",
        "resources": [
            {"type": "aws_security_group", "name": "web", "args": {"description": "sg"}},
            {"type": "aws_instance", "name": "web", "args": {
                "ami": "ami-123", "instance_type": "t3.micro",
                "vpc_security_group_ids": ["=aws_security_group_web.id"]}},
        ],
    }
    text = generate_pulumi(config)
    ast.parse(text)

    assert "aws_security_group_web = " in text
    assert "aws_instance_web = " in text
    assert "aws_security_group_web.id" in text


def test_reference_escape_hatch_emits_raw_python():
    config = _valid_config(
        resources=[
            {"type": "aws_vpc", "name": "main", "args": {"cidr_block": "10.0.0.0/16"}},
            {"type": "aws_subnet", "name": "public", "args": {
                "vpc_id": "=aws_vpc_main.id", "cidr_block": "10.0.1.0/24"}},
        ],
    )
    text = generate_pulumi(config)
    ast.parse(text)

    assert "vpc_id=aws_vpc_main.id," in text
    assert '"=aws_vpc_main.id"' not in text


def test_nested_dict_arg_renders_as_valid_python_dict():
    config = _valid_config(
        resources=[
            {"type": "aws_s3_bucket", "name": "site", "args": {
                "bucket": "x", "tags": {"Env": "prod", "Team": "infra"}}},
        ],
    )
    text = generate_pulumi(config)
    tree = ast.parse(text)
    assert isinstance(tree, ast.Module)
    assert '"Env": \'prod\'' in text
    assert '"Team": \'infra\'' in text


def test_list_of_dicts_arg_renders_as_valid_python():
    config = {
        "provider": "docker",
        "resources": [
            {"type": "docker_image", "name": "nginx", "args": {"name": "nginx:latest"}},
            {"type": "docker_container", "name": "web", "args": {
                "name": "web", "image": "=docker_image_nginx.image_id",
                "ports": [{"internal": 80, "external": 8080}]}},
        ],
    }
    text = generate_pulumi(config)
    ast.parse(text)
    assert '"internal": 80' in text
    assert '"external": 8080' in text


def test_bool_and_number_args_render_as_python_literals():
    config = _valid_config(
        resources=[
            {"type": "aws_s3_bucket", "name": "site", "args": {
                "bucket": "x", "force_destroy": True, "some_count": 3}},
        ],
    )
    text = generate_pulumi(config)
    ast.parse(text)
    assert "force_destroy=True," in text
    assert "some_count=3," in text


def test_outputs_generate_pulumi_export_calls():
    config = _valid_config(outputs={"bucket_arn": "=aws_s3_bucket_site.arn"})
    text = generate_pulumi(config)
    ast.parse(text)
    assert 'pulumi.export("bucket_arn", aws_s3_bucket_site.arn)' in text


def test_provider_config_emitted_as_comment_not_code():
    config = _valid_config(provider_config={"region": "eu-west-1"})
    text = generate_pulumi(config)
    ast.parse(text)
    assert "pulumi config set aws:region eu-west-1" in text
    # Le commentaire ne doit pas casser le parsing (deja verifie par ast.parse),
    # et ne doit pas apparaitre comme une ligne de code executable.
    assert "# pulumi config set aws:region eu-west-1" not in text  # precede de '#   '


def test_resource_without_args_still_generates_valid_call():
    config = _valid_config(resources=[{"type": "aws_s3_bucket", "name": "site", "args": {}}])
    text = generate_pulumi(config)
    ast.parse(text)
    assert 'aws_s3_bucket_site = aws.s3.Bucket("site")' in text


def test_all_presets_generate_valid_python():
    for name in PRESETS:
        config = obtenir_preset(name)
        text = generate_pulumi(config)
        ast.parse(text)


def test_list_presets_matches_dict_keys():
    assert set(list_presets()) == set(PRESETS.keys())


def test_obtenir_preset_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        obtenir_preset("ne-existe-pas")


def test_obtenir_preset_does_not_mutate_original():
    cfg = obtenir_preset("s3-static")
    cfg["resources"].append({"type": "aws_s3_bucket", "name": "extra", "args": {}})
    cfg2 = obtenir_preset("s3-static")
    assert len(cfg2["resources"]) == 1


def test_resource_type_map_only_covers_pulumi_providers():
    """local n'a pas de mapping (pas de paquet Pulumi officiel dedie)."""
    for (provider, _rtype) in RESOURCE_TYPE_MAP:
        assert provider in PULUMI_PROVIDERS
    assert "local" not in PULUMI_PROVIDERS


def test_google_and_docker_providers_generate_correct_import_alias():
    google_text = generate_pulumi({
        "provider": "google",
        "resources": [{"type": "google_storage_bucket", "name": "b", "args": {
            "name": "bucket", "location": "EU"}}],
    })
    ast.parse(google_text)
    assert "import pulumi_gcp as gcp" in google_text
    assert "gcp.storage.Bucket(" in google_text

    docker_text = generate_pulumi({
        "provider": "docker",
        "resources": [{"type": "docker_network", "name": "app", "args": {"name": "app-net"}}],
    })
    ast.parse(docker_text)
    assert "import pulumi_docker as docker" in docker_text
    assert "docker.Network(" in docker_text
