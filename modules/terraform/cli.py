"""
modules/terraform/cli.py
------------------------
Logique CLI du module Terraform d'OpsForge (v0 — a enrichir).
Appele via `python main.py terraform ...`.

Exemples :
    python main.py terraform config.json -o main.tf
    cat config.json | python main.py terraform -
    python main.py terraform --providers        # liste les providers connus
"""

import argparse
import json
import os
import sys

from modules.terraform.core import (
    generate_terraform,
    valider_config,
    SUPPORTED_PROVIDERS,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    p = argparse.ArgumentParser(
        prog="opsforge terraform",
        description="Genere un main.tf a partir d'une config JSON (provider + ressources).",
    )
    p.add_argument("config", nargs="?", help="Chemin du JSON de config, ou '-' pour stdin.")
    p.add_argument("-o", "--output", default=None,
                   help="Fichier de sortie (defaut : output/main.tf ; '-' pour stdout).")
    p.add_argument("--providers", action="store_true",
                   help="Liste les providers connus et quitte.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.providers:
        print("Providers connus :", ", ".join(SUPPORTED_PROVIDERS))
        return 0

    if not args.config:
        print("Erreur : fournis un fichier de config JSON (ou '-' pour stdin), "
              "ou utilise --providers.", file=sys.stderr)
        sys.exit(2)

    brut = sys.stdin.read() if args.config == "-" else _lire(args.config)
    try:
        config = json.loads(brut)
    except json.JSONDecodeError as e:
        print(f"Erreur : JSON invalide ({e})", file=sys.stderr)
        sys.exit(2)

    erreurs, avertissements = valider_config(config)
    for a in avertissements:
        print(f"! {a}", file=sys.stderr)
    if erreurs:
        for e in erreurs:
            print(f"x {e}", file=sys.stderr)
        sys.exit(1)

    contenu = generate_terraform(config)

    if args.output == "-":
        sys.stdout.write(contenu)
        return 0

    output_path = args.output or os.path.join(OUTPUT_DIR, "main.tf")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)
    print(f"main.tf genere : {output_path}", file=sys.stderr)
    return 0


def _lire(chemin):
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Erreur : fichier introuvable : {chemin}", file=sys.stderr)
        sys.exit(2)
