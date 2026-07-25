"""Tests du module verif_box — comparaison du catalogue local à Vagrant Cloud.

Ce module fait des appels reseau (urllib) : tous les tests mockent
`urllib.request.urlopen` pour rester rapides, deterministes et hors-ligne.
"""

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modules.vagrant.core.verif_box import (
    recuperer_providers_distants,
    recuperer_versions_distantes,
    verifier_catalogue,
)


def _reponse_json(payload):
    """Construit un faux gestionnaire de contexte pour urlopen renvoyant du JSON."""
    reponse = MagicMock()
    reponse.read.return_value = json.dumps(payload).encode("utf-8")
    contexte = MagicMock()
    contexte.__enter__.return_value = reponse
    contexte.__exit__.return_value = False
    return contexte


# --------------------------------------------------------------------------
# recuperer_providers_distants
# --------------------------------------------------------------------------

def test_providers_distants_succes():
    payload = {
        "versions": [
            {"providers": [{"name": "virtualbox"}, {"name": "libvirt"}]},
            {"providers": [{"name": "vmware_desktop"}]},
        ]
    }
    with patch("urllib.request.urlopen", return_value=_reponse_json(payload)):
        providers, erreur = recuperer_providers_distants("debian/bookworm64")
    assert erreur is None
    assert providers == ["libvirt", "virtualbox", "vmware_desktop"]


def test_providers_distants_dedoublonne_entre_versions():
    payload = {
        "versions": [
            {"providers": [{"name": "virtualbox"}]},
            {"providers": [{"name": "virtualbox"}]},
        ]
    }
    with patch("urllib.request.urlopen", return_value=_reponse_json(payload)):
        providers, erreur = recuperer_providers_distants("debian/bookworm64")
    assert erreur is None
    assert providers == ["virtualbox"]


def test_providers_distants_aucune_version():
    with patch("urllib.request.urlopen", return_value=_reponse_json({"versions": []})):
        providers, erreur = recuperer_providers_distants("box/inconnue")
    assert erreur is None
    assert providers == []


def test_providers_distants_404():
    erreur_http = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=erreur_http):
        providers, erreur = recuperer_providers_distants("box/nexistepas")
    assert providers is None
    assert "404" in erreur
    assert "introuvable" in erreur


def test_providers_distants_erreur_http_generique():
    erreur_http = urllib.error.HTTPError("url", 500, "Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=erreur_http):
        providers, erreur = recuperer_providers_distants("box/x")
    assert providers is None
    assert "500" in erreur


def test_providers_distants_reseau_indisponible():
    erreur_reseau = urllib.error.URLError("timed out")
    with patch("urllib.request.urlopen", side_effect=erreur_reseau):
        providers, erreur = recuperer_providers_distants("box/x")
    assert providers is None
    assert "réseau indisponible" in erreur


def test_providers_distants_timeout():
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        providers, erreur = recuperer_providers_distants("box/x")
    assert providers is None
    assert "réseau indisponible" in erreur


def test_providers_distants_json_invalide():
    contexte = MagicMock()
    contexte.__enter__.return_value.read.return_value = b"pas du json"
    contexte.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=contexte):
        providers, erreur = recuperer_providers_distants("box/x")
    assert providers is None
    assert "JSON invalide" in erreur


# --------------------------------------------------------------------------
# recuperer_versions_distantes
# --------------------------------------------------------------------------

def test_versions_distantes_succes_ordre_conserve():
    payload = {"versions": [{"version": "12.20240905.1"}, {"version": "12.20240701.0"}]}
    with patch("urllib.request.urlopen", return_value=_reponse_json(payload)):
        versions, erreur = recuperer_versions_distantes("debian/bookworm64")
    assert erreur is None
    assert versions == ["12.20240905.1", "12.20240701.0"]


def test_versions_distantes_respecte_la_limite():
    payload = {"versions": [{"version": str(i)} for i in range(20)]}
    with patch("urllib.request.urlopen", return_value=_reponse_json(payload)):
        versions, erreur = recuperer_versions_distantes("box/x", limite=3)
    assert erreur is None
    assert len(versions) == 3


def test_versions_distantes_ignore_les_versions_sans_numero():
    payload = {"versions": [{"version": "1.0"}, {}, {"version": None}]}
    with patch("urllib.request.urlopen", return_value=_reponse_json(payload)):
        versions, erreur = recuperer_versions_distantes("box/x")
    assert erreur is None
    assert versions == ["1.0"]


def test_versions_distantes_404():
    erreur_http = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=erreur_http):
        versions, erreur = recuperer_versions_distantes("box/nexistepas")
    assert versions is None
    assert "404" in erreur


# --------------------------------------------------------------------------
# verifier_catalogue (agregation, sans reseau reel : on mocke la fonction
# d'appel HTTP sous-jacente plutot que urlopen, pour tester la logique pure)
# --------------------------------------------------------------------------

def test_verifier_catalogue_detecte_manquants_et_en_trop():
    box_providers = {
        "debian/bookworm64": ["virtualbox"],
        "generic/ubuntu2204": ["virtualbox", "libvirt"],
    }

    def fake_providers(nom_box, timeout=10):
        if nom_box == "debian/bookworm64":
            return (["virtualbox", "libvirt", "vmware_desktop"], None)
        return (["virtualbox"], None)

    with patch("modules.vagrant.core.verif_box.recuperer_providers_distants", side_effect=fake_providers):
        rapports = verifier_catalogue(box_providers)

    assert len(rapports) == 2

    debian = next(r for r in rapports if r["box"] == "debian/bookworm64")
    assert debian["manquants_localement"] == ["libvirt", "vmware_desktop"]
    assert debian["en_trop"] == []

    ubuntu = next(r for r in rapports if r["box"] == "generic/ubuntu2204")
    assert ubuntu["manquants_localement"] == []
    assert ubuntu["en_trop"] == ["libvirt"]


def test_verifier_catalogue_propage_les_erreurs_sans_planter():
    box_providers = {"box/cassee": ["virtualbox"]}

    def fake_providers(nom_box, timeout=10):
        return (None, "introuvable sur Vagrant Cloud (404) — box retirée ou renommée ?")

    with patch("modules.vagrant.core.verif_box.recuperer_providers_distants", side_effect=fake_providers):
        rapports = verifier_catalogue(box_providers)

    assert len(rapports) == 1
    assert rapports[0]["erreur"] is not None
    assert rapports[0]["distants"] is None
    assert rapports[0]["manquants_localement"] == []
    assert rapports[0]["en_trop"] == []


def test_verifier_catalogue_trie_par_nom_de_box():
    box_providers = {"z-box": ["virtualbox"], "a-box": ["virtualbox"]}

    with patch(
        "modules.vagrant.core.verif_box.recuperer_providers_distants",
        return_value=(["virtualbox"], None),
    ):
        rapports = verifier_catalogue(box_providers)

    assert [r["box"] for r in rapports] == ["a-box", "z-box"]


def test_verifier_catalogue_catalogue_vide():
    assert verifier_catalogue({}) == []
