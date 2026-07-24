"""
modules/packer/cli.py
----------------------
Logique CLI du module Packer d'OpsForge.
Appele via `python main.py packer ...`.
"""

import argparse
import json
import os
import sys

from modules.packer.core import (
    generate_packer_template,
    generate_split_files,
    write_files,
    write_split_files,
    list_presets,
    get_preset,
    list_builders,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge packer",
        description=(
            "Genere un template Packer HCL2 (build.pkr.hcl) : builder "
            "(virtualbox-iso, qemu, amazon-ebs, docker), provisioners et "
            "post-processors, a partir d'un fichier JSON ou d'un preset."
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
        "--list-builders",
        action="store_true",
        help=f"Affiche la liste des builders geres ({', '.join(list_builders())}) et quitte.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Surcharge le nom du build.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le template genere sans rien ecrire sur disque.",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help=(
            "Ecrit un projet en fichiers separes (variables.pkr.hcl, "
            "sources.pkr.hcl, build.pkr.hcl) plutot qu'un seul build.pkr.hcl."
        ),
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

    if args.name:
        config["name"] = args.name

    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            print(f"  - {name}")
        return 0

    if args.list_builders:
        print("Builders geres :")
        for name in list_builders():
            print(f"  - {name}")
        return 0

    config = _load_config(args)

    if args.dry_run:
        try:
            if args.split:
                fichiers = generate_split_files(config)
            else:
                content = generate_packer_template(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        print("\n--- Apercu (dry-run) ---\n")
        if args.split:
            for nom, contenu in fichiers.items():
                print(f"# --- {nom} ---")
                print(contenu)
        else:
            print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    output_dir = args.output_dir or OUTPUT_DIR

    try:
        paths = write_split_files(config, output_dir) if args.split else write_files(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nTemplate Packer genere avec succes :")
    for path in paths:
        print(f"  - {path}")
    if args.split:
        print(
            f"\nUtilisation : `packer init {output_dir}` puis `packer build {output_dir}`."
        )
    else:
        print(
            "\nUtilisation : `packer init " + os.path.basename(paths[0]) + "` puis "
            f"`packer build {os.path.basename(paths[0])}`."
        )
    return 0
