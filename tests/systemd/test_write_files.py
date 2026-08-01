"""Tests de write_units, la fonction d'ecriture disque du module systemd
(non couverte jusqu'ici) : genere les unites systemd et les ecrit sur disque."""

import os

from modules.systemd.core import generate_units, write_units


def _service_cfg(**overrides):
    cfg = {
        "mode": "service",
        "name": "myapp",
        "exec_start": "/opt/myapp/bin/run",
    }
    cfg.update(overrides)
    return cfg


def test_write_units_ecrit_tous_les_fichiers(tmp_path):
    chemins = write_units(_service_cfg(), str(tmp_path))

    attendu = generate_units(_service_cfg())
    assert len(chemins) == len(attendu)
    for chemin in chemins:
        assert os.path.isfile(chemin)


def test_write_units_contenu_identique_a_generate(tmp_path):
    chemins = write_units(_service_cfg(), str(tmp_path))
    attendu = generate_units(_service_cfg())

    for chemin in chemins:
        nom = os.path.basename(chemin)
        with open(chemin, encoding="utf-8") as f:
            assert f.read() == attendu[nom]


def test_write_units_cree_le_dossier_de_sortie(tmp_path):
    output_dir = tmp_path / "nouveau" / "dossier"
    chemins = write_units(_service_cfg(), str(output_dir))
    assert output_dir.is_dir()
    assert len(chemins) > 0


def test_write_units_inclut_le_fichier_service(tmp_path):
    chemins = write_units(_service_cfg(), str(tmp_path))
    noms = {os.path.basename(c) for c in chemins}
    assert "myapp.service" in noms
