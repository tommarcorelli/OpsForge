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
    python main.py cloudinit  ...   -> generateur de fichier cloud-init (#cloud-config)
    python main.py packer     ...   -> generateur de template Packer (build.pkr.hcl)
    python main.py vault      ...   -> generateur de config HashiCorp Vault (config.hcl/policies/bootstrap)
    python main.py gitops     ...   -> generateur de manifests GitOps (ArgoCD Application / FluxCD)
    python main.py backup     ...   -> generateur de sauvegarde/restauration (restic / Borg)
    python main.py ssh        ...   -> generateur de config SSH (client ~/.ssh/config ou durcissement sshd)
    python main.py authproxy  ...   -> generateur d'authentification en frontal (oauth2-proxy / Authelia)
    python main.py sops       ...   -> generateur de chiffrement de secrets Git (SOPS + age)

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
    python main.py cloudinit --preset docker-host --hostname web-01
    python main.py packer --preset ubuntu-vagrant-box --name ubuntu-base
    python main.py vault --preset app-secrets-kv -o output/vault/
    python main.py gitops --preset argocd-raw-manifests -o output/gitops/
    python main.py backup --preset restic-local-systemd -o output/backup/
    python main.py ssh --preset acces-bastion -o output/ssh/
    python main.py authproxy --preset github-org -o output/authproxy/
    python main.py sops --preset multi-env -o output/sops/

Utilise `python main.py <module> --help` pour voir les options d'un module.
"""

import sys

from modules.ansible import cli as ansible_cli
from modules.authproxy import cli as authproxy_cli
from modules.backup import cli as backup_cli
from modules.cicd import cli as cicd_cli
from modules.cloudinit import cli as cloudinit_cli
from modules.dockerfile import cli as dockerfile_cli
from modules.firewall import cli as firewall_cli
from modules.gitops import cli as gitops_cli
from modules.logging import cli as logging_cli
from modules.precommit import cli as precommit_cli
from modules.k8s import cli as k8s_cli
from modules.monitoring import cli as monitoring_cli
from modules.nginx import cli as nginx_cli
from modules.packer import cli as packer_cli
from modules.sops import cli as sops_cli
from modules.ssh import cli as ssh_cli
from modules.systemd import cli as systemd_cli
from modules.terraform import cli as terraform_cli
from modules.vagrant import cli as vagrant_cli
from modules.vault import cli as vault_cli

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
    "cloudinit": cloudinit_cli.main,
    "packer": packer_cli.main,
    "vault": vault_cli.main,
    "gitops": gitops_cli.main,
    "backup": backup_cli.main,
    "firewall": firewall_cli.main,
    "logging": logging_cli.main,
    "precommit": precommit_cli.main,
    "ssh": ssh_cli.main,
    "authproxy": authproxy_cli.main,
    "sops": sops_cli.main,
}


def _usage():
    print("Usage : python main.py {cicd|ansible|vagrant|terraform|dockerfile|k8s|nginx|systemd|monitoring|cloudinit|packer|vault|gitops|backup|firewall|logging|precommit|ssh|authproxy|sops} [options]")
    print()
    print("  cicd       Genere un pipeline CI/CD (GitHub Actions / GitLab CI / CircleCI / Jenkins / Drone / Bitbucket / TeamCity)")
    print("  ansible    Genere un playbook Ansible (provisioning + deploiement)")
    print("  vagrant    Genere un Vagrantfile multi-VM")
    print("  terraform  Genere un main.tf (v0, a enrichir)")
    print("  dockerfile Genere un Dockerfile multi-stage (build + runtime allege)")
    print("  k8s        Genere des manifests Kubernetes ou un chart Helm")
    print("  nginx      Genere un bloc de config Nginx (statique / reverse proxy / load balancer)")
    print("  systemd    Genere des unites systemd (.service supervise / .timer planifie)")
    print("  monitoring Genere de la config monitoring (prometheus.yml / alertes / datasources Grafana)")
    print("  cloudinit  Genere un fichier cloud-init #cloud-config (premier boot d'une machine)")
    print("  packer     Genere un template Packer build.pkr.hcl (image VM/AMI/conteneur)")
    print("  vault      Genere une config HashiCorp Vault (config.hcl, policies ACL, bootstrap.sh)")
    print("  gitops     Genere des manifests GitOps (ArgoCD Application / FluxCD GitRepository+Kustomization ou HelmRelease)")
    print("  backup     Genere un script de sauvegarde/restauration idempotent (restic / Borg) + planification")
    print("  firewall   Genere des regles pare-feu (ufw / nftables) + config fail2ban (jail.local)")
    print("  logging    Genere une config de collecte de logs (Fluent Bit / Vector) vers Loki/Elasticsearch")
    print("  precommit  Genere des hooks Git pre-commit (framework pre-commit / Husky+lint-staged)")
    print("  ssh        Genere une config SSH (~/.ssh/config client / durcissement sshd_config.d)")
    print("  authproxy  Genere une authentification en frontal (oauth2-proxy / Authelia)")
    print("  sops       Genere une config de chiffrement de secrets Git (SOPS + age)")
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
