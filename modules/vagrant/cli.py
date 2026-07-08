"""
modules/vagrant/cli.py
----------------------
Logique CLI du module Vagrant d'OpsForge (portage de VagrantForge).
Appele via `python main.py vagrant ...`.

Sous-commandes :
    vagrant generer config.json -o Vagrantfile
    vagrant preset k3s --sous-reseau 10.10.10 -o Vagrantfile
    vagrant valider config.json
    vagrant presets
    vagrant verifier-box
"""

import argparse
import json
import sys
from pathlib import Path

# La console Windows est souvent en cp1252 : force l'UTF-8 pour ne pas planter
# sur les accents et les caracteres de dessin du Vagrantfile genere.
for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from modules.vagrant.core.generateur import construire_vagrantfile
from modules.vagrant.core.schema import valider_config, BOX_PROVIDERS
from modules.vagrant.core.presets import PRESETS, obtenir_preset
from modules.vagrant.core.lint import linter_vagrantfile
from modules.vagrant.core.verif_box import verifier_catalogue


class C:
    """Codes couleur ANSI, desactives si la sortie n'est pas un terminal."""
    actif = sys.stderr.isatty()
    ROUGE = "\033[31m" if actif else ""
    VERT = "\033[32m" if actif else ""
    JAUNE = "\033[33m" if actif else ""
    BLEU = "\033[36m" if actif else ""
    GRAS = "\033[1m" if actif else ""
    RAZ = "\033[0m" if actif else ""


def err(msg):
    print(msg, file=sys.stderr)


def afficher_diagnostics(erreurs, avertissements):
    for a in avertissements:
        err(f"{C.JAUNE}! {a}{C.RAZ}")
    for e in erreurs:
        err(f"{C.ROUGE}x {e}{C.RAZ}")


def charger_json(chemin):
    try:
        brut = sys.stdin.read() if chemin == "-" else Path(chemin).read_text(encoding="utf-8")
    except FileNotFoundError:
        err(f"{C.ROUGE}x Fichier introuvable : {chemin}{C.RAZ}")
        sys.exit(2)
    try:
        return json.loads(brut)
    except json.JSONDecodeError as e:
        err(f"{C.ROUGE}x JSON invalide : {e}{C.RAZ}")
        sys.exit(2)


def ecrire_sortie(contenu, sortie):
    if sortie and sortie != "-":
        Path(sortie).write_text(contenu, encoding="utf-8")
        err(f"{C.VERT}v Vagrantfile ecrit dans {sortie}{C.RAZ}")
    else:
        sys.stdout.write(contenu)


def charger_gabarit(chemin):
    if not chemin:
        return None
    try:
        return Path(chemin).read_text(encoding="utf-8")
    except FileNotFoundError:
        err(f"{C.ROUGE}x Gabarit introuvable : {chemin}{C.RAZ}")
        sys.exit(2)


def _generer_depuis_config(config, sortie, forcer, gabarit=None):
    erreurs, avertissements = valider_config(config)
    afficher_diagnostics(erreurs, avertissements)
    if erreurs and not forcer:
        err(f"{C.ROUGE}{C.GRAS}Generation annulee : {len(erreurs)} erreur(s).{C.RAZ} "
            f"Utilise --forcer pour passer outre.")
        sys.exit(1)
    contenu = construire_vagrantfile(config, gabarit)
    lint_erreurs, lint_avert = linter_vagrantfile(contenu)
    afficher_diagnostics(lint_erreurs, lint_avert)
    ecrire_sortie(contenu, sortie)
    return 0


def cmd_generer(args):
    config = charger_json(args.config)
    gabarit = charger_gabarit(args.gabarit)
    return _generer_depuis_config(config, args.output, args.forcer, gabarit)


def cmd_preset(args):
    try:
        config = obtenir_preset(args.nom, args.sous_reseau)
    except KeyError:
        err(f"{C.ROUGE}x Preset inconnu : {args.nom}{C.RAZ}")
        err(f"  Presets disponibles : {', '.join(PRESETS)}")
        sys.exit(2)
    if args.json:
        sys.stdout.write(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        return 0
    gabarit = charger_gabarit(args.gabarit)
    return _generer_depuis_config(config, args.output, forcer=True, gabarit=gabarit)


def cmd_valider(args):
    config = charger_json(args.config)
    erreurs, avertissements = valider_config(config)
    afficher_diagnostics(erreurs, avertissements)
    if erreurs:
        err(f"{C.ROUGE}{C.GRAS}{len(erreurs)} erreur(s), {len(avertissements)} avertissement(s).{C.RAZ}")
        sys.exit(1)
    err(f"{C.VERT}v Config valide{C.RAZ}"
        + (f" ({len(avertissements)} avertissement(s))" if avertissements else "") + ".")
    return 0


def cmd_presets(args):
    print(f"{C.GRAS}Presets Vagrant :{C.RAZ}")
    for nom, (desc, _) in PRESETS.items():
        print(f"  {C.BLEU}{nom:<12}{C.RAZ} {desc}")
    return 0


def cmd_verifier_box(args):
    catalogue = {args.box: BOX_PROVIDERS[args.box]} if args.box else BOX_PROVIDERS
    if args.box and args.box not in BOX_PROVIDERS:
        err(f"{C.ROUGE}x Box inconnue du catalogue local : {args.box}{C.RAZ}")
        sys.exit(2)

    print(f"{C.GRAS}Verification du catalogue face a Vagrant Cloud ({len(catalogue)} box)...{C.RAZ}")
    rapports = verifier_catalogue(catalogue)

    a_signaler = 0
    for r in rapports:
        if r["erreur"]:
            a_signaler += 1
            print(f"  {C.JAUNE}! {r['box']:<28} {r['erreur']}{C.RAZ}")
            continue
        if r["manquants_localement"] or r["en_trop"]:
            a_signaler += 1
            print(f"  {C.JAUNE}! {r['box']}{C.RAZ}")
            if r["manquants_localement"]:
                print(f"      publies mais absents du catalogue local : {', '.join(r['manquants_localement'])}")
            if r["en_trop"]:
                print(f"      dans le catalogue local mais plus publies : {', '.join(r['en_trop'])}")
        else:
            print(f"  {C.VERT}v {r['box']:<28} a jour ({', '.join(r['distants'])}){C.RAZ}")

    print()
    if a_signaler:
        print(f"{C.JAUNE}{a_signaler} box a revoir dans modules/vagrant/core/schema.py::BOX_PROVIDERS.{C.RAZ}")
    else:
        print(f"{C.VERT}Catalogue a jour.{C.RAZ}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="opsforge vagrant",
        description="Module Vagrant — forge des Vagrantfile multi-VM proprement.",
    )
    sous = p.add_subparsers(dest="commande", required=True)

    g = sous.add_parser("generer", help="Genere un Vagrantfile depuis une config JSON.")
    g.add_argument("config", help="Chemin du JSON, ou '-' pour stdin.")
    g.add_argument("-o", "--output", help="Fichier de sortie (defaut : stdout).")
    g.add_argument("--forcer", action="store_true", help="Genere malgre les erreurs de validation.")
    g.add_argument("--gabarit", help="Fichier gabarit personnalise (voir core/generateur.py).")
    g.set_defaults(fonc=cmd_generer)

    pr = sous.add_parser("preset", help="Genere un Vagrantfile depuis un preset.")
    pr.add_argument("nom", help="Nom du preset (voir « vagrant presets »).")
    pr.add_argument("-o", "--output", help="Fichier de sortie (defaut : stdout).")
    pr.add_argument("--sous-reseau", default="192.168.56", dest="sous_reseau",
                    help="Sous-reseau prive de base (defaut : 192.168.56).")
    pr.add_argument("--json", action="store_true", help="Sort la config JSON au lieu du Vagrantfile.")
    pr.add_argument("--gabarit", help="Fichier gabarit personnalise (voir core/generateur.py).")
    pr.set_defaults(fonc=cmd_preset)

    v = sous.add_parser("valider", help="Valide une config sans generer.")
    v.add_argument("config", help="Chemin du JSON, ou '-' pour stdin.")
    v.set_defaults(fonc=cmd_valider)

    lp = sous.add_parser("presets", help="Liste les presets disponibles.")
    lp.set_defaults(fonc=cmd_presets)

    vb = sous.add_parser("verifier-box", help="Compare le catalogue de box a Vagrant Cloud (reseau requis).")
    vb.add_argument("--box", help="Ne verifie qu'une seule box (defaut : tout le catalogue).")
    vb.set_defaults(fonc=cmd_verifier_box)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fonc(args)
