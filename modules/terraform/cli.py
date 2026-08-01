"""
modules/terraform/cli.py
------------------------
Logique CLI du module Terraform d'OpsForge.
Appele via `python main.py terraform ...`.

Trois formats de sortie :
    --format hcl (defaut)     -> main.tf (Terraform), via core.py
    --format cloudformation   -> template.yaml (AWS CloudFormation), via
                                  cloudformation_core.py (schema de config
                                  different : resources[].properties au lieu
                                  de resources[].args, pas de "provider")
    --format pulumi           -> __main__.py (programme Pulumi Python), via
                                  pulumi_core.py. Meme schema resources[].args
                                  que le HCL, reutilise le meme "provider"
                                  (aws/google/azurerm/docker — pas "local",
                                  pas d'equivalent Pulumi officiel).

Exemples :
    python main.py terraform config.json -o main.tf
    cat config.json | python main.py terraform -
    python main.py terraform --providers        # liste les providers connus
    python main.py terraform --format cloudformation --preset ec2-web -o template.yaml
    python main.py terraform --format pulumi --preset ec2-web -o __main__.py
"""

import argparse
import json
import os
import sys

from modules.terraform.cloudformation_core import (
    PRESETS as PRESETS_CFN,
)
from modules.terraform.cloudformation_core import (
    generate_cloudformation,
)
from modules.terraform.cloudformation_core import (
    obtenir_preset as obtenir_preset_cfn,
)
from modules.terraform.cloudformation_core import (
    valider_config as valider_config_cfn,
)
from modules.terraform.core import (
    PRESETS,
    SUPPORTED_PROVIDERS,
    generate_terraform,
    generate_terraform_files,
    obtenir_preset,
    valider_config,
)
from modules.terraform.pulumi_core import (
    OUTPUT_FILENAME as PULUMI_FILENAME,
)
from modules.terraform.pulumi_core import (
    PRESETS as PRESETS_PULUMI,
)
from modules.terraform.pulumi_core import (
    PULUMI_PROVIDERS,
    generate_pulumi,
)
from modules.terraform.pulumi_core import (
    obtenir_preset as obtenir_preset_pulumi,
)
from modules.terraform.pulumi_core import (
    valider_config as valider_config_pulumi,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    p = argparse.ArgumentParser(
        prog="opsforge terraform",
        description="Genere un main.tf (Terraform), un template.yaml (CloudFormation) "
                     "ou un __main__.py (Pulumi) a partir d'une config JSON, ou d'un preset.",
    )
    p.add_argument("config", nargs="?", help="Chemin du JSON de config, ou '-' pour stdin.")
    p.add_argument("-o", "--output", default=None,
                   help="Fichier de sortie (defaut : output/main.tf, output/template.yaml ou "
                        "output/__main__.py selon --format ; '-' pour stdout). "
                        "Avec --split (HCL uniquement), c'est un dossier de sortie (defaut : output/).")
    p.add_argument("--format", choices=["hcl", "cloudformation", "pulumi"], default="hcl",
                   help="Format de sortie : hcl (main.tf Terraform, defaut), "
                        "cloudformation (template.yaml AWS) ou pulumi (__main__.py Python, "
                        "aws/google/azurerm/docker). --split non applicable a cloudformation/pulumi.")
    p.add_argument("--split", action="store_true",
                   help="[hcl uniquement] Ecrit un projet en fichiers separes : main.tf, "
                        "variables.tf et outputs.tf (si non vides), dans --output (dossier).")
    p.add_argument("--preset", default=None, help="Genere depuis un preset (voir --list-presets).")
    p.add_argument("--providers", action="store_true",
                   help="Liste les providers connus et quitte.")
    p.add_argument("--list-presets", action="store_true",
                   help="Liste les presets disponibles et quitte (selon --format).")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    is_cfn = args.format == "cloudformation"
    is_pulumi = args.format == "pulumi"

    if args.providers:
        if is_cfn:
            print("CloudFormation est specifique a AWS : pas de choix de provider.")
        elif is_pulumi:
            print("Providers Pulumi connus :", ", ".join(PULUMI_PROVIDERS))
        else:
            print("Providers connus :", ", ".join(SUPPORTED_PROVIDERS))
        return 0

    if args.list_presets:
        presets = PRESETS_PULUMI if is_pulumi else (PRESETS_CFN if is_cfn else PRESETS)
        print("Presets disponibles :")
        for k, v in presets.items():
            print(f"  {k:<14} {v['label']}")
        return 0

    if args.preset:
        try:
            if is_pulumi:
                config = obtenir_preset_pulumi(args.preset)
            elif is_cfn:
                config = obtenir_preset_cfn(args.preset)
            else:
                config = obtenir_preset(args.preset)
        except KeyError:
            print(f"Erreur : preset inconnu « {args.preset} ». Voir --list-presets.", file=sys.stderr)
            sys.exit(2)
    else:
        if not args.config:
            print("Erreur : fournis un fichier de config JSON (ou '-' pour stdin), "
                  "un --preset, ou utilise --providers / --list-presets.", file=sys.stderr)
            sys.exit(2)
        brut = sys.stdin.read() if args.config == "-" else _lire(args.config)
        try:
            config = json.loads(brut)
        except json.JSONDecodeError as e:
            print(f"Erreur : JSON invalide ({e})", file=sys.stderr)
            sys.exit(2)

    valider = valider_config_pulumi if is_pulumi else (valider_config_cfn if is_cfn else valider_config)
    erreurs, avertissements = valider(config)
    for a in avertissements:
        print(f"! {a}", file=sys.stderr)
    if erreurs:
        for e in erreurs:
            print(f"x {e}", file=sys.stderr)
        sys.exit(1)

    if is_pulumi:
        contenu = generate_pulumi(config)
        default_filename = PULUMI_FILENAME
    elif is_cfn:
        contenu = generate_cloudformation(config)
        default_filename = "template.yaml"
    else:
        if args.split:
            if args.output == "-":
                print("Erreur : --split ecrit plusieurs fichiers, incompatible avec '-o -'.", file=sys.stderr)
                sys.exit(2)
            output_dir = args.output or OUTPUT_DIR
            fichiers = generate_terraform_files(config)
            os.makedirs(output_dir, exist_ok=True)
            for nom, texte in fichiers.items():
                chemin = os.path.join(output_dir, nom)
                with open(chemin, "w", encoding="utf-8") as f:
                    f.write(texte)
                print(f"{nom} genere : {chemin}", file=sys.stderr)
            return 0
        contenu = generate_terraform(config)
        default_filename = "main.tf"

    if args.output == "-":
        sys.stdout.write(contenu)
        return 0

    output_path = args.output or os.path.join(OUTPUT_DIR, default_filename)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)
    print(f"{default_filename} genere : {output_path}", file=sys.stderr)
    return 0


def _lire(chemin):
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Erreur : fichier introuvable : {chemin}", file=sys.stderr)
        sys.exit(2)
