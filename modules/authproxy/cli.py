"""
modules/authproxy/cli.py
--------------------------
Logique CLI du module authproxy d'OpsForge.
Appele via `python main.py authproxy ...`.
"""

import argparse
import json
import os

from modules.authproxy.core import (
    PRESETS,
    SUPPORTED_ENGINES,
    generate_authproxy,
    get_preset,
    list_presets,
    write_authproxy,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge authproxy",
        description=(
            "Genere une authentification en frontal d'une appli deja servie par un "
            "reverse proxy : oauth2-proxy (delegue a GitHub/Google/OIDC) ou Authelia "
            "(portail autonome, utilisateurs locaux, MFA, regles par domaine)."
        ),
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Fichier JSON decrivant la config (voir --preset pour un depart rapide).",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help=f"Utilise un preset predefini. Disponibles : {', '.join(list_presets())}.",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="Affiche la liste des presets disponibles et quitte.",
    )
    parser.add_argument(
        "--engine",
        choices=SUPPORTED_ENGINES,
        default=None,
        help="Surcharge le moteur (oauth2-proxy / authelia).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le(s) fichier(s) genere(s) sans rien ecrire sur disque.",
    )
    return parser


def _load_config(args):
    """Retourne la config chargee, ou None (en ayant deja affiche l'erreur) en cas d'echec."""
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    elif args.preset:
        try:
            config = get_preset(args.preset)
        except ValueError as e:
            print(f"Erreur : {e}")
            return None
    else:
        print(
            "Erreur : fournis un fichier de config JSON ou --preset "
            f"({', '.join(list_presets())})."
        )
        return None

    if args.engine:
        config["engine"] = args.engine

    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            preset = PRESETS[name]
            print(f"  - {name:<20} [{preset['engine']}] {preset['label']}")
        return 0

    config = _load_config(args)
    if config is None:
        return 1

    if args.dry_run:
        try:
            files = generate_authproxy(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        for filename, content in files.items():
            print(f"\n--- Apercu (dry-run) : {filename} ---\n")
            print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    output_dir = args.output_dir or OUTPUT_DIR

    try:
        paths = write_authproxy(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nFichier(s) genere(s) avec succes :")
    for path in paths:
        print(f"  - {path}")

    engine = config.get("engine", "oauth2-proxy")
    if engine == "oauth2-proxy":
        print("\nColle nginx-auth-snippet.conf dans le bloc server{} de l'appli (module nginx),")
        print("puis lance oauth2-proxy avec --config=oauth2-proxy.cfg")
    else:
        print("\nGenere les vrais hash de mot de passe AVANT de deployer :")
        print("  authelia crypto hash generate argon2 --password 'ton-mot-de-passe'")
        print("Remplace-les dans users_database.yml, puis lance authelia avec")
        print("--config=configuration.yml")

    return 0
