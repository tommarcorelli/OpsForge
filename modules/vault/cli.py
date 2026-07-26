"""
modules/vault/cli.py
----------------------
Logique CLI du module HashiCorp Vault d'OpsForge.
Appele via `python main.py vault ...`.
"""

import argparse
import json
import os
import sys

from modules.vault.core import (
    generate_files,
    write_files,
    list_presets,
    get_preset,
    list_storage_backends,
    list_seal_types,
    list_auth_methods,
    list_secrets_engines,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge vault",
        description=(
            "Genere une configuration HashiCorp Vault : config.hcl (serveur, "
            "storage, seal), policies/*.hcl (ACL) et bootstrap.sh (auth "
            "methods + secrets engines), a partir d'un fichier JSON ou d'un preset."
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
        "--list-storage-backends",
        action="store_true",
        help=f"Affiche les backends de storage geres ({', '.join(list_storage_backends())}) et quitte.",
    )
    parser.add_argument(
        "--list-seal-types",
        action="store_true",
        help=f"Affiche les types de seal geres ({', '.join(list_seal_types())}) et quitte.",
    )
    parser.add_argument(
        "--list-auth-methods",
        action="store_true",
        help=f"Affiche les methodes d'auth gerees ({', '.join(list_auth_methods())}) et quitte.",
    )
    parser.add_argument(
        "--list-secrets-engines",
        action="store_true",
        help=f"Affiche les moteurs de secrets geres ({', '.join(list_secrets_engines())}) et quitte.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les fichiers generes sans rien ecrire sur disque.",
    )
    return parser


def _load_config(args):
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    elif args.preset:
        try:
            config = get_preset(args.preset)
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
    else:
        print(
            "Erreur : fournis un fichier de config JSON ou --preset "
            f"({', '.join(list_presets())})."
        )
        sys.exit(1)
    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            print(f"  - {name}")
        return 0

    if args.list_storage_backends:
        print("Backends de storage geres :")
        for name in list_storage_backends():
            print(f"  - {name}")
        return 0

    if args.list_seal_types:
        print("Types de seal geres :")
        for name in list_seal_types():
            print(f"  - {name}")
        return 0

    if args.list_auth_methods:
        print("Methodes d'authentification gerees :")
        for name in list_auth_methods():
            print(f"  - {name}")
        return 0

    if args.list_secrets_engines:
        print("Moteurs de secrets geres :")
        for name in list_secrets_engines():
            print(f"  - {name}")
        return 0

    config = _load_config(args)

    if args.dry_run:
        try:
            fichiers = generate_files(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        print("\n--- Apercu (dry-run) ---\n")
        for nom, contenu in fichiers.items():
            print(f"# --- {nom} ---")
            print(contenu)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    output_dir = args.output_dir or OUTPUT_DIR

    try:
        paths = write_files(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nConfiguration Vault generee avec succes :")
    for path in paths:
        print(f"  - {path}")
    print(
        "\nUtilisation : `vault server -config=" + os.path.basename(paths[0])
        + "` puis, une fois initialise/descelle, `./bootstrap.sh`."
    )
    return 0
