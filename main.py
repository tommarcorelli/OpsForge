"""
main.py
-------
OpsForge — point d'entree CLI unifie.

Deux sous-commandes :
    python main.py cicd    ...   -> generateur de pipeline CI/CD
    python main.py ansible ...   -> generateur de playbook Ansible

Chaque sous-commande accepte ses propres options. Exemples :
    python main.py cicd . --provider gitlab --deploy docker_hub
    python main.py ansible --lang node --repo git@github.com:moi/app.git --layout roles

Utilise `python main.py cicd --help` ou `python main.py ansible --help`
pour voir toutes les options d'un module.
"""

import sys

from modules.cicd import cli as cicd_cli
from modules.ansible import cli as ansible_cli

MODULES = {
    "cicd": cicd_cli.main,
    "ansible": ansible_cli.main,
}


def _usage():
    print("Usage : python main.py {cicd|ansible} [options]")
    print()
    print("  cicd     Genere un pipeline CI/CD (GitHub Actions / GitLab CI)")
    print("  ansible  Genere un playbook Ansible (provisioning + deploiement)")
    print()
    print("Aide detaillee d'un module : python main.py <module> --help")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage()
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    module = sys.argv[1]
    if module not in MODULES:
        print(f"Erreur : module inconnu '{module}'.")
        print()
        _usage()
        sys.exit(1)

    # Delegue le reste des arguments a la CLI du module choisi
    MODULES[module](sys.argv[2:])


if __name__ == "__main__":
    main()
