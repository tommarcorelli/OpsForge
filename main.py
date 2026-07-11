"""
main.py
-------
OpsForge — point d'entree CLI unifie.

Sous-commandes :
    python main.py cicd       ...   -> generateur de pipeline CI/CD
    python main.py ansible    ...   -> generateur de playbook Ansible
    python main.py vagrant    ...   -> generateur de Vagrantfile multi-VM
    python main.py terraform  ...   -> generateur de main.tf (v0)
    python main.py dockerfile ...   -> generateur de Dockerfile multi-stage
    python main.py k8s        ...   -> generateur de manifests K8s / chart Helm
    python main.py nginx      ...   -> generateur de bloc de config Nginx (server/upstream)
    python main.py systemd    ...   -> generateur d'unites systemd (.service / .timer)
    python main.py monitoring ...   -> generateur de config monitoring (Prometheus/Grafana)

Chaque sous-commande accepte ses propres options. Exemples :
    python main.py cicd . --provider gitlab --deploy docker_hub
    python main.py ansible --lang node --repo git@github.com:moi/app.git --layout roles
    python main.py vagrant preset k3s -o Vagrantfile
    python main.py terraform config.json -o main.tf
    python main.py dockerfile . --port 8000 --entrypoint app.py
    python main.py k8s --name mon-app --image monuser/app:1.0 --ingress-host app.example.com
    python main.py nginx --preset api-reverse-proxy --server-name api.example.com --https
    python main.py systemd --preset web-app --name myapp
    python main.py monitoring --preset prometheus-node -o output/

Utilise `python main.py <module> --help` pour voir les options d'un module.
"""

import sys

from modules.cicd import cli as cicd_cli
from modules.ansible import cli as ansible_cli
from modules.vagrant import cli as vagrant_cli
from modules.terraform import cli as terraform_cli
from modules.dockerfile import cli as dockerfile_cli
from modules.k8s import cli as k8s_cli
from modules.nginx import cli as nginx_cli
from modules.systemd import cli as systemd_cli
from modules.monitoring import cli as monitoring_cli

MODULES = {
    "cicd": cicd_cli.main,
    "ansible": ansible_cli.main,
    "vagrant": vagrant_cli.main,
    "terraform": terraform_cli.main,
    "dockerfile": dockerfile_cli.main,
    "k8s": k8s_cli.main,
    "nginx": nginx_cli.main,
    "systemd": systemd_cli.main,
    "monitoring": monitoring_cli.main,
}


def _usage():
    print("Usage : python main.py {cicd|ansible|vagrant|terraform|dockerfile|k8s|nginx|systemd|monitoring} [options]")
    print()
    print("  cicd       Genere un pipeline CI/CD (GitHub Actions / GitLab CI)")
    print("  ansible    Genere un playbook Ansible (provisioning + deploiement)")
    print("  vagrant    Genere un Vagrantfile multi-VM")
    print("  terraform  Genere un main.tf (v0, a enrichir)")
    print("  dockerfile Genere un Dockerfile multi-stage (build + runtime allege)")
    print("  k8s        Genere des manifests Kubernetes ou un chart Helm")
    print("  nginx      Genere un bloc de config Nginx (statique / reverse proxy / load balancer)")
    print("  systemd    Genere des unites systemd (.service supervise / .timer planifie)")
    print("  monitoring Genere de la config monitoring (prometheus.yml / alertes / datasources Grafana)")
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

    # Delegue le reste des arguments a la CLI du module choisi.
    # Certains modules (vagrant, terraform) renvoient un code de sortie.
    rc = MODULES[module](sys.argv[2:])
    if isinstance(rc, int):
        sys.exit(rc)


if __name__ == "__main__":
    main()
