# OpsForge

[![CI](https://github.com/ton-user/OpsForge/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ton-user/OpsForge/actions/workflows/ci.yml)

> Remplace `ton-user` par ton nom d'utilisateur/organisation GitHub une fois
> le repo poussé (badge généré avec le propre module `cicd` d'OpsForge 🙂).

**Plusieurs forges DevOps dans un seul atelier**, 100 % en local :

| Module | Ce qu'il génère | Accès web | Sous-commande CLI |
|---|---|---|---|
| **CI/CD** | Pipelines **GitHub Actions** (`.github/workflows/ci.yml`) et **GitLab CI** (`.gitlab-ci.yml`) | `/cicd` | `python main.py cicd …` |
| **Ansible** | Playbooks de **provisioning + déploiement** serveur (paquets, Docker, Nginx, firewall, fail2ban, bases de données, vault chiffré, multi-serveurs) | `/ansible` | `python main.py ansible …` |
| **Vagrant** | **Vagrantfile multi-VM** (providers, réseau, provisioning, presets, lint) — portage de VagrantForge | `/vagrant` | `python main.py vagrant …` |
| **Terraform** | **`main.tf`** validé et aligné : builder de ressources, presets, validation par provider, variables/outputs | `/terraform` | `python main.py terraform …` |
| **Dockerfile** | **`Dockerfile`** multi-stage (build + runtime allégé) + `.dockerignore`, 8 langages, bonnes pratiques (utilisateur non-root) | `/dockerfile` | `python main.py dockerfile …` |
| **Kubernetes / Helm** | **Manifests** (Deployment + Service + Ingress, probes, resources) prêts pour `kubectl apply`, ou **chart Helm** complet, export `.zip` | `/k8s` | `python main.py k8s …` |

La page d'accueil (`/`) est un **hub** qui renvoie vers les modules. Rien
n'est jamais envoyé sur un serveur externe : tout tourne sur ta machine.

OpsForge fait partie de la suite **Forge** (avec DockerForge, gardé séparé car
c'est une appli React/Vite).

> **Historique** : OpsForge est né de la fusion de deux générateurs qui
> partageaient la même architecture (`ci-cd-generator` et `ansible-generator`),
> puis a accueilli le cœur de **VagrantForge** en module et un module
> **Terraform** neuf. Même logique que NetForge et ses modules réseau : chaque
> générateur reste un bloc autonome (core + routes + cli + templates), juste
> monté sous un préfixe (`/cicd`, `/ansible`, `/vagrant`, `/terraform`).
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

# Apercu sans rien ecrire sur disque
python main.py cicd . --dry-run
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
│       ├── core.py            rendu HCL aligné + catalogue de ressources + presets
│       ├── routes.py          Blueprint Flask (préfixe /terraform) + API
│       └── cli.py             génération depuis un JSON de config ou un preset
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
├── web/
│   ├── templates/         → hub.html, cicd.html, ansible.html, vagrant.html,
│   │                        terraform.html, dockerfile.html, k8s.html
│   └── static/
│       ├── theme.js           bascule clair/sombre partagée par les 7 pages
│       ├── cicd/{style.css, script.js}
│       ├── ansible/{style.css, script.js}
│       ├── dockerfile/{style.css, script.js}
│       ├── k8s/{style.css, script.js}
│       ├── manifest.json, service-worker.js, favicon.ico, logo.svg, icons/
│
├── tests/
│   ├── cicd/              → 4 suites (detector, core, gitlab, features avancées)
│   ├── ansible/           → génération playbooks/rôles/inventaire/vault
│   ├── vagrant/           → génération Vagrantfile / presets / lint
│   ├── terraform/         → génération main.tf / presets / validation
│   ├── dockerfile/        → génération Dockerfile multi-stage / .dockerignore, 8 langages
│   └── k8s/               → manifests K8s / chart Helm, validation DNS-1123
│
└── output/               → fichiers générés par défaut (CLI)
```

Chaque module est un **blueprint Flask** monté sous son préfixe (`/cicd`,
`/ansible`), qui partage les templates et assets statiques de l'app. Le hub
(`/`) ne fait que présenter les deux entrées.

---

## Module CI/CD — détails

Langages supportés : **Python, Node.js, Go, Rust, Java, PHP, Ruby, .NET** (jobs lint / test
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

- **Provisioning** : `update_system`, `base_packages`, `timezone`, `swap`,
  `unattended_upgrades` (MAJ sécurité auto), `users` (utilisateur de déploiement
  + sudo + clé SSH), `docker`, `nginx`, `https` (Let's Encrypt), `database`
  (PostgreSQL/MySQL/Redis), `firewall` (UFW/firewalld), `ssh_hardening`,
  `fail2ban`, `monitoring` (Netdata), `runtime` (installe le runtime du langage
  choisi).
- **Déploiement** : `git_clone`, `install_deps`, `build`, `restart_service`,
  `reload_nginx`, `health_check`, `backup_previous`, `zero_downtime_deploy`,
  `notify` (webhook Slack/Discord).
- **Structures** : `flat` (un seul `playbook.yml`) ou `roles` (un rôle Ansible
  par étape). Génère aussi l'inventaire, un vault chiffré pour les secrets, et
  supporte le mode **multi-serveurs** (plusieurs groupes via un JSON).

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
  `gcp-vm`) — sélectionnables dans l'UI ou en CLI (`--preset`, `--list-presets`).
- **Validation par provider** : vérifie les arguments requis de chaque type de
  ressource connu (`RESOURCE_CATALOG`), les noms dupliqués, le provider.
- **Sortie alignée** façon `terraform fmt` (les `=` d'un même bloc sont alignés).
- **variables** et **outputs** (section avancée de l'UI).
- Rendu HCL générique (chaînes, booléens, nombres, listes, blocs imbriqués).
  Une valeur préfixée par `=` est écrite **sans guillemets** — pour injecter une
  référence Terraform, ex. `"=aws_instance.web.id"` → `aws_instance.web.id`.

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

Options couvertes : replicas, ports (conteneur/service), type de Service
(ClusterIP/NodePort/LoadBalancer), namespace, variables d'environnement,
probes HTTP liveness/readiness, resources requests/limits (défauts sensés),
Ingress (host, path, class, TLS avec secret `<nom>-tls`).

Validation intégrée : noms DNS-1123 (app et namespace), ports 1-65535,
Ingress sans host refusé — et avertissement si l'image n'a pas de tag
explicite (`:latest` implicite non reproductible).

---

## Tests

```bash
pip install -r requirements-dev.txt --break-system-packages
pytest tests/            # tous les modules
pytest tests/cicd/       # module CI/CD uniquement
pytest tests/ansible/    # module Ansible uniquement
pytest tests/vagrant/    # module Vagrant uniquement
pytest tests/terraform/  # module Terraform uniquement
pytest tests/dockerfile/ # module Dockerfile uniquement
pytest tests/k8s/        # module Kubernetes/Helm uniquement
```

> Sous Windows, 3 tests de chiffrement Vault échouent car `ansible-core` a besoin
> de `fcntl` (module Unix). C'est une limite de plateforme, pas un bug du
> générateur — ils passent sous Linux/WSL.

---

## Roadmap — reste à faire

Les 5 modules sont fonctionnels et complets. Ce qui reste, par ordre de priorité :

- [x] ~~Mode sombre unifié~~ — fait (bascule clair/sombre + persistance sur les 6 pages).
- [x] ~~Module Dockerfile~~ — fait (multi-stage, 8 langages, `.dockerignore`).
- [x] ~~Module Kubernetes/Helm~~ — fait (manifests + chart Helm, export .zip).
- [ ] *(optionnel)* Cible **Windows / WinRM** pour le module Ansible (comme
      Vagrant qui gère déjà Windows).
- [ ] *(optionnel)* Terraform : export de `variables.tf` / `outputs.tf` séparés
      en `.zip`, davantage de presets et de types de ressources au catalogue.
- [ ] *(optionnel)* Rôles supplémentaires côté Ansible (bases de données, backup).

### Nouveaux modules envisagés

Tout générateur de config/IaC en Python (inputs → fichier) rentre dans le moule.
Candidats, du plus prioritaire au moins :

- [ ] **Nginx / reverse-proxy** (+ variantes Caddy, Traefik) — server blocks,
      HTTPS, load-balancing.
- [ ] **systemd** — unité `.service` + timer (prolonge le déploiement Ansible).
- [ ] **Packer** (images de VM) et **cloud-init** (première init) — complètent
      Vagrant / Terraform.
- [ ] **Monitoring** — Prometheus (`prometheus.yml`, alertes) + datasources Grafana.

> À intégrer aux modules existants plutôt que comme nouveaux modules : autres
> systèmes CI (CircleCI, Jenkins, Drone…) = providers du module CI/CD ;
> CloudFormation/Pulumi = cibles à côté de Terraform.
>
> À éviter (doublons d'autres projets) : docker-compose = DockerForge ;
> réseau/firewall/VLAN = NetForge.

### Déjà fait (résumé)


Fusion CI/CD + Ansible, ajout des modules Vagrant (portage complet, support
Windows/WinRM) et Terraform (builder, presets, validation, backend distant),
unification visuelle CasaOS des 5 pages, identité + icône OpsForge, guides
d'installation par OS, 8 langages CI/CD (Python, Node, Go, Rust, Java, PHP,
Ruby, .NET), bonnes pratiques workflows (permissions/concurrency), étapes de
provisioning Ansible étendues (timezone, swap, unattended_upgrades, users).
