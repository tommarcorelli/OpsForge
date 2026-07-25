"""Tests de write_config, la fonction d'ecriture disque du module nginx
(non couverte jusqu'ici) : genere une config nginx et l'ecrit sur disque."""

from modules.nginx.core import write_config, generate_config


def _static_cfg(**overrides):
    cfg = {
        "mode": "static",
        "server_name": "site.example.com",
        "root": "/var/www/site",
    }
    cfg.update(overrides)
    return cfg


def test_write_config_ecrit_le_fichier(tmp_path):
    output_path = tmp_path / "site.conf"
    resultat = write_config(_static_cfg(), str(output_path))

    assert resultat == str(output_path)
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == generate_config(_static_cfg())


def test_write_config_cree_les_dossiers_manquants(tmp_path):
    output_path = tmp_path / "etc" / "nginx" / "sites-available" / "site.conf"
    write_config(_static_cfg(), str(output_path))
    assert output_path.exists()


def test_write_config_sans_dossier_parent_fonctionne(monkeypatch, tmp_path):
    # output_path sans repertoire (os.path.dirname(...) == "") : la fonction
    # doit gerer ce cas sans planter (fallback sur ".").
    monkeypatch.chdir(tmp_path)
    resultat = write_config(_static_cfg(), "site.conf")
    assert resultat == "site.conf"
    assert (tmp_path / "site.conf").exists()
