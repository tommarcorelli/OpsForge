"""Tests des fonctions d'ecriture disque du module Terraform (non couvertes
jusqu'ici) : write_terraform (fichier unique) et write_terraform_files
(projet en fichiers separes : main.tf, variables.tf, outputs.tf)."""

import os

from modules.terraform.core import (
    generate_terraform,
    generate_terraform_files,
    write_terraform,
    write_terraform_files,
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


# --------------------------------------------------------------------------
# write_terraform (fichier unique)
# --------------------------------------------------------------------------

def test_write_terraform_ecrit_le_fichier(tmp_path):
    output_path = tmp_path / "main.tf"
    resultat = write_terraform(_cfg(), str(output_path))

    assert resultat == str(output_path)
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == generate_terraform(_cfg())


def test_write_terraform_cree_les_dossiers_manquants(tmp_path):
    output_path = tmp_path / "infra" / "aws" / "main.tf"
    write_terraform(_cfg(), str(output_path))
    assert output_path.exists()


# --------------------------------------------------------------------------
# write_terraform_files (projet en fichiers separes)
# --------------------------------------------------------------------------

def test_write_terraform_files_ecrit_tous_les_fichiers(tmp_path):
    chemins = write_terraform_files(_cfg(), str(tmp_path))

    attendu = generate_terraform_files(_cfg())
    assert len(chemins) == len(attendu)
    for chemin in chemins:
        assert os.path.isfile(chemin)


def test_write_terraform_files_contenu_identique_a_generate(tmp_path):
    chemins = write_terraform_files(_cfg(), str(tmp_path))
    attendu = generate_terraform_files(_cfg())

    for chemin in chemins:
        nom = os.path.basename(chemin)
        with open(chemin, encoding="utf-8") as f:
            assert f.read() == attendu[nom]


def test_write_terraform_files_cree_le_dossier_de_sortie(tmp_path):
    output_dir = tmp_path / "nouveau" / "dossier"
    chemins = write_terraform_files(_cfg(), str(output_dir))
    assert output_dir.is_dir()
    assert len(chemins) > 0
