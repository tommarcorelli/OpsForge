"""Tests de write_files, la fonction d'ecriture disque du module monitoring
(non couverte jusqu'ici) : genere prometheus.yml / alertes / datasources
Grafana et les ecrit sur disque."""

import os

from modules.monitoring.core import write_files, generate_files


def _prom_cfg(**overrides):
    cfg = {
        "mode": "prometheus",
        "jobs": [{"job_name": "node", "targets": ["localhost:9100"]}],
    }
    cfg.update(overrides)
    return cfg


def _alerts_cfg(**overrides):
    cfg = {
        "mode": "alerts",
        "rules": ["instance_down", "high_cpu"],
    }
    cfg.update(overrides)
    return cfg


def test_write_files_ecrit_tous_les_fichiers_prometheus(tmp_path):
    chemins = write_files(_prom_cfg(), str(tmp_path))

    attendu = generate_files(_prom_cfg())
    assert len(chemins) == len(attendu)
    for chemin in chemins:
        assert os.path.isfile(chemin)


def test_write_files_contenu_identique_a_generate(tmp_path):
    chemins = write_files(_prom_cfg(), str(tmp_path))
    attendu = generate_files(_prom_cfg())

    for chemin in chemins:
        nom = os.path.basename(chemin)
        with open(chemin, encoding="utf-8") as f:
            assert f.read() == attendu[nom]


def test_write_files_cree_le_dossier_de_sortie(tmp_path):
    output_dir = tmp_path / "nouveau" / "dossier"
    chemins = write_files(_prom_cfg(), str(output_dir))
    assert output_dir.is_dir()
    assert len(chemins) > 0


def test_write_files_mode_alerts(tmp_path):
    chemins = write_files(_alerts_cfg(), str(tmp_path))
    assert len(chemins) > 0
    for chemin in chemins:
        assert os.path.isfile(chemin)
