# OpsForge

Générateur de pipeline CI/CD prêt à l'emploi — `.github/workflows/ci.yml`
pour **GitHub Actions**, ou `.gitlab-ci.yml` pour **GitLab CI** — à
partir de ton stack technique (Python, Node.js, Go, Rust, Java, PHP).

OpsForge fait partie de la suite « Forge » (avec VagrantForge et
DockerForge). À terme, il couvrira aussi le **provisioning serveur via
Ansible** (voir la Roadmap) — les templates de playbooks sont déjà
présents dans `templates/provisioning/` et `templates/deployment/`,
le moteur de génération reste à écrire.

Deux façons de l'utiliser :
- **En ligne de commande** (`main.py`)
- **Via une interface web locale** (`app.py`, Flask)

Le projet peut soit **détecter automatiquement** le stack d'un dossier
(en cherchant des fichiers comme `package.json`, `pyproject.toml`,
`go.mod`...), soit fonctionner en **sélection manuelle** si tu préfères
choisir toi-même.

---

## Sommaire

- [Installation](#installation)
- [Utilisation — CLI](#utilisation--cli)
- [Utilisation — Interface web](#utilisation--interface-web)
- [Stacks et jobs supportés](#stacks-et-jobs-supportés)
- [Architecture du projet](#architecture-du-projet)
- [Comment ça marche en détail](#comment-ça-marche-en-détail)
- [Ajouter un nouveau langage](#ajouter-un-nouveau-langage)
- [Limitations connues](#limitations-connues)
- [Roadmap](#roadmap)

---

## Installation

```bash
pip install -r requirements.txt --break-system-packages
```

Dépendances : `flask` (interface web) et `pyyaml` (validation du YAML généré).

---

## Utilisation — CLI

```bash
python main.py /chemin/vers/mon/projet
```

Ça analyse le dossier, détecte le(s) stack(s), et écrit un fichier
`output/ci.yml` par défaut.

### Options disponibles

| Option | Description | Exemple |
|---|---|---|
| `--provider` | `github` (défaut) ou `gitlab` | `--provider gitlab` |
| `--jobs` | Jobs à inclure parmi `lint`, `test`, `build` | `--jobs lint test` |
| `--output` | Chemin de sortie du fichier `.yml` | `--output .github/workflows/ci.yml` |
| `--branches` | Branches qui déclenchent le pipeline | `--branches main develop` |
| `--deploy` | Cible(s) de déploiement : `github_pages`/`gitlab_pages`, `docker_hub`, `ssh` | `--deploy docker_hub` |
| `--pages-dir` | [github_pages] Dossier du build statique | `--pages-dir dist` |
| `--pages-build-cmd` | [github_pages] Commande de build | `--pages-build-cmd "npm run build"` |
| `--docker-image` | [docker_hub] Nom de l'image | `--docker-image monusername/monapp` |
| `--deploy-path` | [ssh] Chemin distant | `--deploy-path /var/www/monapp` |
| `--service-name` | [ssh] Service systemd à redémarrer | `--service-name monapp` |

### Exemple complet (avec déploiement)

```bash
python main.py . \
  --jobs lint test build \
  --branches main \
  --deploy docker_hub ssh \
  --docker-image monusername/monapp \
  --deploy-path /var/www/monapp \
  --service-name monapp \
  --output .github/workflows/ci.yml
```

Si aucune stack n'est détectée, le script s'arrête avec un message
d'erreur explicite (aucun fichier généré à moitié).

---

## Utilisation — Interface web

```bash
python app.py
```

Puis ouvre **http://127.0.0.1:5050** dans ton navigateur. C'est une
appli 100% locale : rien n'est envoyé sur un serveur externe.

Si le port 5050 est lui aussi déjà utilisé sur ta machine, tu peux en
choisir un autre :

```bash
PORT=8080 python app.py
```

### Étapes dans l'interface

1. **Chemin du projet** — renseigne un chemin absolu et clique sur
   "Détecter" pour lancer la détection automatique. Laisse vide si tu
   préfères choisir manuellement.
2. **Stack(s)** — affichées automatiquement après détection, ou à
   cocher toi-même dans la liste si tu n'as pas renseigné de chemin.
3. **Jobs à inclure** — coche lint / test / build. Le schéma en haut à
   droite s'illumine en fonction de tes choix, pour visualiser le
   pipeline avant de le générer.
4. **Branches déclenchantes** — les branches qui lanceront le pipeline
   (`main`, `develop`, etc.), séparées par des virgules.
5. **Déploiement (optionnel)** — coche une ou plusieurs cibles parmi
   GitHub Pages, Docker Hub, Serveur SSH. Des champs spécifiques
   apparaissent selon la cible choisie (nom de l'image Docker, chemin
   de déploiement...). GitHub Pages n'apparaît que si une stack Node
   est sélectionnée (nécessaire pour builder un site statique).
6. **Générer** — affiche le YAML final, avec des boutons pour le
   copier dans le presse-papier ou le télécharger directement en
   `ci.yml`.

Un **sélecteur en haut du formulaire** permet de basculer entre
GitHub Actions et GitLab CI — les champs s'adaptent automatiquement
(libellés, secrets/variables mentionnés).

### Installer comme une application (PWA)

L'interface est installable comme une vraie application :
- **Chrome/Edge (desktop)** : icône d'installation dans la barre
  d'adresse, ou menu ⋮ → "Installer OpsForge"
- **Mobile (Android/iOS)** : menu du navigateur → "Ajouter à l'écran
  d'accueil"

Une fois installée, elle s'ouvre dans sa propre fenêtre (sans barre
d'adresse) et fonctionne partiellement hors-ligne (l'interface se
charge même sans connexion, mais générer un pipeline nécessite que
`python app.py` tourne toujours en arrière-plan sur ta machine).

---

## GitLab CI — spécificités

Le générateur GitLab CI suit la même logique que GitHub Actions, avec
quelques différences propres à la plateforme :

- **Pas de `needs:` explicite** : GitLab exécute déjà tous les jobs
  d'un même `stage` en parallèle, et attend qu'un stage soit terminé
  avant de passer au suivant. L'ordre lint → test → build → deploy est
  donc obtenu simplement en plaçant chaque job dans le bon stage.
- **GitLab Pages** : le job doit s'appeler **exactement** `pages` pour
  que GitLab le reconnaisse (c'est fait automatiquement). Nécessite
  une stack Node, comme pour GitHub Pages.
- **Docker Hub** : utilise l'image `docker:24` avec le service
  `docker:24-dind` (Docker-in-Docker), au lieu d'une action dédiée.
- **Secrets** : sur GitLab, on parle de **variables CI/CD** (Settings
  → CI/CD → Variables) plutôt que de "secrets", mais le principe est
  identique — mêmes noms de variables que pour GitHub
  (`DOCKERHUB_USERNAME`, `SSH_HOST`, etc.) pour rester cohérent.

---

## Stacks et jobs supportés

| Langage | Lint | Test | Build | Package managers détectés |
|---|---|---|---|---|
| Python | flake8 | pytest | `python -m build` | pip, poetry, pipenv |
| Node.js | `npm run lint` | `npm test` | `npm run build` | npm, yarn, pnpm |
| Go | golangci-lint | `go test` | `go build` | go modules |
| Rust | clippy | `cargo test` | `cargo build --release` | cargo |
| Java | compile check | `mvn test` | `mvn package` | maven, gradle |
| PHP | `php -l` (syntaxe) | PHPUnit | composer (prod) | composer |

Les jobs correspondent à des **jobs GitHub Actions séparés**
(`lint-python`, `test-node`, etc.). Le job `lint` tourne toujours en
parallèle (feedback le plus rapide possible). Si `test` **et** `build`
sont tous les deux sélectionnés pour une même stack, `build` attend
que `test` réussisse (`needs: test-xxx`) — un vrai pipeline séquentiel,
pas juste des jobs qui tournent en parallèle sans lien entre eux.

---

## Déploiement

Trois cibles de déploiement disponibles, à cocher en plus des jobs
lint/test/build. **Chaque job de déploiement attend que le dernier job
de build (ou de test, s'il n'y a pas de build) réussisse** avant de se
lancer — pas de déploiement d'un code qui ne compile pas ou dont les
tests échouent.

### GitHub Pages

Build un site statique et le publie automatiquement. **Nécessite une
stack Node** dans ta sélection (c'est actuellement la seule prise en
charge pour ce type de déploiement). Si aucune stack Node n'est
présente, cette cible est **ignorée silencieusement** — pas d'erreur,
juste pas de job généré pour elle.

- Aucun secret GitHub à configurer (utilise le token automatique
  `GITHUB_TOKEN`, déjà fourni par GitHub Actions).
- Champs à renseigner : dossier du build (`dist` par défaut), commande
  de build (`npm run build` par défaut).

### Docker Hub

Build ton image Docker et la pousse sur Docker Hub. Nécessite un
`Dockerfile` à la racine de ton repo (généré par exemple avec le
générateur Docker que tu utilises en parallèle).

**Secrets GitHub requis** (Settings → Secrets and variables → Actions) :
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (token d'accès, pas ton mot de passe — à générer
  depuis les paramètres de sécurité de ton compte Docker Hub)

### Serveur SSH

Envoie les fichiers du repo sur un serveur distant via `rsync`, puis
redémarre un service `systemd`.

**Secrets GitHub requis** :
- `SSH_HOST` (IP ou nom d'hôte du serveur)
- `SSH_USER` (utilisateur SSH)
- `SSH_PRIVATE_KEY` (clé privée SSH, format PEM)

Champs à renseigner : chemin de déploiement distant, nom du service
`systemd` à redémarrer.

> **Note** : cette approche est volontairement simple (rsync brut).
> Pour un provisioning plus complet (installer des paquets, configurer
> Nginx, pare-feu, fail2ban...), le futur **module Ansible** d'OpsForge
> prendra le relais — voir la Roadmap.

### Vercel

Déploiement direct via l'action officielle Vercel. Indépendant du
langage (Vercel détecte et build lui-même la plupart des projets).

**Secrets requis** : `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
(à récupérer dans les paramètres de ton projet Vercel).

### AWS S3

Build le site puis synchronise le résultat vers un bucket S3 (hébergement
de site statique). Nécessite une stack Node, comme GitHub Pages.

**Secrets requis** : `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

Champs à renseigner : nom du bucket, région AWS (`us-east-1` par défaut).

---

## Matrix builds

Le job `test` peut tourner sur **plusieurs versions du langage en
parallèle** (ex : Python 3.10, 3.11 et 3.12 en même temps), pour
vérifier la compatibilité de ton code sur plusieurs versions. Coche
"Matrix build" et indique les versions séparées par une virgule.

Ça génère une vraie section `strategy.matrix` (GitHub) ou
`parallel.matrix` (GitLab) — le job tourne réellement N fois en
parallèle, pas juste une fois avec un avertissement.

Seul le job `test` supporte le matrix build (lint/build tournent sur
une seule version, ça suffit dans la grande majorité des cas).

---

## Déclenchement planifié (cron)

Ajoute un déclenchement automatique à intervalle régulier (ex : tous
les jours à 3h du matin), en plus du push/PR habituel. Format cron
standard (`0 3 * * *`).

Sur **GitHub Actions**, ça s'ajoute directement dans le fichier généré.
Sur **GitLab CI**, ce n'est pas possible en pur YAML — une note est
ajoutée en tête de fichier expliquant comment configurer le planning
manuellement (Settings → CI/CD → Schedules).

---

## Badge de statut (Markdown)

Renseigne ton dépôt (`utilisateur/repo` pour GitHub,
`namespace/projet` pour GitLab) pour obtenir un snippet Markdown à
coller dans ton `README.md`, affichant le statut du dernier pipeline :

```markdown
[![CI](https://github.com/octocat/hello-world/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/octocat/hello-world/actions/workflows/ci.yml)
```

---

## Tests

Une suite de tests automatisés (`pytest`) couvre la détection de
stack et l'assemblage des workflows.

```bash
pip install -r requirements-dev.txt --break-system-packages
pytest tests/ -v
```

Ce qui est couvert :
- Détection de chaque langage (Python, Node, Go, Rust, Java, PHP) et
  de leurs versions/package managers respectifs
- Détection de plusieurs stacks dans un même projet
- Génération de jobs uniquement pour les jobs demandés
- Dépendances entre jobs (`needs:`) — build attend test, deploy attend build
- Cas limite : cible de déploiement incompatible (github_pages sans
  stack Node) ignorée proprement
- Non-régression sur la syntaxe `${{ secrets.XXX }}` (le passage de
  `.format()` à `.replace()` ne doit jamais la casser)
- Fallback gracieux sur un package manager inconnu

---

## Architecture du projet

```
opsforge/
├── README.md              → ce fichier
├── main.py                → point d'entrée CLI
├── app.py                 → point d'entrée interface web (Flask)
├── requirements.txt       → dépendances Python
├── requirements-dev.txt   → dépendances de développement (pytest)
│
├── tests/
│   ├── test_detector.py          → tests de la détection de stack
│   ├── test_core.py              → tests de l'assemblage GitHub Actions
│   ├── test_gitlab_core.py       → tests de l'assemblage GitLab CI
│   └── test_advanced_features.py → matrix, cron, Vercel/S3, badges
│
├── generator/
│   ├── __init__.py
│   ├── detector.py        → détection auto du stack dans un dossier
│   ├── core.py            → assemblage des templates en un workflow complet (GitHub)
│   ├── gitlab_core.py      → assemblage du pipeline GitLab CI
│   └── config.py          → (réservé, vide pour l'instant)
│
├── templates/             → templates YAML bruts, un dossier par langage
│   ├── python/{lint,test,build}.yml
│   ├── node/{lint,test,build}.yml
│   ├── go/{lint,test,build}.yml
│   ├── rust/{lint,test,build}.yml
│   ├── java/{lint,test,build}.yml
│   ├── php/{lint,test,build}.yml
│   ├── deploy/{github_pages,docker_hub,ssh,vercel,aws_s3}.yml
│   ├── provisioning/       → templates Ansible (futur module, pas encore branchés)
│   └── deployment/         → templates Ansible de déploiement (idem)
│
├── web/                   → interface web (utilisée uniquement par app.py)
│   ├── templates/index.html
│   └── static/{style.css, script.js}
│
└── output/                → fichiers .yml générés par défaut (CLI)
```

> **Note sur les deux dossiers `templates/`** : celui à la racine
> contient les templates **YAML** (le cœur du générateur). Celui dans
> `web/templates/` contient le **HTML** de l'interface (convention
> Flask). Ce sont deux choses différentes malgré le nom identique —
> `app.py` pointe explicitement vers `web/templates` pour éviter toute
> confusion entre les deux.

---

## Comment ça marche en détail

### 1. Détection (`generator/detector.py`)

Pour chaque langage, on cherche des "fichiers signature" à la racine
du dossier (ex : `package.json` pour Node). Si trouvé :
- le **package manager** est déduit des fichiers de lock présents
  (`yarn.lock` → yarn, `package-lock.json` → npm, etc.)
- la **version** est déduite via différentes sources selon le langage :

| Langage | Sources de version (par ordre de priorité) |
|---|---|
| Python | `.python-version`, champ `python` dans `pyproject.toml` |
| Node.js | `engines.node` dans `package.json`, `.nvmrc` |
| Go | directive `go X.Y` dans `go.mod`, `.go-version` |
| Rust | `rust-toolchain.toml` (champ `channel`), `rust-toolchain` |
| Java | `.java-version`, `maven.compiler.release`/`source` dans `pom.xml`, `sourceCompatibility` dans `build.gradle` |
| PHP | `.php-version`, contrainte `require.php` dans `composer.json` |

Si aucune source n'est trouvée, une valeur par défaut raisonnable est
utilisée (ex : Python 3.12, Node 20, Go 1.22...).

Un projet peut avoir **plusieurs stacks détectées** en même temps
(ex : backend Python + frontend Node dans le même repo).

### 2. Templates (`templates/{langage}/{job}.yml`)

Chaque fichier est un **fragment YAML** représentant les `steps`
complets d'un job GitHub Actions (checkout, setup de l'environnement,
installation des dépendances, puis la commande spécifique au job).
Ils contiennent des **placeholders** `{version}`, `{install_cmd}`,
`{cache_key}` remplis dynamiquement.

### 3. Assemblage (`generator/core.py`)

Pour chaque stack détectée/choisie et chaque job demandé :
1. charge le template correspondant
2. remplace les placeholders avec les vraies valeurs (version détectée,
   commande d'installation adaptée au package manager...)
3. l'enveloppe dans un bloc `job:` avec un nom unique
   (ex : `test-python`, `lint-node`)

Tous les blocs sont ensuite concaténés sous une seule section `jobs:`,
précédée d'une section `on:` générée à partir des branches/déclencheurs
choisis. Le résultat est un YAML **validé avec `pyyaml`** avant d'être
retourné.

### 4. Utilisation (`main.py` / `app.py`)

- `main.py` orchestre tout ça en ligne de commande et écrit le fichier
  final sur disque.
- `app.py` expose la même logique via 3 routes Flask :
  - `GET /` → sert la page HTML
  - `POST /api/detect` → appelle `detect_stack()`, retourne du JSON
  - `POST /api/generate` → appelle `generate_workflow()`, retourne le
    YAML en JSON

Le JavaScript (`web/static/script.js`) appelle ces routes en `fetch()`
et met à jour la page sans rechargement.

---

## Ajouter un nouveau langage

1. Crée un dossier `templates/{langage}/` avec 3 fichiers :
   `lint.yml`, `test.yml`, `build.yml`
2. Dans `generator/core.py`, ajoute une entrée dans :
   - `INSTALL_COMMANDS` (commande d'installation par package manager)
   - `DEFAULT_VERSIONS` (version par défaut)
   - `AVAILABLE_JOBS` (jobs disponibles pour ce langage)
3. (Optionnel) Dans `generator/detector.py`, ajoute une entrée dans
   `SIGNATURES` pour permettre la détection automatique.
4. Dans `web/static/script.js`, ajoute le langage à
   `SUPPORTED_LANGUAGES` pour qu'il apparaisse dans la sélection
   manuelle de l'interface web.

---

## Limitations connues

- GitHub Pages ne fonctionne qu'avec une stack Node (pas de support
  pour des générateurs de site statique Python comme MkDocs, par
  exemple).
- Le déploiement SSH est volontairement simple (rsync brut, pas de
  gestion fine des permissions ou de rollback en cas d'échec).
- Pas de gestion de secrets Docker Hub/SSH autre que les secrets
  GitHub standards (pas d'intégration avec un vault externe).

---

## Roadmap

- [x] Mode déploiement (GitHub Pages, Docker Hub, SSH, Vercel, AWS S3)
- [x] Détection fine des versions pour Go/Rust/Java/PHP
- [x] Dépendances entre jobs (`needs:`) pour un vrai pipeline séquentiel
- [x] Support GitLab CI
- [x] Matrix builds (tester plusieurs versions en parallèle)
- [x] Déclenchement planifié (cron)
- [x] Badges de statut Markdown pour le README
- [ ] **Module Ansible** : génération de playbooks de provisioning/déploiement
      serveur (les templates YAML existent déjà dans `templates/provisioning/`
      et `templates/deployment/`, il reste à écrire le moteur `generator/ansible_core.py`,
      la CLI et l'onglet dans l'interface web)
- [ ] Déploiement GitHub/GitLab Pages pour d'autres langages (MkDocs, Hugo...)
- [ ] Rollback automatique en cas d'échec du déploiement SSH
- [ ] Kubernetes / Helm comme cible de déploiement supplémentaire

---

## Changelog

### Fusion — naissance d'OpsForge

Les deux dossiers `ci-cd-generator/` et `ansible-generator/` étaient
deux copies divergées du même projet, source de confusion permanente.
Ils sont désormais **fusionnés sous le nom OpsForge** : le code retenu
est la version la plus avancée (matrix builds, Vercel/AWS S3, cron,
badges), et les templates Ansible sont conservés dans
`templates/provisioning/` et `templates/deployment/` en attendant leur
moteur de génération (voir Roadmap).

Au passage : la clé `on:` des workflows GitHub Actions est maintenant
générée entre guillemets (`"on":`) — YAML 1.1 interprète le mot nu
comme un booléen, ce qui cassait le parsing PyYAML.

### Ajout — matrix builds, cron, Vercel/AWS S3, badges Markdown

**Nouveau — matrix builds** : le job `test` peut maintenant tourner
sur plusieurs versions du langage en parallèle (ex : Python 3.10, 3.11
et 3.12 en même temps). Génère une vraie `strategy.matrix` (GitHub) ou
`parallel.matrix` (GitLab) — pas juste des jobs dupliqués à la main.

**Nouveau — déclenchement planifié (cron)** : ajoute un `schedule:`
au pipeline GitHub Actions. Sur GitLab, comme ce n'est pas possible en
pur YAML, une note explicative est ajoutée en tête de fichier avec les
instructions pour le configurer via l'interface.

**Nouveau — 2 cibles de déploiement** :
- **Vercel** — déploiement direct via token (indépendant du langage)
- **AWS S3** — build + sync vers un bucket S3 (nécessite une stack
  Node, comme GitHub Pages)

**Nouveau — badges Markdown** : génère un snippet `[![CI](...)](...)`
à coller dans ton README, pour afficher le statut du pipeline
(GitHub Actions ou GitLab CI selon le provider choisi).

**Nouveau** : `tests/test_advanced_features.py` (17 cas, tous validés)
couvrant toutes ces fonctionnalités sur les deux providers.

### Correctif — mauvaise interprétation du style CasaOS (fond violet trop présent)

**Erreur** : j'avais mis en place un fond "wallpaper" dégradé bleu/violet
vif sur toute la page, en pensant que c'était l'esthétique CasaOS.
Après vérification (captures d'écran réelles), ce n'est pas ça : le
fond CasaOS est en réalité **clair et neutre** — c'est la **diversité
des couleurs des icônes d'applications** (chaque appli a sa propre
couleur) qui donne le côté "coloré", pas un dégradé géant en arrière-plan.

**Correctif** :
- Fond repassé en gris clair neutre (`#EEF1F7`), sans dégradé ni
  animation
- Cartes repassées en blanc solide (l'effet de flou n'avait plus de
  sens sur un fond uni)
- Texte du header repassé en sombre (il était en blanc, pensé pour
  contraster avec le fond violet)
- **Nouveau** : les badges numérotés (01 à 05) ont chacun leur propre
  couleur (bleu, violet, vert, orange, rose) au lieu d'un dégradé
  bleu-violet uniforme partout — c'est ça qui apporte le côté "coloré,
  diversifié" façon icônes d'applications CasaOS
- Mode sombre ajusté en conséquence (fond `#14151F` neutre, cartes
  sombres solides)

### Ajout — couleurs affinées, mode sombre, bouton d'installation natif

**Correctif couleurs** : le fond mélangeait bleu/violet/vert/orange
dans les coins, ce qui faisait "fouillis" et ne collait pas à
l'identité utilisée ailleurs (boutons, logo, badges = bleu→violet
uniquement). Remplacé par un vrai dégradé **aurora** cohérent
(bleu → violet → magenta), avec une légère animation de dérive lente
(désactivée automatiquement si `prefers-reduced-motion`).

**Nouveau — mode sombre** : bouton 🌙/☀️ en haut à droite. Respecte la
préférence système (`prefers-color-scheme`) au premier chargement,
puis mémorise ton choix manuel. Le fond sombre utilise sa propre
palette aurora (violet/indigo profonds) plutôt qu'un simple
assombrissement du thème clair.

**Nouveau — bouton d'installation natif** : un bouton "📲 Installer
l'app" apparaît automatiquement (via l'évènement `beforeinstallprompt`)
quand le navigateur détecte que l'app est installable, en plus de
l'icône native du navigateur.

### Correctif — fond trop pâle, pas assez "CasaOS"

**Problème** : le fond clair (`#F0F2F7`) avec juste de légers dégradés
radiaux en overlay finissait par paraître presque blanc à l'usage —
pas du tout l'effet "wallpaper coloré + cartes en verre dépoli" propre
à CasaOS.

**Correctif** :
- Le fond de la page est maintenant un vrai **wallpaper dégradé
  vif** (bleu → violet, avec des touches vertes et orange en coins),
  couvrant tout le viewport
- Les cartes (panneaux, dock du bas) sont passées en **glassmorphism**
  réel : fond blanc semi-transparent + `backdrop-filter: blur()`, pour
  laisser transparaître le fond coloré flouté derrière, au lieu d'un
  blanc opaque
- Le texte du header (titre, sous-titre, badge) est repassé en blanc
  avec une légère ombre portée, pour rester lisible sur le fond coloré
  (il était sombre, pensé pour l'ancien fond clair)

### Ajout — PWA (installable) + améliorations diverses

**Nouveau — Progressive Web App** : l'interface web est maintenant
**installable** comme une vraie application (bouton "Installer" dans
Chrome/Edge, "Ajouter à l'écran d'accueil" sur mobile) :
- `manifest.json` avec 13 tailles d'icônes générées automatiquement
  (16px à 512px, plus une version "maskable" pour Android)
- Service worker (`service-worker.js`) avec mise en cache des assets
  statiques — fonctionne partiellement hors-ligne (l'interface se
  charge, mais générer un pipeline nécessite toujours le serveur local
  puisque les appels `/api/*` ne sont jamais mis en cache)
- Favicon, meta tags Apple (`apple-touch-icon`, statut de la barre iOS)
- Toutes les icônes sont dessinées par script (dégradé + logo), pas
  besoin d'outil de conversion SVG externe

**Nouveau — bouton "Réinitialiser"** : remet le formulaire à zéro
(chemin, branches, champs de déploiement, jobs, provider) en un clic.

**Nouveau — mémorisation des réglages** : les branches, le nom de
l'image Docker, le chemin de déploiement, etc. sont sauvegardés dans
le `localStorage` du navigateur après chaque génération réussie, et
restaurés à la prochaine visite. Comme cette appli tourne 100% en
local sur ta machine, `localStorage` est parfaitement approprié ici.

**Nouveau — micro-animation de succès** : le bouton "GÉNÉRER" affiche
brièvement "✓ GÉNÉRÉ !" en vert après une génération réussie.

### Refonte visuelle — thème inspiré de CasaOS (clair, cartes, dégradés)

**Changement majeur** : bascule complète du thème "plan technique"
(sombre, bleu marine/cyan) vers un thème inspiré de **CasaOS** — fond
clair, cartes blanches arrondies avec ombres douces, dégradés
bleu/violet, boutons en pilule, badges numérotés en dégradé devant
chaque section.

**Détail des changements** :
- Fond clair (`#F0F2F7`) avec dégradés radiaux doux en arrière-plan
  (au lieu du fond quadrillé sombre)
- Cartes blanches avec coins très arrondis (24px) et ombres portées
  douces plutôt que des contours nets
- Police de titre passée de Fraunces (serif) à **Poppins** (sans-serif
  géométrique, plus proche de l'esthétique CasaOS)
- Jobs/déploiement transformés en **chips** sélectionnables (pilules
  avec surbrillance dégradée quand cochées) plutôt que des checkboxes
  brutes dans un encadré
- Bouton "GÉNÉRER" en pilule pleine largeur, dégradé bleu→violet
- Cartouche transformée en **dock flottant** centré en bas de page
  (au lieu d'une barre pleine largeur collée en bas)
- Le panneau de résultat (YAML généré) reste volontairement sombre
  façon éditeur de code — contraste voulu façon "widget terminal"
  dans un dashboard clair, très courant dans ce type d'interface
- Logo recoloré en blanc sur fond dégradé (au lieu de cyan sur navy)

### Ajout — support GitLab CI (deuxième provider)

**Nouveau** : `generator/gitlab_core.py` génère maintenant des
fichiers `.gitlab-ci.yml` complets, avec les mêmes fonctionnalités que
GitHub Actions (lint/test/build, déploiement GitLab Pages/Docker
Hub/SSH). Un sélecteur en haut du formulaire web permet de basculer
entre les deux providers. Voir la section "GitLab CI — spécificités"
plus haut pour le détail des différences.

**Nouveau** : `tests/test_gitlab_core.py` (10 cas, tous validés).

**Changement d'architecture** : contrairement à GitHub Actions
(templates YAML externes par langage/job dans `templates/`), GitLab CI
utilise des commandes définies directement en Python dans
`gitlab_core.py` — la structure des jobs GitLab (juste `image` +
`script`) est assez simple pour ne pas justifier des fichiers de
template séparés.

### Ajout — suite de tests automatisés (pytest)

**Nouveau** : `tests/test_detector.py` et `tests/test_core.py`
couvrent la détection de stack et l'assemblage des workflows (14 cas
de test, tous validés). Voir la section "Tests" plus haut pour les
lancer.

### Refonte visuelle — logo, profondeur, animations, coloration syntaxique

**Nouveau** : un logo SVG dédié (`web/static/logo.svg`) — une ligne de
progression ascendante qui se termine par un check, animée d'un léger
flottement dans le header.

**Amélioré** :
- Fond avec dégradés radiaux subtils (au lieu d'un aplat uni)
- Panneaux avec vraie profondeur (ombres, dégradé interne, effet de
  survol)
- Bouton "GÉNÉRER" en dégradé plein avec lueur cuivrée et effet de
  levée au survol (au lieu d'un simple contour)
- Schéma de pipeline : les connecteurs "coulent" (animation) entre
  deux étapes actives, au lieu d'un simple changement d'opacité statique
- **Coloration syntaxique du YAML** dans le résultat généré (clés en
  cyan, chaînes en cuivre, commentaires en italique) — beaucoup plus
  lisible qu'un bloc de texte monochrome
- Rayons de bordure harmonisés, effets de survol ajoutés sur les
  cases à cocher et les stacks détectées

### Ajout — déploiement (GitHub Pages, Docker Hub, SSH) + dépendances entre jobs

**Nouveau** : le générateur peut maintenant produire des jobs de
déploiement en plus de lint/test/build. Trois cibles disponibles :
GitHub Pages, Docker Hub, et un serveur distant via SSH. Voir la
section "Déploiement" plus haut pour le détail des secrets GitHub à
configurer pour chacune.

**Nouveau** : les jobs ont maintenant de vraies dépendances entre eux
(`needs:`) — `build` attend que `test` réussisse (si les deux sont
sélectionnés pour la même stack), et chaque job de déploiement attend
que le dernier job de build (ou de test) réussisse. Avant, tous les
jobs tournaient en parallèle sans lien logique entre eux.

**Changement technique interne** : le remplacement des placeholders
dans les templates est passé de `.format()` à un `.replace()` ciblé,
pour pouvoir coexister avec la syntaxe `${{ secrets.XXX }}` de GitHub
Actions (qui utilise aussi des accolades, et que `.format()` aurait
cassée).

### Correctif — bouton "GÉNÉRER" affiché de travers

**Bug** : le bouton "GÉNÉRER" avait une légère rotation (-1deg, effet
"tampon encreur" voulu au départ), ce qui le faisait apparaître décalé/
crooked par rapport au reste de l'interface — donnant l'impression
d'un bug d'affichage plutôt que d'un choix de style.

**Correctif** : rotation retirée, le bouton est maintenant bien droit
et aligné avec le reste des éléments.

### Correctif — résultat "fantôme" après une génération invalide

**Bug** : si tu générais un pipeline avec succès, puis décochais tous
les stacks/jobs et cliquais à nouveau sur "GÉNÉRER", le message
d'erreur s'affichait bien mais l'**ancien résultat restait affiché**
dans le panneau de droite. Ça donnait l'impression que le bouton
ignorait tes changements de sélection.

**Correctif** : le panneau de résultat est maintenant réinitialisé
avec un message explicite ("rien n'a été généré...") à chaque fois que
la génération échoue (validation, erreur serveur, ou serveur
inaccessible). Le message d'erreur est aussi mis en valeur avec un
encadré, pour être plus visible qu'avant.
