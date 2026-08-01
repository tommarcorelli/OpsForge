# OpsForge

[![CI](https://github.com/ton-user/OpsForge/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ton-user/OpsForge/actions/workflows/ci.yml)

> Remplace `ton-user` par ton nom d'utilisateur/organisation GitHub une fois
> le repo poussé (badge généré avec le propre module `cicd` d'OpsForge 🙂).

## Qu'est-ce qu'OpsForge ?

OpsForge est une suite de **générateurs de fichiers de configuration DevOps/IaC**
(CI/CD, Terraform, Ansible, Dockerfile, Kubernetes, Nginx, systemd,
monitoring, cloud-init, Packer) réunis sous un seul hub web + CLI. Au lieu
d'écrire à la main le YAML/HCL/Groovy répétitif de chacun de ces outils, tu
remplis un formulaire (ou passes une config JSON), et OpsForge produit un
fichier **validé et prêt à l'emploi** dans le format natif de l'outil visé —
un vrai `.gitlab-ci.yml`, un vrai `main.tf`, un vrai `Jenkinsfile`, etc.
Ce n'est ni un remplaçant de ces outils ni un service : OpsForge ne provisionne
rien et n'exécute rien lui-même, il se contente de produire le fichier de
départ, correct du premier coup, que tu commites ensuite dans ton propre
dépôt. Tout tourne **100 % en local** : rien n'est jamais envoyé sur un
serveur externe.

**Plusieurs forges DevOps dans un seul atelier**, 100 % en local :

| Module | Ce qu'il génère | Accès web | Sous-commande CLI |
|---|---|---|---|
| **CI/CD** | Pipelines **GitHub Actions** (`.github/workflows/ci.yml`), **GitLab CI** (`.gitlab-ci.yml`), **CircleCI** (`.circleci/config.yml`), **Jenkins** (`Jenkinsfile`), **Drone** (`.drone.yml`), **Bitbucket Pipelines** (`bitbucket-pipelines.yml`) et **TeamCity** (`.teamcity/settings.kts`) | `/cicd` | `python main.py cicd …` |
| **Ansible** | Playbooks de **provisioning + déploiement** serveur (paquets, Docker, Nginx, firewall, fail2ban, bases de données, vault chiffré, multi-serveurs) | `/ansible` | `python main.py ansible …` |
| **Vagrant** | **Vagrantfile multi-VM** (providers, réseau, provisioning, presets, lint) — portage de VagrantForge | `/vagrant` | `python main.py vagrant …` |
| **Terraform** | **`main.tf`** validé et aligné : builder de ressources, presets, validation par provider, variables/outputs — ou export **CloudFormation** (`template.yaml`) ou **Pulumi** (`__main__.py`, aws/google/azurerm/docker) | `/terraform` | `python main.py terraform …` |
| **Dockerfile** | **`Dockerfile`** multi-stage (build + runtime allégé) + `.dockerignore`, 8 langages, bonnes pratiques (utilisateur non-root), option **`docker-bake.hcl`** (build multi-tags/multi-plateformes via `docker buildx bake`) | `/dockerfile` | `python main.py dockerfile …` |
| **Kubernetes / Helm / Kustomize** | **Manifests** (Deployment + Service + Ingress, probes, resources) prêts pour `kubectl apply`, **chart Helm** complet, ou structure **Kustomize** (`base/` + `overlays/dev,staging,prod`) — export `.zip` | `/k8s` | `python main.py k8s …` |
| **Nginx** | Bloc **`server{}`** Nginx : site statique (SPA), reverse proxy (WebSocket) ou load balancer (`upstream{}`), HTTPS Let's Encrypt en option — et variantes **Caddy** (Caddyfile) / **Traefik** (config dynamique YAML) / **HAProxy** (fragment `haproxy.cfg`) | `/nginx` | `python main.py nginx …` |
| **systemd** | Unité **`.service`** durcie (utilisateur dédié, redémarrage auto, sandboxing) ou paire **`.service` + `.timer`** planifiée (`OnCalendar`, remplace cron) | `/systemd` | `python main.py systemd …` |
| **Monitoring** | **`prometheus.yml`** (scrape multi-jobs + Alertmanager), **règles d'alerte** Prometheus (CPU/mém/disque/instance), **datasources Grafana** ou **`dashboard.json`** (panels réels prêts à importer) | `/monitoring` | `python main.py monitoring …` |
| **cloud-init** | **`#cloud-config`** (user-data) de premier boot : utilisateurs, clés SSH, paquets, `write_files`, `runcmd`, durcissement SSH — ou export **Ignition** (`config.ign`, Fedora CoreOS/Flatcar/RHCOS) | `/cloudinit` | `python main.py cloudinit …` |
| **Packer** | **`build.pkr.hcl`** (HCL2) : builder **virtualbox-iso / qemu / amazon-ebs / docker**, provisioners shell/file, post-processors (`vagrant`, `docker-tag`, `compress`) | `/packer` | `python main.py packer …` |
| **Vault** | **`config.hcl`** (storage file/raft/consul, seal shamir/awskms/transit, listener), **`policies/*.hcl`** (ACL), **`bootstrap.sh`** (activation auth methods et secrets engines : userpass/approle/kubernetes/ldap/github/oidc/jwt/aws/gcp/azure/cert, kv-v2/pki/database/transit/aws/ssh/gcp/azure/consul/nomad/totp…) | `/vault` | `python main.py vault …` |
| **GitOps** | **ArgoCD** (`argocd-application.yaml`) ou **FluxCD** (`flux-gitrepository.yaml` + `flux-kustomization.yaml`/`flux-helmrelease.yaml`) — sources raw/Kustomize/Helm, sync auto ou manuelle | `/gitops` | `python main.py gitops …` |
| **Backup** | **`backup.sh`**/**`restore.sh`** idempotents (**restic** ou **Borg**, backend local/SFTP/S3), planification **`*.service`+`*.timer`** ou **cron**, **`backup.env.example`** (secrets jamais en dur) | `/backup` | `python main.py backup …` |
| **SSH** | **`~/.ssh/config`** côté client (alias, clés dédiées, rebond **ProxyJump**, tunnels) ou fragment **`sshd_config.d/`** de durcissement côté serveur (+ **`authorized_keys`** restreint par clé : `from=`, `command=`, `restrict`) | `/ssh` | `python main.py ssh …` |
| **Auth** | Authentification en frontal d'une appli déjà servie par un reverse proxy : **`oauth2-proxy.cfg`** (délégué à GitHub/Google/OIDC) + snippet Nginx, ou **`configuration.yml`** **Authelia** (comptes locaux, MFA, règles d'accès par domaine) + `users_database.yml` | `/authproxy` | `python main.py authproxy …` |
| **SOPS** | **`.sops.yaml`** pour chiffrer les secrets versionnés dans un dépôt Git avec **SOPS + age** : une règle par chemin, un ou plusieurs destinataires, `encrypted_regex` pour ne chiffrer que certaines clés (ex : secrets Kubernetes) + fragment `.gitattributes` pour un diff Git lisible | `/sops` | `python main.py sops …` |

La page d'accueil (`/`) est un **hub** qui renvoie vers les modules. Rien
n'est jamais envoyé sur un serveur externe : tout tourne sur ta machine.

OpsForge fait partie de la suite **Forge** (avec DockerForge, gardé séparé car
c'est une appli React/Vite).

> **Historique** : OpsForge est né de la fusion de deux générateurs qui
> partageaient la même architecture (`ci-cd-generator` et `ansible-generator`),
> puis a accueilli le cœur de **VagrantForge** en module et un module
> **Terraform** neuf. Même logique que NetForge et ses modules réseau : chaque
> générateur reste un bloc autonome (core + routes + cli + templates), juste
> monté sous un préfixe (`/cicd`, `/ansible`, `/vagrant`, `/terraform`,
> `/nginx`, `/systemd`…).
>
> **Ajouter un module** = créer `modules/<nom>/{core,routes,cli}.py`, une page
> `web/templates/<nom>.html`, l'enregistrer dans `app.py` et `main.py`, et
> ajouter une carte au hub. Tout générateur de fichiers de config en Python s'y
> branche naturellement.

---

## Installation

```bash
pip install -r requirements.txt --break-system-packages
```

Dépendances : `flask` (interface web), `pyyaml` (validation du YAML généré) et
`ansible-core` (chiffrement Ansible Vault du module Ansible).

> ⚠️ **Le chiffrement Vault nécessite un environnement Unix/Linux** (ou WSL) :
> `ansible-core` dépend du module `fcntl`, absent sous Windows natif. Tout le
> reste (génération de playbooks, pipelines, rôles, inventaires) fonctionne
> partout. Sous Windows, génère avec le Vault **désactivé**, ou lance OpsForge
> depuis WSL.

---

## Interface web

```bash
python app.py
```

Puis ouvre **http://127.0.0.1:5050**. Choisis un module depuis le hub, ou vas
directement sur `/cicd` ou `/ansible`. Port configurable : `PORT=8080 python app.py`.
Mode debug (rechargement auto + debugger Werkzeug) désactivé par défaut,
activable pour le dev : `FLASK_DEBUG=1 python app.py`.

L'interface est installable comme **PWA** (Chrome/Edge : icône dans la barre
d'adresse ; mobile : « Ajouter à l'écran d'accueil »).

---

## Application desktop (.exe)

Pour lancer OpsForge sans terminal ni navigateur (fenêtre native, double-clic) :

```bash
pip install -r requirements-desktop.txt   # pywebview + pyinstaller
python desktop.py                          # test en dev
pyinstaller opsforge.spec                  # build -> dist/OpsForge.exe
```

`desktop.py` démarre Flask en arrière-plan (thread, sur le premier port libre à
partir de 5050 — n'entre pas en conflit si `python app.py` tourne déjà) et
ouvre une fenêtre native **pywebview** (WebView2 sous Windows) dessus. L'`.exe`
généré est **autonome** : aucune installation de Python requise sur la machine
cible. `ansible-core` est volontairement exclu du bundle (voir `opsforge.spec`)
— le chiffrement Vault reste indisponible dans l'exe, comme sous Windows natif
en usage normal (voir note ci-dessus).

Cet `.exe` est **portable** (aucune installation, tu le lances où qu'il soit).
Pour un vrai installateur Windows (icône Bureau + Menu Démarrer, désinstalleur
listé dans « Programmes ») :

```bash
winget install JRSoftware.InnoSetup      # une seule fois
iscc opsforge-installer.iss              # -> installer/OpsForge-Setup.exe
```

Installe **par utilisateur** (`{localappdata}\Programs\OpsForge`), sans droits
administrateur ni invite UAC — plus adapté à un outil perso qu'une installation
machine entière dans `Program Files`.

> ⚠️ Le build PyInstaller/Inno Setup est **spécifique à Windows** : `desktop.py`
> tourne aussi sur Linux/Mac (pywebview y a des backends natifs — GTK/Qt,
> Cocoa/WebKit), mais produire un vrai binaire natif pour ces plateformes
> nécessite de relancer le build **depuis** un Mac/Linux — PyInstaller ne
> fait pas de cross-compilation, et Inno Setup est Windows-only.

---

## Ligne de commande

Le CLI est unifié avec deux sous-commandes. Aide détaillée par module :
`python main.py cicd --help` / `python main.py ansible --help`.

### Module CI/CD

```bash
# Détecte le stack du dossier courant et génère un pipeline GitHub Actions
python main.py cicd .

# GitLab CI, avec déploiement Docker Hub + SSH
python main.py cicd . --provider gitlab --deploy docker_hub ssh \
  --docker-image monuser/monapp --deploy-path /var/www/app --service-name app

# Matrix build (teste plusieurs versions) + cron + badge
python main.py cicd . --matrix-versions 3.10 3.11 3.12 \
  --schedule-cron "0 3 * * *" --badge-repo monuser/monrepo

# CircleCI, Jenkins, Drone, Bitbucket ou TeamCity (memes options --deploy/--matrix-versions/--schedule-cron)
python main.py cicd . --provider circleci --deploy aws_s3 --s3-bucket mon-bucket
python main.py cicd . --provider jenkins --dry-run
python main.py cicd . --provider drone --dry-run
python main.py cicd . --provider bitbucket --dry-run
python main.py cicd . --provider teamcity --dry-run

# Apercu sans rien ecrire sur disque
python main.py cicd . --dry-run

# Pipeline + mises a jour automatiques des dependances (fichier en plus)
python main.py cicd . --deps dependabot
python main.py cicd . --provider gitlab --deps renovate --deps-schedule daily --deps-docker
```

### Module SSH

```bash
# Liste les presets (client et serveur)
python main.py ssh --list-presets

# Cote client : ~/.ssh/config avec rebond par bastion
python main.py ssh --preset acces-bastion -o output/ssh/

# Cote serveur : fragment de durcissement sshd, port et groupes surcharges
python main.py ssh --preset serveur-durci --port 2222 --allow-groups admins devops -o output/ssh/

# Depuis une config JSON sur mesure
python main.py ssh ma-config-ssh.json -o output/ssh/

# Apercu sans rien ecrire sur disque
python main.py ssh --preset sftp-only --dry-run
```

### Module Auth (authentification en frontal)

```bash
# oauth2-proxy restreint a une organisation GitHub
python main.py authproxy --preset github-org -o output/authproxy/

# Authelia : deux facteurs sur les routes sensibles
python main.py authproxy --preset two-factor-sensitive -o output/authproxy/

# Apercu sans rien ecrire sur disque
python main.py authproxy --preset homelab-simple --dry-run
```

### Module SOPS (secrets Git chiffres)

```bash
# Une cle par environnement (dev / staging / prod)
python main.py sops --preset multi-env -o output/sops/

# Secrets Kubernetes : seules les valeurs data/stringData sont chiffrees
python main.py sops --preset k8s-secrets -o output/sops/

# Apercu sans rien ecrire sur disque
python main.py sops --preset solo-dev --dry-run
```

### Module Kubernetes / Helm / Kustomize

```bash
# Manifests bruts, prets pour kubectl apply -f
python main.py k8s --name mon-app --image monuser/mon-app:1.0.0

# Chart Helm
python main.py k8s --name mon-app --image monuser/mon-app:1.0.0 --helm

# Kustomize : base + overlays dev/staging/prod (defaut)
python main.py k8s --name mon-app --image monuser/mon-app:1.0.0 --kustomize

# Kustomize avec overlays personnalises
python main.py k8s --name mon-app --image monuser/mon-app:1.0.0 --kustomize --overlays dev staging prod qa
```

### Module Nginx (+ Caddy / Traefik / HAProxy)

```bash
# Nginx classique (defaut)
python main.py nginx --preset api-reverse-proxy --https -o -

# Meme config, en Caddyfile
python main.py nginx --preset api-reverse-proxy --target caddy --dry-run

# Meme config, en config dynamique Traefik (YAML)
python main.py nginx --preset load-balanced-app --target traefik --dry-run

# Meme config, en fragment haproxy.cfg
python main.py nginx --preset load-balanced-app --target haproxy --dry-run
```

### Module Terraform

```bash
# Depuis un preset, fichier main.tf unique sur stdout
python main.py terraform --preset ec2-web -o -

# Depuis une config JSON, en fichiers separes (main.tf/variables.tf/outputs.tf)
python main.py terraform config.json --split -o output/mon-projet/

# Preset avec variables/outputs -> 3 fichiers separes
python main.py terraform --preset rds-postgres --split -o output/rds/

# Export CloudFormation (AWS uniquement) au lieu du HCL Terraform
python main.py terraform --format cloudformation --preset ec2-web -o -
python main.py terraform --format cloudformation --list-presets

# Export Pulumi (programme Python, aws/google/azurerm/docker)
python main.py terraform --format pulumi --preset ec2-web -o __main__.py
python main.py terraform --format pulumi --providers
```

### Module Ansible

```bash
# Playbook "flat" : provisioning + déploiement d'une app Node
python main.py ansible --lang node --repo git@github.com:moi/app.git \
  --provisioning update_system base_packages runtime firewall fail2ban \
  --deployment git_clone install_deps restart_service

# Projet organisé en rôles (bonnes pratiques Ansible) + inventaire
python main.py ansible --lang python --repo git@github.com:moi/app.git \
  --layout roles --inventory-host 203.0.113.10

# Multi-serveurs à partir d'un fichier JSON de groupes
python main.py ansible --groups-file mes-serveurs.json

# Aperçu sans rien écrire sur disque (layout flat uniquement)
python main.py ansible --lang node --repo git@github.com:moi/app.git \
  --provisioning base_packages --deployment git_clone --dry-run

# Base MongoDB + sauvegardes automatiques quotidiennes (cron + rotation)
python main.py ansible --lang node --repo git@github.com:moi/app.git \
  --provisioning update_system database backups \
  --database-engine mongodb --db-name app --db-user app_user \
  --backup-dir /mnt/backups --backup-retention-days 14 --backup-hour 3

# Cible Windows / WinRM (voir les etapes disponibles avec --list-windows-steps)
python main.py ansible --lang node --repo git@github.com:moi/app.git \
  --target-os windows --provisioning update_system base_packages runtime \
  --deployment git_clone install_deps restart_service \
  --inventory-host 203.0.113.20 --ssh-user Administrator --winrm-password 'S3cret!'
```

Sortie par défaut : dossier `output/` à la racine du projet.

---

## Architecture

```
opsforge/
├── app.py                 → hub Flask : monte les blueprints des modules + page d'accueil
├── main.py                → CLI unifié : dispatch vers chaque module
├── conftest.py            → rend `modules.*` importable par pytest
├── requirements.txt
│
├── modules/
│   ├── cicd/              → module CI/CD (GitHub Actions, GitLab CI, CircleCI, Jenkins, Drone)
│   │   ├── core.py            assemblage des workflows GitHub Actions
│   │   ├── gitlab_core.py     assemblage des pipelines GitLab CI
│   │   ├── circleci_core.py   assemblage des config.yml CircleCI
│   │   ├── jenkins_core.py    assemblage des Jenkinsfile (pipeline déclaratif)
│   │   ├── drone_core.py      assemblage des .drone.yml
│   │   ├── detector.py        détection auto du stack d'un dossier
│   │   ├── routes.py          Blueprint Flask (préfixe /cicd)
│   │   ├── cli.py             logique CLI du module
│   │   └── templates/         fragments YAML par langage + cibles de déploiement
│   │       ├── {python,node,go,rust,java,php}/{lint,test,build}.yml
│   │       └── deploy/{github_pages,docker_hub,ssh,vercel,aws_s3}.yml
│   │
│   └── ansible/           → module Ansible (provisioning + déploiement)
│       ├── core.py            playbooks, rôles, inventaire, vault, multi-groupes
│       ├── routes.py          Blueprint Flask (préfixe /ansible)
│       ├── cli.py             logique CLI du module
│   │   └── templates/
│   │       ├── provisioning/  base_packages, docker, nginx, https, firewall,
│   │       │                  ssh_hardening, fail2ban, monitoring, database/, runtime/
│   │       └── deployment/    git_clone, build, install_deps/, restart_service,
│   │                          reload_nginx, health_check, backup_previous,
│   │                          zero_downtime_deploy, notify
│   │
│   ├── vagrant/           → module Vagrant (portage de VagrantForge)
│   │   ├── core/              generateur, schema, presets, lint, verif_box
│   │   ├── routes.py          Blueprint Flask (préfixe /vagrant) + API
│   │   └── cli.py             sous-commandes generer/preset/valider/presets/verifier-box
│   │
│   └── terraform/        → module Terraform (builder, presets, backend, validation)
│       ├── core.py                  rendu HCL aligné + catalogue de ressources + presets
│       ├── cloudformation_core.py   export alternatif AWS CloudFormation (template.yaml)
│       ├── pulumi_core.py           export alternatif Pulumi Python (__main__.py)
│       ├── routes.py                Blueprint Flask (préfixe /terraform) + API
│       └── cli.py                   génération depuis un JSON de config ou un preset (--format)
│
│   └── dockerfile/       → module Dockerfile (multi-stage, 8 langages)
│       ├── core.py            assemblage du Dockerfile + .dockerignore par langage
│       ├── routes.py          Blueprint Flask (préfixe /dockerfile) + API
│       ├── cli.py             logique CLI du module
│       └── templates/         un .dockerfile par langage (+ java_maven/java_gradle)
│           └── dockerignore/  un .dockerignore par langage
│
│   └── k8s/              → module Kubernetes/Helm (manifests + chart)
│       ├── core.py            manifests (dicts → yaml.dump) + chart Helm + validation
│       ├── routes.py          Blueprint Flask (préfixe /k8s) + API + export .zip
│       ├── cli.py             logique CLI du module
│       └── templates/helm/    templates Go statiques du chart (pilotés par values.yaml)
│
│   ├── nginx/            → module Nginx (statique / reverse proxy / load balancer)
│   │   ├── core.py            assemblage server{}/upstream{} + validation + presets
│   │   ├── routes.py          Blueprint Flask (préfixe /nginx) + API
│   │   └── cli.py             logique CLI du module
│   │
│   ├── systemd/          → module systemd (unités .service / .timer)
│   │   ├── core.py            assemblage des sections INI + durcissement + presets
│   │   ├── routes.py          Blueprint Flask (préfixe /systemd) + API
│   │   └── cli.py             logique CLI du module
│   │
│   ├── monitoring/       → module Monitoring (Prometheus / alertes / Grafana)
│   │   ├── core.py            assemblage YAML (PyYAML) + catalogue de règles + presets
│   │   ├── routes.py          Blueprint Flask (préfixe /monitoring) + API
│   │   └── cli.py             logique CLI du module
│   │
│   ├── cloudinit/        → module cloud-init (#cloud-config / user-data)
│   │   ├── core.py            assemblage YAML (PyYAML) + users/write_files + presets
│   │   ├── routes.py          Blueprint Flask (préfixe /cloudinit) + API
│   │   └── cli.py             logique CLI du module
│   │
│   ├── packer/           → module Packer (build.pkr.hcl)
│   │   ├── core.py            rendu HCL2 (builder/provisioners/post-processors) + presets
│   │   ├── routes.py          Blueprint Flask (préfixe /packer) + API
│   │   └── cli.py             logique CLI du module
│   │
│   ├── vault/            → module HashiCorp Vault (config.hcl / policies / bootstrap.sh)
│   │   ├── core.py            rendu HCL (storage/seal/listener) + policies ACL + script bootstrap + presets
│   │   ├── routes.py          Blueprint Flask (préfixe /vault) + API
│   │   └── cli.py             logique CLI du module
│   │
│   └── gitops/           → module GitOps (ArgoCD Application / FluxCD)
│       ├── core.py            rendu YAML (ArgoCD Application, Flux GitRepository+Kustomization/HelmRelease) + presets
│       ├── routes.py          Blueprint Flask (préfixe /gitops) + API
│       └── cli.py             logique CLI du module
│
│   └── backup/           → module Backup/Restore (restic / Borg)
│       ├── core.py            rendu backup.sh/restore.sh idempotents + systemd/cron + env template + presets
│       ├── routes.py          Blueprint Flask (préfixe /backup) + API
│       └── cli.py             logique CLI du module
│
├── web/
│   ├── templates/         → hub.html, cicd.html, ansible.html, vagrant.html,
│   │                        terraform.html, dockerfile.html, k8s.html, nginx.html,
│   │                        systemd.html, monitoring.html, cloudinit.html, packer.html,
│   │                        vault.html, gitops.html, backup.html
│   │                        (terraform.html sert aussi le format CloudFormation)
│   └── static/
│       ├── theme.js           bascule clair/sombre partagée par les 15 pages
│       ├── cicd/{style.css, script.js}
│       ├── ansible/{style.css, script.js}
│       ├── dockerfile/{style.css, script.js}
│       ├── k8s/{style.css, script.js}
│       ├── nginx/{style.css, script.js}
│       ├── systemd/{style.css, script.js}
│       ├── monitoring/{style.css, script.js}
│       ├── cloudinit/{style.css, script.js}
│       ├── packer/{style.css, script.js}
│       ├── vault/{style.css, script.js}
│       ├── gitops/{style.css, script.js}
│       ├── backup/{style.css, script.js}
│       ├── manifest.json, service-worker.js, favicon.ico, opsforge-logo.svg, icons/
│
├── tests/
│   ├── cicd/              → detector, core, gitlab, circleci, jenkins, drone, bitbucket, teamcity, features avancées
│   ├── ansible/           → génération playbooks/rôles/inventaire/vault
│   ├── vagrant/           → génération Vagrantfile / presets / lint
│   ├── terraform/         → génération main.tf / cloudformation_core / presets / validation
│   ├── dockerfile/        → génération Dockerfile multi-stage / .dockerignore, 8 langages
│   ├── k8s/               → manifests K8s / chart Helm, validation DNS-1123
│   ├── nginx/             → génération server{}/upstream{}, validation par mode, presets
│   ├── systemd/           → génération .service/.timer, durcissement, presets
│   ├── monitoring/        → génération prometheus.yml/alertes/datasources, YAML valide
│   ├── cloudinit/         → génération #cloud-config, users/SSH/write_files, presets
│   ├── packer/            → génération build.pkr.hcl, builders/presets, validation
│   ├── vault/             → génération config.hcl/policies/bootstrap.sh, seal/storage, presets
│   ├── gitops/            → génération ArgoCD Application / Flux GitRepository+Kustomization/HelmRelease, presets
│   └── backup/            → génération backup.sh/restore.sh (bash -n), systemd/cron, presets
│
└── output/               → fichiers générés par défaut (CLI)
```

Chaque module est un **blueprint Flask** monté sous son préfixe (`/cicd`,
`/ansible`), qui partage les templates et assets statiques de l'app. Le hub
(`/`) ne fait que présenter les deux entrées.

---

## Module CI/CD — détails

Langages supportés : **Python, Node.js, Go, Rust, Java, PHP, Ruby, .NET** (jobs lint / test
/ build, avec détection du package manager et de la version). **7 plateformes** :

- **GitHub Actions** (`.github/workflows/ci.yml`) — déploiement GitHub Pages,
  Docker Hub, SSH, Vercel, AWS S3 ; secrets via Settings → Secrets and
  variables → Actions.
- **GitLab CI** (`.gitlab-ci.yml`) — déploiement GitLab Pages (job `pages`
  natif), Docker Hub, SSH, Vercel, AWS S3 ; variables CI/CD via Settings →
  CI/CD → Variables.
- **CircleCI** (`.circleci/config.yml`, version 2.1) — Docker Hub, SSH, Vercel,
  AWS S3 (pas de « pages » natif) ; matrix build via `parameters` +
  `matrix:` ; variables d'environnement via Project Settings.
- **Jenkins** (`Jenkinsfile`, pipeline déclaratif) — un `agent { docker {...} }`
  par stage (mélange de langages dans un seul fichier), identifiants via le
  Credentials Store (`credentials()`), déploiement SSH via le plugin SSH
  Agent (`sshagent`).
- **Drone** (`.drone.yml`) — steps séquentiels par défaut (pas de DAG), plugins
  officiels pour le déploiement (`plugins/docker`, `plugins/s3-sync`), secrets
  via `drone secret add`.
- **Bitbucket Pipelines** (`bitbucket-pipelines.yml`) — steps séquentiels par
  défaut comme Drone ; les steps de déploiement sont placés sous
  `pipelines.branches.<branche>` (pas d'équivalent direct à un filtre par step),
  variables via Repository Settings → Pipelines → Repository variables
  (cochées « Secured » pour les secrets).
- **TeamCity** (`.teamcity/settings.kts`, Kotlin DSL) — un `BuildType` Kotlin
  par étape (lint/test/build/deploy), dépendances explicites via
  `dependencies { snapshot(...) }`, exécution dans le conteneur voulu via le
  Docker Wrapper natif du step script (`dockerImage`/`dockerPull`), paramètres
  (type « Password » pour les secrets) via Administration → Parameters,
  référencés en `%nom.parametre%`.

Fonctions avancées (communes aux 7 plateformes) : matrix builds (tester
plusieurs versions en parallèle, GitHub/GitLab/CircleCI/Jenkins), déclenchement
cron (natif sur GitHub/CircleCI/Jenkins/TeamCity ; note d'instructions manuelle
sur GitLab/Drone/Bitbucket qui ne supportent pas de planification directement
dans le fichier de pipeline), badges de statut Markdown, dépendances entre
jobs (`needs:`/`requires:`/stages/`snapshot()` selon la plateforme).

Les jobs correspondent à des jobs séparés (`test-python`, `lint-node`…). Le YAML
généré est validé avec `pyyaml` avant d'être renvoyé (sauf Jenkins et TeamCity,
qui génèrent respectivement du Groovy et du Kotlin).

> Note : la clé `on:` des workflows GitHub Actions est générée entre guillemets
> (`"on":`) — YAML 1.1 interprète le mot nu `on` comme un booléen, ce qui
> cassait le parsing PyYAML.

### Mises à jour de dépendances (Dependabot / Renovate)

Extension du module CI/CD, pas un module à part : le fichier produit se dépose
dans le même dépôt que le pipeline et se déduit des **mêmes stacks détectées**.
Coché dans le formulaire (ou `--deps` en CLI), il apparaît dans un **second
onglet** à côté du pipeline.

- **Dependabot** (`.github/dependabot.yml`, version 2) — natif GitHub, rien à
  installer. Un bloc `updates:` par écosystème (`pip`, `npm`, `gomod`, `cargo`,
  `maven`/`gradle` selon le package manager Java détecté, `composer`,
  `bundler`, `nuget`), plus `github-actions` (toujours sur `/`, c'est là que
  vivent les workflows) et `docker` en option.
- **Renovate** (`renovate.json`) — plus configurable et **pas limité à
  GitHub** (GitLab, Bitbucket, auto-hébergé). `extends: config:recommended`,
  `enabledManagers` déduits des stacks, créneau horaire au lieu d'un simple
  intervalle (Renovate tourne en continu et se bride par `schedule`).

Dans les deux cas : les mises à jour **mineures et correctives sont
regroupées** en une seule PR (sinon le dépôt est noyé sous une PR par
dépendance), les **majeures restent isolées** (c'est là que ça casse), et les
**alertes de sécurité ne sont pas soumises au créneau** (`vulnerabilityAlerts`
en `at any time` côté Renovate). La branche cible reprend la première branche
déclenchante du pipeline.

Options CLI : `--deps dependabot|renovate`, `--deps-schedule daily|weekly|monthly`,
`--deps-docker` (surveiller aussi les images de base), `--deps-no-group`
(une PR par dépendance).

## Module Ansible — détails

- **Provisioning** : `update_system`, `base_packages`, `timezone`, `swap`,
  `unattended_upgrades` (MAJ sécurité auto), `users` (utilisateur de déploiement
  + sudo + clé SSH), `docker`, `nginx`, `https` (Let's Encrypt), `database`
  (PostgreSQL/MySQL/Redis/**MongoDB**), **`backups`** (sauvegarde quotidienne
  automatique via cron : dump de la base sélectionnée + archive du dossier
  applicatif, rotation configurable), `firewall` (UFW/firewalld),
  `ssh_hardening`, `fail2ban`, `monitoring` (Netdata), `runtime` (installe le
  runtime du langage choisi).
- **Déploiement** : `git_clone`, `install_deps`, `build`, `restart_service`,
  `reload_nginx`, `health_check`, `backup_previous`, `zero_downtime_deploy`,
  `notify` (webhook Slack/Discord).
- **Structures** : `flat` (un seul `playbook.yml`) ou `roles` (un rôle Ansible
  par étape). Génère aussi l'inventaire, un vault chiffré pour les secrets, et
  supporte le mode **multi-serveurs** (plusieurs groupes via un JSON).

### Cible Windows / WinRM

Sélectionnable dans l'UI (bouton « Cible » : Linux/SSH ou Windows/WinRM) ou en
CLI (`--target-os windows`, `--list-windows-steps` pour lister ce qui est
disponible). Un sous-ensemble d'étapes est proposé, avec des templates dédiés
utilisant les collections `ansible.windows.*`, `chocolatey.chocolatey.*` et
`community.windows.*` (à installer via `ansible-galaxy collection install
ansible.windows community.windows chocolatey.chocolatey`) plutôt que
apt/dnf/systemd :

- **Provisioning** : `update_system` (win_updates), `base_packages`
  (Chocolatey + git/curl/7zip), `users` (win_user + groupe Administrators),
  `firewall` (win_firewall_rule), `runtime` (Node.js/Python via Chocolatey —
  seuls ces deux langages sont supportés côté Windows).
- **Déploiement** : `backup_previous` (robocopy), `git_clone`, `install_deps`
  (npm/pip), `build`, `restart_service` (win_service), `health_check`
  (Test-NetConnection, avec message d'échec explicite — le rollback
  automatique n'est pas disponible côté Windows), `notify` (identique à la
  cible Linux : le webhook se déclenche depuis le contrôleur).
- Toute étape ou langage hors de cette liste est refusé avec un message
  d'erreur explicite listant ce qui est disponible.
- L'**inventaire** bascule automatiquement en connexion WinRM
  (`ansible_connection=winrm`, port 5986/HTTPS par défaut, transport `ntlm`
  par défaut) dès que la cible Windows est choisie — y compris par groupe en
  mode multi-serveurs.

### Tests de rôles avec Molecule

Disponible uniquement en mode `--layout roles` (ou `--groups-file`, par
groupe). Ajoute, pour **chaque rôle** du projet généré, un scénario
`roles/<rôle>/molecule/default/` complet :

- **`molecule.yml`** : driver au choix — `docker` (défaut, conteneur jetable
  `geerlingguy/docker-ubuntu2204-ansible`, systemd actif via `/usr/sbin/init`
  + cgroups montés, adapté aux rôles qui gèrent des services), `delegated`
  (applique directement sur la machine locale, sans VM ni conteneur — le
  plus rapide, utile en CI ou pour un test rapide) ou `vagrant` (VM
  VirtualBox, box `generic/ubuntu2204`, pour les rôles qui ont vraiment
  besoin d'un noyau/systemd complet, ex. modules bas niveau).
- **`converge.yml`** : applique le rôle seul sur `hosts: all`.
- **`verify.yml`** : assertions post-convergence en modules Ansible natifs
  (`ansible.builtin.assert`, `service_facts`, `package_facts` — pas de
  dépendance Testinfra). Une douzaine d'étapes ont une vérification dédiée
  (`docker`, `nginx`, `firewall`, `fail2ban`, `monitoring`, `https`,
  `users`, `swap`, `database`, `restart_service`, `runtime`) ; les autres
  reçoivent une vérification générique (confirme que `molecule converge`
  s'est terminé sans erreur) à compléter au besoin.
- **`requirements-molecule.txt`** : généré à la racine du projet
  (`pip install molecule ansible-core` + `molecule-plugins[docker]` ou
  `molecule-plugins[vagrant]` selon le driver ; rien de plus pour
  `delegated`).

```bash
pip install -r requirements-molecule.txt --break-system-packages
cd roles/docker && molecule test     # converge + verify + destroy
```

Sélecteur dans l'UI (case à cocher + choix du driver, section « Tests
Molecule ») ou `--molecule --molecule-driver docker|delegated|vagrant` en
CLI ; refusé avec un message explicite si combiné à `--layout flat` (pas de
rôles à tester individuellement dans ce mode).

## Module Vagrant — détails

Portage du cœur Python de **VagrantForge**. Génère un `Vagrantfile` multi-VM à
partir d'une config JSON : providers (VirtualBox, VMware, libvirt), réseau privé,
provisioning shell, locale/clavier. Fournit des **presets** prêts à l'emploi
(`solo`, `k3s`, `lamp`, `devsecops`, `pentest`, `monitoring`, `elk`,
`wordpress`, `gitlab-runner`), un **lint** du Vagrantfile généré, et une
vérification du catalogue de box face à Vagrant Cloud. L'interface web
(`/vagrant`) est le frontend autonome de VagrantForge, qui génère **côté client**
en JS ; l'API `/vagrant/api/*` est un bonus pour scripter via HTTP.

## Module Terraform — détails

À partir d'un provider (`aws`, `google`, `azurerm`, `docker`, `local`) et de
ressources, génère un `main.tf` (bloc `terraform{}` + `provider{}` +
`resource{}`). Fonctionnalités :

- **Builder de ressources** (web) : ajoute des ressources par cartes (type
  choisi dans un catalogue par provider, nom, arguments) ; un template
  d'arguments est pré-rempli selon le type.
- **Presets** prêts à l'emploi (`ec2-web`, `s3-static`, `docker-nginx`,
  `gcp-vm`, `vpc-basic`, `rds-postgres`, `docker-network-app`, `gcp-network`,
  `azure-vm`) — sélectionnables dans l'UI ou en CLI (`--preset`,
  `--list-presets`).
- **Catalogue de ressources élargi** : en plus des types de base, `aws_internet_gateway`,
  `aws_route_table` (+ association), `aws_iam_role`, `aws_lambda_function` (AWS) ;
  `google_compute_firewall`, `google_sql_database_instance` (GCP) ; `azurerm_virtual_network`,
  `azurerm_linux_virtual_machine` (Azure) ; `docker_network`, `docker_volume` (Docker) ;
  `local_sensitive_file` (local).
- **Export en fichiers séparés** : `main.tf` (terraform + provider + ressources),
  et `variables.tf` / `outputs.tf` dès qu'ils sont utilisés — téléchargeables en
  **`.zip`** depuis l'UI (bouton « Télécharger .zip ») ou en CLI (`--split -o mon-dossier/`).
- **Validation par provider** : vérifie les arguments requis de chaque type de
  ressource connu (`RESOURCE_CATALOG`), les noms dupliqués, le provider.
- **Sortie alignée** façon `terraform fmt` (les `=` d'un même bloc sont alignés).
- **variables** et **outputs** (section avancée de l'UI).
- Rendu HCL générique (chaînes, booléens, nombres, listes, blocs imbriqués).
  Une valeur préfixée par `=` est écrite **sans guillemets** — pour injecter une
  référence Terraform, ex. `"=aws_instance.web.id"` → `aws_instance.web.id`.

### Export CloudFormation

En plus du HCL Terraform, le module peut sortir un template **AWS
CloudFormation** (`template.yaml`) — sélecteur de format dans l'UI (le
builder de ressources devient AWS-only, la config provider/backend
disparaît) ou `--format cloudformation` en CLI. CloudFormation n'étant pas
multi-cloud, ce moteur a son propre catalogue de types (`AWS::Service::Resource`,
13 types : EC2, S3, VPC/Subnet/Route/Gateway, RDS, IAM, Lambda) et ses propres
presets (`ec2-web`, `s3-static`, `vpc-basic`, `rds-postgres`, préfixés `cfn-`
côté web pour ne pas entrer en collision avec les presets Terraform de même
nom). Les références entre ressources utilisent la même échappatoire `=` que
Terraform, mais en syntaxe courte CloudFormation : `"=!Ref MonBucket"` →
`!Ref MonBucket`, `"=!GetAtt Web.PublicIp"` → `!GetAtt Web.PublicIp`. Les
policy documents IAM se rendent nativement en YAML imbriqué (pas besoin d'un
équivalent à `jsonencode()`).

### Export Pulumi

Troisième moteur de sortie : un programme **Pulumi (Python)** (`__main__.py`)
— sélecteur de format `pulumi-aws` / `pulumi-google` / `pulumi-azurerm` /
`pulumi-docker` dans l'UI (pas de `pulumi-local`, Pulumi n'a pas
d'équivalent officiel au provider Terraform `hashicorp/local`) ou
`--format pulumi` en CLI. Contrairement à CloudFormation, Pulumi **réutilise
directement le catalogue de ressources Terraform** (`RESOURCE_CATALOG` de
`core.py`) plutôt que d'en avoir un à part : les SDK `pulumi_aws` /
`pulumi_gcp` / `pulumi_azure` sont dérivés des mêmes schémas de provider
Terraform, donc les noms d'arguments (déjà en snake_case) sont identiques.
Une table `RESOURCE_TYPE_MAP` fait juste correspondre chaque type Terraform
(`aws_instance`...) à sa classe Pulumi (`aws.ec2.Instance`) ; un type non
mappé est un **rejet explicite**, pas une génération générique (impossible
de produire un appel Python sans connaître la classe). 5 presets propres à
Pulumi (préfixés `pulumi:` côté web), avec des références déjà exprimées en
Python plutôt qu'en HCL. Même échappatoire `=`, mais en **Python brut**
cette fois : `"=aws_instance_web.public_ip"` → `aws_instance_web.public_ip`,
où le nom de variable est dérivé de façon déterministe (`type_name`
assaini) pour éviter toute collision si deux ressources de types différents
partagent le même `name`. La config du provider (région, projet…) n'est
**pas** injectée dans le code (pas idiomatique côté Pulumi) : un commentaire
rappelle la commande `pulumi config set` à lancer à la place.

## Module Dockerfile — détails

Réutilise le détecteur de stack du module CI/CD (`modules.cicd.detector`) pour
générer un `Dockerfile` **multi-stage** (stage `build` + stage `runtime`
allégé) adapté au langage détecté. Langages supportés : **Python, Node.js,
Go, Rust, Java (Maven/Gradle), PHP, Ruby, .NET**.

- **Multi-stage systématique** : le stage `build` contient les outils de
  compilation/installation, le stage `runtime` ne garde que le nécessaire
  (JRE au lieu du JDK+Maven, binaire seul pour Go/Rust, etc.).
- **Bonnes pratiques intégrées** : utilisateur non-root dans l'image finale,
  `.dockerignore` assorti au langage, layers cachables (dépendances copiées
  avant le code source).
- **Options** : port exposé, point d'entrée (fichier/binaire/DLL), dossier
  de travail — avec des valeurs par défaut sensées par langage, surchargeables
  dans l'UI ou en CLI (`--port`, `--entrypoint`, `--workdir`).
- **Cas particuliers** : Java choisit son template (Maven ou Gradle) selon
  le package manager détecté ; PHP sert via Apache (port 80 fixe, pas de
  point d'entrée) ; Java copie le `.jar` par wildcard (pas de point d'entrée
  à préciser non plus).
- Nécessite **Docker 23+ / BuildKit** (`# syntax=docker/dockerfile:1` en tête
  de fichier) pour les `COPY` optionnels (fichiers de lock absents tolérés).

## Module Kubernetes / Helm — détails

Deux modes de génération à partir du même formulaire (nom + image suffisent) :

- **Manifests bruts** : `Deployment` + `Service` (+ `Namespace` et `Ingress`
  optionnels), numérotés par ordre d'application (`00-` à `30-`) et prêts pour
  `kubectl apply -f`. Le YAML est **valide par construction** : les objets sont
  des dicts Python sérialisés par `yaml.dump` (jamais de templating de chaînes).
- **Chart Helm** : squelette complet (`Chart.yaml`, `values.yaml`,
  `templates/…`, `_helpers.tpl`, `.helmignore`). `Chart.yaml` et `values.yaml`
  sont générés depuis la config (l'`appVersion` reprend le tag de l'image) ;
  les templates Go sont statiques et entièrement pilotés par `values.yaml`.
  Téléchargeable en `.zip` depuis l'interface web.
- **Kustomize** : structure `base/` (les mêmes manifests, sans préfixe
  numérique) + `overlays/<env>/`, prête pour `kubectl apply -k`. Trois
  overlays par défaut — `dev` (1 replica), `staging` (2 replicas), `prod`
  (hérite du nombre de replicas de la base, sans patch) — chacun avec son
  propre `namePrefix` (`dev-`, `staging-`...) et un `commonLabels`
  (`app.kubernetes.io/environment`). Les patches de replicas sont des
  patchs stratégiques minimalistes (`patch-replicas.yaml`), référencés
  sans `target` explicite (matchés par `apiVersion`/`kind`/`metadata.name`).
  Personnalisable en CLI (`--overlays dev staging prod qa`, tout nom hors
  des presets connus produit un overlay sans patch) ou via l'API Python
  (`generate_kustomize(config, overlays={...})` pour fixer replicas/namespace
  par overlay).

Options couvertes : replicas, ports (conteneur/service), type de Service
(ClusterIP/NodePort/LoadBalancer), namespace, variables d'environnement,
probes HTTP liveness/readiness, resources requests/limits (défauts sensés),
Ingress (host, path, class, TLS avec secret `<nom>-tls`).

Validation intégrée : noms DNS-1123 (app et namespace), ports 1-65535,
Ingress sans host refusé — et avertissement si l'image n'a pas de tag
explicite (`:latest` implicite non reproductible).

---

## Module Nginx — détails

Trois modes, un seul formulaire (nom de domaine + options communes) :

- **Statique** : `root` + `index`, avec bascule **SPA** (`try_files $uri $uri/
  /index.html`) pour les apps React/Vue/Svelte coté client.
- **Reverse proxy** : `proxy_pass` vers un backend unique, en-têtes
  `X-Forwarded-*` inclus, option **WebSocket** (`Upgrade`/`Connection`).
- **Load balancer** : bloc `upstream{}` avec plusieurs backends (poids
  optionnel par serveur), algorithme **round robin** (défaut Nginx),
  **least_conn** ou **ip_hash**.

Options transverses : **HTTPS** (redirection 80→443 + bloc `ssl_certificate`
Let's Encrypt, pense-bête `certbot certonly --nginx` en commentaire), **gzip**,
**en-têtes de sécurité** (X-Frame-Options, X-Content-Type-Options…),
`client_max_body_size`. Presets prêts à l'emploi (`spa`, `static-site`,
`api-reverse-proxy`, `load-balanced-app`, `https-reverse-proxy`).

Validation intégrée par mode (backend/host/port requis, 2+ backends pour le
load balancer, algorithme et taille de body reconnus) ; chaque config générée
est **valide par construction** et a été testée avec `nginx -t` réel.

### Cibles Caddy, Traefik et HAProxy

Le **même formulaire** (mode + options) peut produire quatre formats de
sortie différents, sélectionnables dans l'UI (bouton « Cible ») ou en CLI
(`--target nginx|caddy|traefik|haproxy`, défaut `nginx`) :

- **Caddy** (`Caddyfile`) : `file_server` + `try_files` pour le statique,
  `reverse_proxy` (WebSocket géré nativement) pour le reverse proxy et le
  load balancer (`lb_policy round_robin|least_conn|ip_hash`), HTTPS
  automatique par défaut (Caddy gère lui-même Let's Encrypt — `https: false`
  force le préfixe `http://` pour désactiver le TLS auto), `encode gzip`,
  `header {}` pour les en-têtes de sécurité, `request_body { max_size … }`
  pour la taille max.
- **Traefik** (config dynamique **YAML**, provider `file`) : un `router`
  (règle `Host(...)`, `entryPoints` web/websecure, `tls.certResolver` si
  HTTPS) et un `service` `loadBalancer` (un ou plusieurs `servers`). Pas de
  mode **statique** côté Traefik (ce n'est pas un serveur de fichiers) — seuls
  `reverse_proxy` et `load_balancer` sont disponibles pour cette cible ;
  `ip_hash` devient une session collante par cookie (équivalent le plus
  proche), et `least_conn` n'a pas d'équivalent direct (note ajoutée dans le
  fichier généré).
- **HAProxy** (fragment `haproxy.cfg`) : un `frontend fe_<nom>` (+ un second
  `frontend fe_<nom>_http` qui redirige en 301 vers HTTPS si HTTPS est actif)
  et un `backend be_<nom>` avec `balance roundrobin|leastconn|source` selon
  l'algorithme choisi (`ip_hash` → `source`, le hash d'IP le plus proche
  nativement disponible), `server srv<n> host:port check` par backend (poids
  optionnel), `compression algo gzip` si gzip est activé, `http-response
  set-header` pour les en-têtes de sécurité, et `timeout tunnel 1h` si
  WebSocket est activé. Pas de mode **statique** non plus (pas de serveur de
  fichiers intégré) ; `client_max_body_size` n'a pas d'équivalent direct côté
  HAProxy (note ajoutée dans le fichier généré, avec la piste `http-request
  deny` ou un WAF en amont). Vérifiable avec `haproxy -c -f`.

---

## Module systemd — détails

Deux modes, un seul formulaire. Prolonge le module Ansible : ce qu'on déploie,
systemd le supervise.

- **Service** : une unité `<name>.service` avec `Type=` (simple/exec/forking/
  oneshot/notify), utilisateur & groupe dédiés, `WorkingDirectory`,
  `EnvironmentFile` + variables `Environment=`, hooks `ExecStartPre/Post`,
  **politique de redémarrage** (`Restart=` + `RestartSec=`) et dépendances
  (`After=`).
- **Timer** : une paire `<name>.service` (oneshot) + `<name>.timer` qui la
  déclenche — le remplaçant moderne de cron. `OnCalendar` (ou `OnBootSec`/
  `OnUnitActiveSec`) et **`Persistent=`** pour rattraper les exécutions
  manquées après un arrêt.

Options de **durcissement (sandboxing)** cochables : `NoNewPrivileges`,
`PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`. Presets prêts à l'emploi
(`web-app`, `background-worker`, `forking-daemon`, `daily-backup`,
`weekly-maintenance`).

Validation intégrée (nom d'unité, `ExecStart` requis, type/redémarrage
reconnus, planification obligatoire en mode timer) ; chaque unité est **valide
par construction** et sort avec son pense-bête d'installation (`cp` vers
`/etc/systemd/system/` + `daemon-reload` + `enable --now`) en commentaire.

---

## Module Monitoring — détails

Trois modes, un seul formulaire. Complète la chaîne : ce que Vagrant/Terraform
provisionne et que systemd supervise, ce module l'observe. Le YAML est produit
via **PyYAML** (donc toujours valide) puis préfixé d'un pense-bête
d'installation.

- **Prometheus** : `prometheus.yml` avec `global` (scrape/evaluation interval),
  **scrape_configs multi-jobs** (chaque job = un ou plusieurs `hôte:port`),
  câblage **Alertmanager** et référence **`rule_files`** en option.
- **Alertes** : fichier de règles d'alerte Prometheus (`alert.rules.yml`) à
  partir d'un **catalogue** (instance injoignable, CPU/mémoire/disque élevés,
  charge système), avec **seuils configurables** — les expressions PromQL
  restent intactes (pas de casse sur les `{label="…"}`).
- **Grafana** : provisioning de **datasources** (`datasource.yml`, `apiVersion 1`)
  — Prometheus, Loki, InfluxDB, Tempo… avec datasource par défaut.

Validation intégrée par mode (au moins un job/une règle/une datasource, cibles
`hôte:port`, durées Prometheus, seuils 1-100, types de datasource reconnus).
Presets prêts à l'emploi (`prometheus-node`, `prometheus-docker`,
`alerts-basic`, `grafana-prometheus`, `grafana-prom-loki`). Chaque fichier
peut être vérifié avec `promtool check`.

---

## Module cloud-init — détails

Ferme la chaîne : ce que Vagrant/Terraform **instancie**, cloud-init le
**configure au tout premier démarrage** — avant même qu'Ansible ne prenne le
relais. Un seul formulaire produit un `#cloud-config` (user-data), YAML valide
via PyYAML avec la ligne d'en-tête `#cloud-config` obligatoire.

- **Identité** : `hostname`, `timezone`.
- **Utilisateurs** : nom, groupes, **clés SSH** (le mot de passe est alors
  verrouillé automatiquement), `sudo` NOPASSWD en un clic.
- **Paquets** : `package_update` / `package_upgrade` + liste à installer.
- **write_files** : fichiers à écrire (chemin, permissions normalisées en
  `0644`, contenu).
- **runcmd** : commandes de premier boot.
- **Durcissement SSH** : `disable_root`, `ssh_pwauth: false` (clé uniquement).

Presets prêts à l'emploi (`docker-host`, `web-server`, `secure-baseline`,
`minimal`). Le fichier se passe en user-data (Terraform `user_data`, metadata
cloud, seed ISO NoCloud) et se vérifie avec `cloud-init schema`.

---

## Module Packer — détails

Dernier maillon de la chaîne : Packer **construit l'image** (ISO → box/VM
locale, ou instance cloud → AMI, ou conteneur), que Vagrant/Terraform
**instancient**, que cloud-init **configure au premier boot**, avant qu'Ansible
ne prenne le relais pour le déploiement applicatif. Un seul formulaire produit
un template HCL2 (`build.pkr.hcl`) prêt pour `packer build`.

- **Builder** (bloc `source`) : `virtualbox-iso` et `qemu` pour une image
  locale à partir d'une ISO, `amazon-ebs` pour une AMI AWS, `docker` pour une
  image de conteneur. Chaque builder a ses champs requis (validés) et ses
  valeurs par défaut sensées (`disk_size`, `headless`, `communicator`…),
  surchargeables via le builder d'arguments libre.
- **Plugin requis** : le bloc `packer { required_plugins { ... } }` est généré
  automatiquement selon le builder choisi (source + version du plugin
  HashiCorp officiel).
- **Variables Packer** : nom, type, valeur par défaut, `sensitive` optionnel —
  pour surcharger au build (`packer build -var ...`) sans toucher au template.
- **Provisioners** : `shell` (commandes inline ou script externe), `file`
  (upload d'un fichier/dossier local vers l'image en construction), et
  `powershell` (commandes inline PowerShell, pour une image Windows via
  WinRM).
- **Post-processors** : filtrés selon compatibilité avec le builder —
  `vagrant` (export `.box`, pour virtualbox-iso/qemu), `docker-tag` (tag
  d'image, pour docker), `compress` (archive `.tar.gz` de l'artefact, tous
  builders).
- **Export en fichiers séparés** : en plus du `build.pkr.hcl` unique,
  un bouton « Télécharger le projet (.zip) » (et `--split` en CLI) génère
  un projet Packer en 2-3 fichiers à la convention officielle
  (`variables.pkr.hcl` si des variables sont définies, `sources.pkr.hcl`,
  `build.pkr.hcl`), tous ramassés par `packer init <dossier>`.
- **Datasources** : `amazon-ami` pour piocher dynamiquement le dernier AMI
  correspondant à des filtres (au lieu d'un ID codé en dur), référencée dans
  un argument source via `=data.amazon-ami.<nom>.id`. Le plugin requis est
  fusionné avec celui du builder (pas de doublon si les deux sont `amazon`).
- **Provisioner `ansible`** : joue un playbook local sur l'image en
  construction (`playbook_file`, `user`) — relie Packer au module Ansible
  d'OpsForge dans un même pipeline.
- **Publication HCP Packer Registry** : bloc `hcp_packer_registry` optionnel
  dans le `build` (nom de bucket, description, labels), pour suivre l'image
  produite dans le registre HCP Packer — laisse le champ vide pour l'ignorer.

Presets prêts à l'emploi couvrant chaque famille de builder
(`ubuntu-vagrant-box`, `debian-qemu-image`, `aws-ami-webserver`,
`windows-server-ami`, `docker-app-image`) — dont un exemple Windows/WinRM
avec provisioner PowerShell, un exemple AWS avec datasource dynamique et
provisioner Ansible, et un exemple Docker avec publication HCP Packer
Registry. Le template se vérifie avec `packer validate` et s'initialise
avec `packer init` avant `packer build`.

---

## Module Vault — détails

Distinct de l'**Ansible Vault** existant (qui ne fait que chiffrer des
variables) : ce module génère la configuration du **serveur** HashiCorp
Vault lui-même. Trois artefacts, chacun avec le format qui lui correspond
vraiment :

- **`config.hcl`** (fichier de config natif Vault) :
  - **Storage** (`storage "..." { ... }`) : `file` (dev/single-node),
    `raft` (Integrated Storage, HA multi-nœuds, avec `node_id`), ou
    `consul` (backend externe). Chaque backend a ses arguments requis
    (validés) et ses valeurs par défaut.
  - **Listener** (`listener "tcp" { ... }`) : adresse d'écoute, TLS activé
    par défaut (`tls_cert_file`/`tls_key_file`) ou désactivé explicitement
    (`tls_disable = true`, dev uniquement).
  - **Seal** (`seal "..." { ... }`) : `shamir` (défaut, clés de
    descellement locales, aucun bloc généré car c'est le comportement par
    défaut de Vault), `awskms` (auto-unseal via AWS KMS) ou `transit`
    (auto-unseal via un autre cluster Vault) — chacun avec ses arguments
    requis (`region`/`kms_key_id`, ou `address`/`key_name`/`mount_path`).
  - `ui`, `api_addr`, `cluster_addr` (Raft), `cluster_name`, `log_level`.
- **`policies/<nom>.hcl`** (un fichier par policy) : blocs ACL
  `path "..." { capabilities = [...] }`, capacités validées contre la
  liste officielle (`create`, `read`, `update`, `delete`, `list`, `sudo`,
  `deny`).
- **`bootstrap.sh`** : script shell idempotent qui charge les policies
  (`vault policy write`), active les méthodes d'authentification
  (`vault auth enable` — userpass, approle, kubernetes, ldap, github, oidc,
  jwt, aws, gcp, azure, cert) et les moteurs de secrets (`vault secrets
  enable` — kv-v2/kv-v1, database, pki, transit, aws, ssh, gcp, azure,
  consul, nomad, totp), puis pousse leur configuration (`vault write
  <path>/config ...`) si fournie. Généré uniquement si au moins une
  policy, méthode d'auth ou moteur de secrets est déclaré — ce sont des
  opérations d'API/CLI à l'exécution (après initialisation + descellement),
  pas un format de fichier natif comme `config.hcl`.

Presets prêts à l'emploi : `dev-single-node` (storage `file`, TLS
désactivé, KV v2 + userpass — pour tester en local), `ha-raft-cluster`
(storage `raft`, TLS activé, policy admin), `app-secrets-kv` (KV v2 +
AppRole, policy applicative read/write), `pki-internal-ca` (moteur `pki`,
policy d'émission de certificats), `database-dynamic-creds` (moteur
`database`, auth Kubernetes, seal AWS KMS auto-unseal), `sso-oidc-login`
(auth OIDC via un fournisseur d'identité externe, KV v2), `multi-cloud-dynamic-creds`
(moteurs GCP + Azure, auth JWT — identifiants dynamiques multi-cloud).

Usage typique : `vault server -config=config.hcl`, puis une fois
`vault operator init` et `vault operator unseal` effectués,
`./bootstrap.sh` applique policies/auth/secrets engines d'un coup.

---

## Module GitOps — détails

Génère les manifests de déploiement continu (CD) pour Kubernetes, à partir
d'un dépôt Git surveillé. **Deux outils** :

- **ArgoCD** (`argocd-application.yaml`) : un manifest `Application`
  (CRD `argoproj.io/v1alpha1`) — `source` (repoURL/path/targetRevision),
  `destination` (cluster + namespace), `syncPolicy` (sync automatique avec
  `selfHeal`/`prune`, `syncOptions` dont `CreateNamespace=true`, retry avec
  backoff exponentiel).
- **FluxCD** (`flux-gitrepository.yaml` + `flux-kustomization.yaml` ou
  `flux-helmrelease.yaml`) : une `GitRepository` (source du dépôt) couplée
  soit à une `Kustomization` (manifests bruts ou overlay Kustomize), soit
  à une `HelmRelease` dont le chart est référencé via `sourceRef` de type
  `GitRepository` — évite de gérer un second type de source
  (`HelmRepository`) et garde une configuration symétrique avec ArgoCD :
  un seul `repo_url`/`path`/`revision` couvre les deux outils, quel que
  soit le type de source.

Trois types de source (`source_type`), gérés de façon identique pour les
deux outils : `raw` (manifests bruts), `kustomize` (overlay avec
`kustomization.yaml`), `helm` (chart hébergé dans le même dépôt Git).

> Note : contrairement à ArgoCD, la `Kustomization` FluxCD n'a pas
> d'option `createNamespace` native — le fichier généré inclut un
> commentaire rappelant d'ajouter un manifest `Namespace` au dépôt ou de
> créer le namespace manuellement avant la première synchronisation.

Presets prêts à l'emploi : `argocd-raw-manifests`, `argocd-kustomize`,
`argocd-helm-chart`, `flux-raw-manifests`, `flux-helm-chart`.

Usage typique : une fois ArgoCD ou Flux installé sur le cluster,
`kubectl apply -f argocd-application.yaml` (ArgoCD), ou
`kubectl apply -f flux-gitrepository.yaml -f flux-kustomization.yaml`
(Flux) — ou commiter ces fichiers dans le dépôt surveillé par
`flux bootstrap` si les sources sont elles-mêmes gérées via Git.

---

## Module Backup — détails

Génère un jeu de fichiers de sauvegarde/restauration prêts à déployer, pour
deux outils :

- **restic** : backends **local**, **SFTP**, **S3**. Repository initialisé
  de façon idempotente (`restic snapshots || restic init`), sauvegarde avec
  tags et exclusions, retention via `restic forget --keep-daily/-weekly/
  -monthly/-yearly --prune`.
- **Borg** (borgbackup) : backends **local**, **SFTP** (pas de S3 natif,
  volontairement non proposé pour rester honnête sur les capacités réelles
  de l'outil — il faudrait un montage rclone externe à OpsForge). Repository
  initialisé en `--encryption=repokey`, archives nommées
  `<app>-{now:%Y-%m-%d_%H%M%S}`, retention via `borg prune`.

Fichiers générés : **`backup.sh`** et **`restore.sh`** (exécutables,
idempotents, `set -euo pipefail`), **`backup.env.example`** (modèle —
la vraie passphrase et les identifiants ne sont **jamais** écrits en dur,
uniquement des références à des variables d'environnement chargées depuis
`backup.env`, à ne jamais committer), et selon la planification choisie :
**`<app>-backup.service`** + **`<app>-backup.timer`** (systemd, avec
`RandomizedDelaySec` et `Persistent=true`) ou **`crontab-entry.txt`** (ligne
prête à coller via `crontab -e`). Notification webhook optionnelle en cas
d'échec (`trap ... ERR`, compatible healthchecks.io/ntfy.sh/tout endpoint
acceptant un POST).

Presets prêts à l'emploi : `restic-local-systemd`, `restic-sftp-cron`,
`restic-s3-systemd` (avec notification webhook), `borg-local-systemd`,
`borg-sftp-cron`.

Usage typique : générer les fichiers, copier `backup.env.example` en
`backup.env` à côté de `backup.sh` et renseigner les vraies valeurs, puis
`systemctl enable --now <app>-backup.timer` (systemd) ou coller la ligne de
`crontab-entry.txt` via `crontab -e`.

---

## Module SSH — détails

Deux rôles, symétriques aux deux bouts d'une connexion.

**Côté client — `~/.ssh/config`** : un bloc `Host` par serveur (alias,
`HostName`, `User`, `Port`, `IdentityFile`), rebond via **`ProxyJump`** vers un
alias déclaré plus haut (accès à un réseau privé derrière un bastion),
redirections de ports (**`LocalForward`**, `RemoteForward`, `DynamicForward`
pour un proxy SOCKS), et un bloc `Host *` de réglages communs
(`ServerAliveInterval`, `AddKeysToAgent`, `IdentitiesOnly`, `HashKnownHosts`,
multiplexage `ControlMaster`/`ControlPersist`).

> Deux pièges gérés à la génération : le bloc `Host *` est écrit **en fin de
> fichier** (OpenSSH garde la *première* valeur trouvée pour chaque option —
> placé en tête, il court-circuiterait tous les blocs suivants), et les
> redirections sont écrites au format d'un fichier de config
> (`LocalForward 5432 localhost:5432`, avec un espace) et non au format de la
> ligne de commande `-L 5432:localhost:5432`.

**Côté serveur — `sshd_config.d/10-opsforge-durcissement.conf`** : un fragment
d'inclusion (mécanisme standard depuis Debian 12 / Ubuntu 22.04) plutôt qu'un
`sshd_config` complet réécrit — rien n'est écrasé, et le durcissement se retire
en supprimant le fichier. Le préfixe `10-` n'est pas décoratif : sshd garde la
**première** valeur lue dans `sshd_config.d/`, un `99-` arriverait après les
fragments de la distribution (`50-cloud-init.conf`…) et serait ignoré sur les
directives qu'ils définissent déjà.

Contenu : `PermitRootLogin`, `PasswordAuthentication`/`PubkeyAuthentication`,
`AllowUsers`/`AllowGroups`, `MaxAuthTries`, `LoginGraceTime`, keepalive,
`AllowTcpForwarding`/`AllowAgentForwarding`/`X11Forwarding`, `LogLevel`,
bannière, algorithmes modernes en option (`Ciphers`/`MACs`/`KexAlgorithms` sans
CBC, SHA-1 ni courbes NIST), et un bloc **`Match Group` SFTP chrooté**
(`ChrootDirectory` + `ForceCommand internal-sftp`, aucun shell) — toujours placé
en dernier, puisque tout ce qui suit un `Match` lui appartient.

**`authorized_keys` (option, rôle serveur)** : c'est le seul endroit où une
restriction s'applique à **une clé précise** — `from="203.0.113.0/24"`,
`command="/usr/local/bin/deploy.sh"`, `restrict` — là où `sshd_config` ne sait
raisonner que par utilisateur ou par groupe. Une clé privée collée par erreur
(`-----BEGIN …`) est refusée explicitement, comme un type de clé inconnu.

Presets : `poste-de-travail`, `acces-bastion`, `tunnels` (client),
`serveur-durci`, `bastion`, `sftp-only`, `cle-restreinte` (serveur).

Les fichiers écrits sur disque reçoivent les permissions attendues (`600` pour
`ssh_config` et `authorized_keys`, qu'OpenSSH ignore s'ils sont lisibles par
d'autres comptes). Avant de recharger sshd : `sudo sshd -t`, puis
`systemctl reload ssh` **en gardant une session ouverte** le temps de tester une
nouvelle connexion.

---

## Module Auth — détails

Deux moteurs pour protéger une appli déjà servie par le module `nginx` — celui-ci
gère le *comment on y accède*, celui-là le *qui a le droit*.

**oauth2-proxy** délègue l'authentification à un fournisseur externe (GitHub,
Google, OIDC générique, GitLab). Génère `oauth2-proxy.cfg` (provider, upstream,
identifiants, `cookie_secret` **généré aléatoirement** — contrairement à un
jeton OAuth lié à une identité externe, un secret de session local n'a pas de
« bonne » valeur à part aléatoire et unique, donc autant le produire tout de
suite) et un snippet Nginx (`auth_request` + redirection vers `/oauth2/sign_in`)
à coller dans le bloc `server{}` de l'appli protégée.

**Authelia** est un portail d'authentification autonome : comptes locaux, MFA
TOTP, règles d'accès **par domaine** avec plusieurs niveaux de politique
(`bypass`, `one_factor`, `two_factor`, `deny`), évaluées dans l'ordre. Génère
`configuration.yml` (backend fichier, stockage SQLite/PostgreSQL, notifications
fichier local ou SMTP, secrets de session/JWT/stockage générés aléatoirement)
et `users_database.yml`. Les mots de passe ne sont **jamais** générés en clair
— Authelia exige un hash argon2id, produit avec
`authelia crypto hash generate argon2`, le fichier ne contient qu'un
placeholder explicite à remplacer avant déploiement.

Presets : `github-org`, `google-domain`, `generic-oidc` (oauth2-proxy),
`homelab-simple`, `two-factor-sensitive`, `multi-domain` (Authelia).

---

## Module SOPS — détails

Comble un trou du module `gitops` : celui-ci génère des manifests ArgoCD/FluxCD
qui pointent vers un dépôt Git, mais rien n'y protège les secrets qu'on
voudrait y verser — `vault` gère les secrets **côté serveur**, pas ceux
versionnés dans le dépôt lui-même.

SOPS ne chiffre pas un fichier entier : il chiffre les **valeurs** d'un
YAML/JSON, les **clés restent en clair** — un `git diff` reste lisible, on voit
quelle clé a changé, pas sa nouvelle valeur. `.sops.yaml`, à la racine du
dépôt, associe chaque fichier (par `path_regex`) aux destinataires **age**
autorisés à le déchiffrer ; `sops` le lit tout seul, aucune option à répéter à
la main. `encrypted_regex` restreint le chiffrement à certaines clés
seulement (typiquement `^(data|stringData)$` pour un manifest Kubernetes
`Secret` : les métadonnées restent lisibles et diffables, seules les valeurs
sont illisibles).

Comme pour les clés SSH, seule la clé **publique** age (le destinataire) a sa
place dans une config versionnée — ce module ne génère ni ne manipule de clé
privée, celle-ci se produit avec `age-keygen`, hors d'OpsForge. En bonus, un
fragment `.gitattributes` (`sops-diff.gitattributes`, à fusionner à la main
plutôt qu'à écraser) active un driver de diff Git lisible sur les fichiers
chiffrés.

Presets : `solo-dev` (une clé), `team-shared` (plusieurs destinataires),
`multi-env` (une clé par environnement dev/staging/prod), `k8s-secrets`
(`encrypted_regex` ciblé), `terraform-tfvars` (`*.tfvars.json`).

---

## Tests

```bash
pip install -r requirements-dev.txt --break-system-packages
pytest tests/            # tous les modules
pytest tests/cicd/       # module CI/CD uniquement (GitHub/GitLab/CircleCI/Jenkins/Drone/Bitbucket/TeamCity)
pytest tests/ansible/    # module Ansible uniquement
pytest tests/ansible/test_molecule.py   # scaffolding Molecule uniquement
pytest tests/vagrant/    # module Vagrant uniquement
pytest tests/terraform/  # module Terraform uniquement
pytest tests/dockerfile/ # module Dockerfile uniquement
pytest tests/k8s/        # module Kubernetes/Helm uniquement
pytest tests/nginx/      # module Nginx uniquement
pytest tests/systemd/    # module systemd uniquement
pytest tests/monitoring/ # module Monitoring uniquement
pytest tests/cloudinit/  # module cloud-init uniquement
pytest tests/packer/     # module Packer uniquement
pytest tests/vault/      # module Vault uniquement
pytest tests/gitops/     # module GitOps uniquement
pytest tests/backup/     # module Backup uniquement
pytest tests/ssh/        # module SSH uniquement (client ~/.ssh/config + durcissement sshd)
pytest tests/authproxy/  # module Auth uniquement (oauth2-proxy / Authelia)
pytest tests/sops/       # module SOPS uniquement (secrets Git chiffres SOPS + age)
pytest tests/cicd/test_deps_core.py tests/cicd/test_deps_routes.py   # Dependabot / Renovate
```

> Sous Windows, 6 tests de chiffrement Vault sont **skippés proprement**
> (`skipif`) car `ansible-core` a besoin de `fcntl` (module Unix, absent
> nativement sous Windows). C'est une limite de plateforme, pas un bug du
> générateur — ils s'exécutent et passent sous Linux/WSL (et en CI GitHub,
> qui tourne sur `ubuntu-latest`).

---

## Roadmap — reste à faire

Les 20 modules sont fonctionnels et complets. Ce qui reste, par ordre de priorité :

- [x] ~~Module Backup~~ — fait (restic / Borg, voir plus bas).
- [x] ~~Module GitOps~~ — fait (ArgoCD Application / FluxCD, voir plus bas).
- [x] ~~Module Vault~~ — fait (`config.hcl`, policies ACL, `bootstrap.sh` — voir plus bas).

- [x] ~~Mode sombre unifié~~ — fait (bascule clair/sombre + persistance sur toutes les pages).
- [x] ~~Module Dockerfile~~ — fait (multi-stage, 8 langages, `.dockerignore`).
- [x] ~~Module Kubernetes/Helm~~ — fait (manifests + chart Helm, export .zip).
- [x] ~~Module Nginx~~ — fait (statique/reverse proxy/load balancer, HTTPS, presets).
- [x] ~~Module systemd~~ — fait (unités `.service` durcies / `.timer` planifiées, presets).
- [x] ~~Module Monitoring~~ — fait (prometheus.yml, règles d'alerte, datasources Grafana).
- [x] ~~Module cloud-init~~ — fait (#cloud-config : users/SSH, paquets, write_files, runcmd).
- [x] ~~Cible **Windows / WinRM** pour le module Ansible~~ — fait (sous-ensemble
      d'étapes dédiées `ansible.windows.*`/`chocolatey.chocolatey.*` :
      update_system, base_packages, users, firewall, runtime (node/python),
      backup_previous, git_clone, install_deps, build, restart_service,
      health_check, notify ; inventaire WinRM ; sélecteur de cible dans l'UI
      et `--target-os` en CLI).
- [x] ~~Terraform : export de `variables.tf` / `outputs.tf` séparés~~ — fait
      (fichiers séparés en `.zip` depuis l'UI, `--split` en CLI, 5 nouveaux
      presets et 11 nouveaux types de ressources au catalogue).
- [x] ~~Rôles supplémentaires côté Ansible (bases de données, backup)~~ — fait
      (moteur **MongoDB** ajouté, nouvelle étape **`backups`** : sauvegarde
      quotidienne automatique cron avec rotation, DB + dossier applicatif).
- [x] ~~Variantes Caddy et Traefik pour le module Nginx~~ — fait (même
      formulaire, sortie Caddyfile / config dynamique Traefik en YAML,
      sélecteur de cible dans l'UI et `--target` en CLI).
- [x] ~~Module Packer~~ — fait (`build.pkr.hcl` HCL2 : builders
      virtualbox-iso / qemu / amazon-ebs / docker, provisioners shell/file,
      post-processors vagrant / docker-tag / compress, 4 presets).
- [x] ~~Providers CircleCI, Jenkins, Drone pour le module CI/CD~~ — fait
      (`.circleci/config.yml`, `Jenkinsfile`, `.drone.yml`, mêmes cibles de
      déploiement docker_hub/ssh/vercel/aws_s3 que GitHub/GitLab, secrets/
      credentials/variables dédiés par plateforme, badges de statut).
- [x] ~~Providers Bitbucket Pipelines, TeamCity pour le module CI/CD~~ — fait
      (`bitbucket-pipelines.yml`, `.teamcity/settings.kts` Kotlin DSL, mêmes
      cibles de déploiement docker_hub/ssh/vercel/aws_s3, snapshot
      dependencies TeamCity, cron converti en champs Quartz-like, badges de
      statut).
- [x] ~~Nouveaux auth methods/secrets engines pour le module Vault~~ — fait
      (auth : oidc/jwt/aws/gcp/azure/cert en plus de userpass/approle/
      kubernetes/ldap/github ; secrets engines : gcp/azure/consul/nomad/totp
      en plus de kv-v2/kv-v1/database/pki/transit/aws/ssh ; 2 nouveaux
      presets `sso-oidc-login` et `multi-cloud-dynamic-creds`).
- [x] ~~**Module GitOps** (ArgoCD / FluxCD)~~ — fait (`argocd-application.yaml` :
      CRD `Application`, syncPolicy automated/selfHeal/prune, retry avec
      backoff ; `flux-gitrepository.yaml` + `flux-kustomization.yaml` ou
      `flux-helmrelease.yaml` : chart Helm référencé via `sourceRef` de
      type `GitRepository` pour rester symétrique avec ArgoCD sans gérer un
      second type de source. 3 types de source raw/kustomize/helm communs
      aux deux outils, 5 presets, sélecteur d'outil dans l'UI et
      `--preset`/`--list-*` en CLI).
- [x] ~~**Module Backup** (restic / Borg)~~ — fait (`backup.sh`/`restore.sh`
      idempotents, backends local/SFTP/S3 (restic) ou local/SFTP (Borg —
      pas de S3 natif, honnêtement non simulé), retention
      `--keep-daily/-weekly/-monthly/-yearly`, planification systemd
      timer ou cron, `backup.env.example` sans aucun secret en dur,
      notification webhook optionnelle sur échec. 5 presets, sélecteur
      d'outil dans l'UI et `--preset`/`--list-*` en CLI).
- [x] ~~Cible CloudFormation pour le module Terraform~~ — fait
      (`template.yaml` AWS : catalogue de 13 types de ressources CFN,
      4 presets, intrinsic functions `!Ref`/`!GetAtt`, sélecteur de format
      dans l'UI et `--format cloudformation` en CLI).
- [x] ~~Kustomize pour le module Kubernetes~~ — fait (troisième format à
      côté des manifests bruts et du chart Helm : `base/` + `overlays/dev,
      staging,prod/`, patches de replicas, `namePrefix`/`commonLabels` par
      overlay, overlays personnalisables en CLI et via l'API Python,
      sélecteur de mode dans l'UI).
- [x] ~~HAProxy pour le module Nginx~~ — fait (quatrième cible à côté de
      Nginx/Caddy/Traefik : fragment `haproxy.cfg`, `frontend`/`backend`,
      redirection HTTPS, compression, en-têtes de sécurité, sélecteur de
      cible dans l'UI et `--target haproxy` en CLI).
- [x] ~~Pulumi pour le module Terraform~~ — fait (troisième format à côté
      de HCL/CloudFormation : programme Python `__main__.py`, réutilise le
      catalogue de ressources Terraform pour aws/google/azurerm/docker —
      pas `local`, pas d'équivalent Pulumi officiel — 5 presets préfixés
      `pulumi:`, sélecteur `pulumi-<cloud>` dans l'UI et `--format pulumi`
      en CLI).

### Nouveaux modules envisagés

Tout générateur de config/IaC en Python (inputs → fichier) rentre dans le moule.
Candidats, du plus prioritaire au moins :

- [x] ~~**systemd**~~ — fait (unité `.service` + `.timer`, prolonge le déploiement Ansible).
- [x] ~~**Monitoring**~~ — fait (Prometheus `prometheus.yml` + alertes + datasources Grafana).
- [x] ~~**cloud-init**~~ — fait (`#cloud-config` : users/SSH, paquets, write_files, runcmd).
- [x] ~~**Packer**~~ — fait (build de templates HCL2, dernier candidat de la
      liste — complète Vagrant / cloud-init).

Tous les modules candidats de cette liste sont désormais implémentés. Les
prochaines pistes d'extension (nouveaux providers CI, nouvelles cibles IaC)
sont plutôt des ajouts *dans* les modules existants que de nouveaux modules
à part entière — CircleCI/Jenkins/Drone/Bitbucket/TeamCity (CI/CD),
CloudFormation et Pulumi (Terraform), Kustomize (K8s), HAProxy (Nginx) ont
déjà été traités ainsi. Plusieurs pistes sont venues s'ajouter depuis, et
illustrent bien la règle de partage entre nouveau module et extension : **SSH**
avait assez de matière (deux rôles, sept presets, trois formats de fichier)
pour devenir un **module à part entière**, tout comme **Auth** (deux moteurs
oauth2-proxy/Authelia, six presets, quatre formats de fichier) et **SOPS**
(règles multiples, cinq presets, deux formats de fichier) — alors que
**Dependabot/Renovate** — un seul petit fichier de config, déduit des stacks
déjà détectées — est resté une **extension du module CI/CD**. Les prochaines
directions restent des ajouts de providers/cibles supplémentaires (ex :
TeamCity/Bitbucket Pipelines pour le CI/CD, déjà faits ; d'autres pourraient
suivre selon les besoins).

> À éviter (doublons d'autres projets) : docker-compose = DockerForge ;
> réseau/firewall/VLAN = NetForge.

- [x] ~~**Kustomize** (module K8s)~~ — fait (troisième format à côté des
      manifests bruts et du chart Helm : `base/` + `overlays/<env>/`, presets
      `dev`/`staging`/`prod` avec patches de replicas, `namePrefix` et
      `commonLabels` par overlay, overlays personnalisables en CLI et via
      l'API Python).

Autres extensions possibles, par module :

- [x] ~~**HAProxy** (module Nginx)~~ — fait (même principe que les
      variantes Caddy/Traefik : fragment `haproxy.cfg` avec `frontend`/
      `backend`, `balance roundrobin|leastconn|source`, redirection HTTPS,
      compression, en-têtes de sécurité, sélecteur de cible dans l'UI et
      `--target haproxy` en CLI).
- [x] ~~**Dashboards Grafana** en JSON de panels réels (module Monitoring)~~ —
      fait (mode `dashboards` : `dashboard.json` prêt à importer, catalogue
      de 6 panels node_exporter — CPU/mémoire/disque/réseau/charge/uptime —
      types timeseries/gauge/stat, disposition en grille, sélecteur de
      datasource, preset `dashboard-node`).
- [x] ~~**Ignition** (module cloud-init)~~ — fait (config `config.ign` JSON
      spec 3.4.0, pour Fedora CoreOS/Flatcar/RHCOS : réutilise le MEME
      formulaire/schéma que `#cloud-config` — hostname, utilisateurs +
      clés SSH, `write_files` encodés en base64, `runcmd`. Paquets installés
      via `rpm-ostree install` et commandes `runcmd` enchaînées dans une
      unité systemd `oneshot` de premier boot générée automatiquement, avec
      redémarrage géré si des paquets sont demandés ; sélecteur de format
      dans l'UI et `--format ignition` en CLI).
- [x] ~~**Docker Bake** (`docker-bake.hcl`, module Dockerfile)~~ — fait
      (fichier `docker-bake.hcl` généré à côté du Dockerfile : `group
      "default"` + `target`, tags/nom d'image personnalisables, build
      multi-plateforme (`linux/amd64`/`linux/arm64` par défaut), variable
      `VERSION`, option `--push` pour pousser directement vers un registry ;
      case à cocher dans l'UI et `--bake` en CLI).
- [x] ~~**Scaffolding Molecule** (module Ansible)~~ — fait (un scenario
      `molecule/default/{molecule,converge,verify}.yml` genere par role en
      mode `--layout roles` / `--groups-file` : 3 drivers au choix
      (`docker` — conteneur jetable geerlingguy/Ubuntu 22.04, `delegated` —
      hote local sans VM, `vagrant` — VM VirtualBox), assertions de
      verification natives Ansible (`assert`/`service_facts`/`package_facts`)
      specifiques a une douzaine d'etapes (docker, nginx, firewall, fail2ban,
      monitoring, https, users, swap, database, restart_service, runtime),
      fallback generique pour les autres, `requirements-molecule.txt`
      genere selon le driver, case a cocher + selecteur de driver dans l'UI
      et `--molecule`/`--molecule-driver` en CLI).

- [x] ~~**Mises à jour de dépendances** (module CI/CD)~~ — fait, et
      volontairement **en extension du module CI/CD plutôt qu'en module à
      part** : ça produit un seul petit fichier de config
      (`.github/dependabot.yml` ou `renovate.json`), déduit des mêmes stacks
      détectées et déposé dans le même dépôt que le pipeline — pas assez de
      matière pour justifier une page et une CLI dédiées. Écosystèmes déduits
      des stacks, mineures/correctives regroupées, majeures isolées, alertes de
      sécurité hors créneau ; case dans l'UI (second onglet de résultat) et
      `--deps`/`--deps-schedule`/`--deps-docker`/`--deps-no-group` en CLI.

Deux candidats à un **nouveau module à part entière** avaient été identifiés,
et ils sont désormais traités :

- [x] ~~**HashiCorp Vault**~~ — fait (`config.hcl` : storage
      file/raft/consul, seal shamir/awskms/transit, listener TCP+TLS ;
      `policies/<nom>.hcl` : ACL avec capabilities validées ; `bootstrap.sh` :
      activation idempotente des auth methods — userpass/approle/kubernetes/
      ldap/github/oidc/jwt/aws/gcp/azure/cert — et des secrets engines —
      kv-v2/kv-v1/database/pki/transit/aws/ssh/gcp/azure/consul/nomad/totp —
      via `vault auth enable`/`vault secrets enable`/
      `vault policy write`. Distinct de l'Ansible Vault existant, qui ne
      fait que chiffrer des variables : ici c'est la configuration du
      serveur Vault lui-même. 7 presets, sélecteurs storage/seal dans l'UI
      et `--preset`/`--list-*` en CLI).

- [x] ~~**SSH**~~ — fait (deux rôles : `~/.ssh/config` côté client — alias,
      clés dédiées, `ProxyJump` vers un bastion, `LocalForward`/
      `DynamicForward`, bloc `Host *` en fin de fichier ; et fragment
      `sshd_config.d/10-opsforge-durcissement.conf` côté serveur —
      authentification par clé seule, `AllowGroups`, limites de session,
      forwarding, algorithmes modernes, bloc `Match Group` SFTP chrooté —
      plus un `authorized_keys` restreint par clé (`from=`, `command=`,
      `restrict`) en option. 7 presets, sélecteur de rôle dans l'UI et
      `--preset`/`--role`/`--port`/`--allow-groups` en CLI. Assez de matière
      pour un module complet, contrairement aux mises à jour de dépendances,
      traitées en extension du module CI/CD).

- [x] ~~**Auth** (authentification en frontal)~~ — fait (deux moteurs :
      **oauth2-proxy** — délègue à GitHub/Google/OIDC générique/GitLab,
      `oauth2-proxy.cfg` + snippet Nginx `auth_request`, `cookie_secret`
      généré aléatoirement ; **Authelia** — portail autonome, comptes
      locaux, MFA TOTP, `access_control.rules` par domaine avec politiques
      `bypass`/`one_factor`/`two_factor`/`deny` évaluées dans l'ordre,
      `configuration.yml` + `users_database.yml` avec hash argon2id en
      placeholder explicite — jamais de mot de passe en clair. 6 presets,
      sélecteur de moteur dans l'UI et `--preset`/`--engine` en CLI).
- [x] ~~**SOPS** (chiffrement de secrets Git)~~ — fait (`.sops.yaml` :
      règles `path_regex` → destinataires **age**, `encrypted_regex` pour
      ne chiffrer que certaines clés — ex : `^(data|stringData)$` sur un
      `Secret` Kubernetes, métadonnées en clair —, `input_type` par règle ;
      + fragment `.gitattributes` pour un diff Git lisible (driver
      `sopsdiffer`). Comble le trou laissé par le module GitOps existant
      (manifests ArgoCD/FluxCD sans réponse sur les secrets versionnés) ;
      ne génère ni ne manipule de clé privée, comme pour SSH. 5 presets,
      cartes de règles dans l'UI et `--preset` en CLI).

Tous les modules candidats identifiés dans cette roadmap sont désormais
implémentés. Les prochaines pistes restent des ajouts *dans* les modules
existants (nouveaux providers CI, nouvelles cibles IaC, nouveaux auth
methods/secrets engines Vault) plutôt que de nouveaux modules à part
entière.

### Déjà fait (résumé)


Fusion CI/CD + Ansible, ajout des modules Vagrant (portage complet, support
Windows/WinRM), Terraform (builder, presets, validation, backend distant),
Dockerfile (multi-stage, 8 langages) et Kubernetes/Helm (manifests + chart,
export .zip), unification visuelle CasaOS des pages, identité + icône
OpsForge, guides d'installation par OS, 8 langages CI/CD (Python, Node, Go,
Rust, Java, PHP, Ruby, .NET), bonnes pratiques workflows
(permissions/concurrency), étapes de provisioning Ansible étendues (timezone,
swap, unattended_upgrades, users), module Nginx (statique/reverse
proxy/load balancer, HTTPS, gzip, en-têtes de sécurité, validation par
`nginx -t` réel), module systemd (unités `.service` durcies et `.timer`
planifiées, durcissement/sandboxing, presets, pense-bête d'installation),
module Monitoring (prometheus.yml multi-jobs + Alertmanager, catalogue de
règles d'alerte à seuils, provisioning de datasources Grafana, YAML valide),
module cloud-init (`#cloud-config` de premier boot : utilisateurs + clés
SSH, paquets, write_files, runcmd, durcissement SSH, presets), et module
Packer (`build.pkr.hcl` HCL2 : builders virtualbox-iso / qemu / amazon-ebs /
docker, builder d'arguments source libre, provisioners shell-inline /
shell-script / file, post-processors vagrant / docker-tag / compress
filtrés selon compatibilité builder, variables Packer, 4 presets couvrant
chaque famille de builder) — dernier maillon de la chaîne Packer (construit
l'image) → Vagrant/Terraform (l'instancie) → cloud-init (la configure au
premier boot) → Ansible (déploiement applicatif). Puis extension des modules
existants plutôt que nouveaux modules : CI/CD passé de 2 à **5 plateformes**
(ajout CircleCI, Jenkins, Drone, mêmes cibles de déploiement et badges que
GitHub/GitLab), et Terraform gagne un second moteur de sortie, **CloudFormation**
(`template.yaml` AWS, catalogue et presets dédiés, sélecteur de format
UI/CLI).
