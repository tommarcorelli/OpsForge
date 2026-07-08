"""
modules/vagrant/routes.py
-------------------------
Blueprint Flask du module Vagrant (monte sous /vagrant).

Le frontend genere deja 100 % cote client (JS) ; cette API est un bonus
pour generer cote serveur ou scripter via HTTP (portee de VagrantForge).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.vagrant.core.generateur import construire_vagrantfile
from modules.vagrant.core.schema import valider_config, BOX_PROVIDERS
from modules.vagrant.core.presets import PRESETS, obtenir_preset
from modules.vagrant.core.lint import linter_vagrantfile
from modules.vagrant.core.verif_box import verifier_catalogue

bp = Blueprint("vagrant", __name__, url_prefix="/vagrant")


@bp.route("/")
def index():
    return render_template("vagrant.html")


@bp.get("/api/presets")
def api_presets():
    return jsonify({nom: desc for nom, (desc, _) in PRESETS.items()})


@bp.get("/api/preset/<nom>")
def api_preset(nom):
    sous_reseau = request.args.get("sous_reseau", "192.168.56")
    try:
        return jsonify(obtenir_preset(nom, sous_reseau))
    except KeyError:
        return jsonify({"erreur": f"Preset inconnu : {nom}"}), 404


@bp.post("/api/valider")
def api_valider():
    config = request.get_json(silent=True) or {}
    erreurs, avertissements = valider_config(config)
    return jsonify({"erreurs": erreurs, "avertissements": avertissements,
                    "valide": not erreurs})


@bp.post("/api/generer")
def api_generer():
    corps = request.get_json(silent=True) or {}
    # Retrocompatible : accepte soit la config JSON brute, soit
    # {"config": {...}, "gabarit": "texte optionnel"}.
    if "config" in corps and isinstance(corps.get("config"), dict):
        config = corps["config"]
        gabarit = corps.get("gabarit") or None
    else:
        config = corps
        gabarit = None

    erreurs, avertissements = valider_config(config)
    if erreurs and not request.args.get("forcer"):
        return jsonify({"erreurs": erreurs, "avertissements": avertissements,
                        "vagrantfile": None,
                        "lint_erreurs": [], "lint_avertissements": []}), 422

    vagrantfile = construire_vagrantfile(config, gabarit)
    lint_erreurs, lint_avertissements = linter_vagrantfile(vagrantfile)
    return jsonify({
        "vagrantfile": vagrantfile,
        "erreurs": erreurs,
        "avertissements": avertissements,
        "lint_erreurs": lint_erreurs,
        "lint_avertissements": lint_avertissements,
    })


@bp.get("/api/verifier-box")
def api_verifier_box():
    """Compare le catalogue local a Vagrant Cloud (reseau requis cote serveur)."""
    box = request.args.get("box")
    if box:
        if box not in BOX_PROVIDERS:
            return jsonify({"erreur": f"Box inconnue du catalogue local : {box}"}), 404
        catalogue = {box: BOX_PROVIDERS[box]}
    else:
        catalogue = BOX_PROVIDERS
    return jsonify({"rapports": verifier_catalogue(catalogue)})
