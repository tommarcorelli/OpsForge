# OpsForge

**Deux forges DevOps dans un seul atelier**, 100 % en local :

| Module | Ce qu'il génère | Accès web | Sous-commande CLI |
|---|---|---|---|
| **CI/CD** | Pipelines **GitHub Actions** (`.github/workflows/ci.yml`) et **GitLab CI** (`.gitlab-ci.yml`) | `/cicd` | `python main.py cicd …` |
| **Ansible** | Playbooks de **provisioning + déploiement** serveur (paquets, Docker, Nginx, firewall, fail2ban, bases de données, vault chiffré, multi-serveurs) | `/ansible` | `python main.py ansible …` |

La page d'accueil (`/`) est un **hub** qui renvoie vers les deux modules. Rien
n'est jamais envoyé sur un serveur externe : tout tourne sur ta machine.

OpsForge fait partie de la suite **Forge** (avec VagrantForge et DockerForge).

> **Historique** : OpsForge est né de la fusion de deux générateurs qui
> partageaient la même architecture (`ci-cd-generator` et `ansible-generator`).
> Ils sont désormais réunis en deux modules sous un même toit — même logique que
> NetForge et ses modules réseau. Le code de chaque générateur est préservé tel
> quel, juste réorganisé.

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

L'interface est installable comme **PWA** (Chrome/Edge : icône dans la barre
d'adresse ; mobile : « Ajouter à l'écran d'accueil »).

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
```

Sortie par défaut : dossier `output/` à la racine du projet.

---

## Architecture

```
opsforge/
├── app.py                 → hub Flask : monte les 2 blueprints + page d'accueil
├── main.py                → CLI unifié : dispatch vers cicd/ ou ansible/
├── conftest.py            → rend `modules.*` importable par pytest
├── requirements.txt
│
├── modules/
│   ├── cicd/              → module CI/CD (GitHub Actions & GitLab CI)
│   │   ├── core.py            assemblage des workflows GitHub Actions
│   │   ├── gitlab_core.py     assemblage des pipelines GitLab CI
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
│       └── templates/
│           ├── provisioning/  base_packages, docker, nginx, https, firewall,
│           │                  ssh_hardening, fail2ban, monitoring, database/, runtime/
│           └── deployment/    git_clone, build, install_deps/, restart_service,
│                              reload_nginx, health_check, backup_previous,
│                              zero_downtime_deploy, notify
│
├── web/
│   ├── templates/         → hub.html, cicd.html, ansible.html
│   └── static/
│       ├── cicd/{style.css, script.js}
│       ├── ansible/{style.css, script.js}
│       ├── manifest.json, service-worker.js, favicon.ico, logo.svg, icons/
│
├── tests/
│   ├── cicd/              → 4 suites (detector, core, gitlab, features avancées)
│   └── ansible/           → génération playbooks/rôles/inventaire/vault
│
└── output/               → fichiers générés par défaut (CLI)
```

Chaque module est un **blueprint Flask** monté sous son préfixe (`/cicd`,
`/ansible`), qui partage les templates et assets statiques de l'app. Le hub
(`/`) ne fait que présenter les deux entrées.

---

## Module CI/CD — détails

Langages supportés : **Python, Node.js, Go, Rust, Java, PHP** (jobs lint / test
/ build, avec détection du package manager et de la version). Cibles de
déploiement : **GitHub Pages, Docker Hub, SSH, Vercel, AWS S3** (GitHub) et
**GitLab Pages, Docker Hub, SSH** (GitLab). Fonctions avancées : matrix builds
(tester plusieurs versions en parallèle), déclenchement cron, badges de statut
Markdown, dépendances entre jobs (`needs:`).

Les jobs correspondent à des jobs séparés (`test-python`, `lint-node`…). Le YAML
généré est validé avec `pyyaml` avant d'être renvoyé.

> Note : la clé `on:` des workflows GitHub Actions est générée entre guillemets
> (`"on":`) — YAML 1.1 interprète le mot nu `on` comme un booléen, ce qui
> cassait le parsing PyYAML.

## Module Ansible — détails

- **Provisioning** : `update_system`, `base_packages`, `docker`, `nginx`,
  `https` (Let's Encrypt), `database` (PostgreSQL/MySQL/Redis), `firewall`
  (UFW/firewalld), `ssh_hardening`, `fail2ban`, `monitoring` (Netdata),
  `runtime` (installe le runtime du langage choisi).
- **Déploiement** : `git_clone`, `install_deps`, `build`, `restart_service`,
  `reload_nginx`, `health_check`, `backup_previous`, `zero_downtime_deploy`,
  `notify` (webhook Slack/Discord).
- **Structures** : `flat` (un seul `playbook.yml`) ou `roles` (un rôle Ansible
  par étape). Génère aussi l'inventaire, un vault chiffré pour les secrets, et
  supporte le mode **multi-serveurs** (plusieurs groupes via un JSON).

---

## Tests

```bash
pip install -r requirements-dev.txt --break-system-packages
pytest tests/            # les 2 modules
pytest tests/cicd/       # module CI/CD uniquement
pytest tests/ansible/    # module Ansible uniquement
```

> Sous Windows, 3 tests de chiffrement Vault échouent car `ansible-core` a besoin
> de `fcntl` (module Unix). C'est une limite de plateforme, pas un bug du
> générateur — ils passent sous Linux/WSL.
