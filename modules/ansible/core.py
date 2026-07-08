"""
core.py
-------
Assemble un projet Ansible complet a partir des options choisies :
- etapes de provisioning (mise a jour systeme, Docker, Nginx, runtime...)
- etapes de deploiement (clone git, install deps, build, restart service...)

Deux modes de sortie :
- "flat"  : un seul playbook.yml (+ vars.yml, vault.yml, inventory.ini)
- "roles" : un projet organise en roles Ansible (un role par etape),
            ce qui est la structure recommandee par les bonnes pratiques
            Ansible des que le projet grandit un peu.

Usage basique :
    from generator.core import generate_playbook, generate_inventory

    config = {
        "hosts_group": "webservers",
        "provisioning": ["update_system", "base_packages", "docker", "nginx", "runtime"],
        "runtime_language": "node",
        "runtime_version": "20",
        "deployment": ["git_clone", "install_deps", "build", "restart_service", "reload_nginx"],
        "deployment_language": "node",
        "repo_url": "git@github.com:moi/mon-projet.git",
        "branch": "main",
        "app_dir": "/opt/mon-projet",
        "service_name": "mon-projet",
        "build_cmd": "npm run build",
    }
    yaml_text = generate_playbook(config)               # mode flat
    files = generate_role_based_project(config)         # mode roles
"""

import os

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# --------------------------------------------------------------------------
# Etapes de provisioning disponibles, dans l'ordre logique d'execution.
# "runtime" est un cas special : le fichier depend de la langue choisie.
# --------------------------------------------------------------------------
PROVISIONING_STEPS = [
    "update_system",
    "base_packages",
    "firewall",
    "ssh_hardening",
    "fail2ban",
    "monitoring",
    "docker",
    "nginx",
    "https",
    "database",
    "runtime",
]

DATABASE_ENGINES = ["postgresql", "mysql", "redis"]

# Etapes de deploiement disponibles, dans l'ordre logique d'execution.
# "install_deps" est un cas special : le fichier depend de la langue choisie.
DEPLOYMENT_STEPS = [
    "backup_previous",
    "git_clone",
    "zero_downtime_deploy",
    "install_deps",
    "build",
    "restart_service",
    "reload_nginx",
    "health_check",
    "notify",
]

SUPPORTED_LANGUAGES = ["python", "node", "go", "rust", "java", "php"]

# Valeurs par defaut utilisees si non fournies dans la config
DEFAULT_VERSIONS = {
    "python": "3.12",
    "node": "20",
    "go": "1.22.0",
    "rust": "stable",
    "java": "17",
    "php": "8.3",
}

DEFAULTS = {
    "hosts_group": "webservers",
    "app_dir": "/opt/mon-application",
    "branch": "main",
    "service_name": "mon-application",
}

# Description courte de chaque etape, utilisee dans les meta/main.yml
# des roles generes (mode "roles").
ROLE_DESCRIPTIONS = {
    "update_system": "Met a jour le systeme (apt/dnf update + upgrade).",
    "base_packages": "Installe les paquets de base (git, curl, unzip, outils de compilation).",
    "docker": "Installe Docker Engine et Docker Compose.",
    "nginx": "Installe et demarre Nginx.",
    "runtime": "Installe le runtime applicatif choisi (langage de l'appli).",
    "https": "Installe Certbot et obtient un certificat Let's Encrypt pour Nginx.",
    "database": "Installe et configure le moteur de base de donnees choisi.",
    "firewall": "Configure le pare-feu (UFW ou firewalld) : ouvre uniquement SSH, HTTP, HTTPS et le port applicatif.",
    "ssh_hardening": "Durcit la configuration SSH (desactive le login root et l'authentification par mot de passe).",
    "fail2ban": "Installe et configure Fail2ban pour bannir les IP apres des tentatives de connexion SSH echouees.",
    "monitoring": "Installe l'agent de supervision Netdata (tableau de bord temps reel des ressources serveur).",
    "git_clone": "Clone ou met a jour le depot Git de l'application.",
    "install_deps": "Installe les dependances du projet applicatif.",
    "build": "Execute la commande de build du projet.",
    "restart_service": "Redemarre le service applicatif (systemd).",
    "reload_nginx": "Recharge la configuration Nginx.",
    "backup_previous": "Sauvegarde la version precedente de l'appli avant le nouveau deploiement (rollback).",
    "health_check": "Verifie que le service applicatif repond bien apres le deploiement.",
    "zero_downtime_deploy": "Deploie dans un nouveau dossier horodate puis bascule un lien symbolique (sans interruption de service).",
    "notify": "Envoie une notification Slack/Discord a la fin du deploiement.",
}


def _load_template(relative_path):
    """Charge le contenu brut d'un template .yml, ou None si absent."""
    path = os.path.join(TEMPLATES_DIR, relative_path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _role_name_for_step(kind, step, config):
    """
    Nom du dossier de role a utiliser pour une etape donnee.

    Les etapes "runtime" et "install_deps" dependent du langage choisi ;
    on suffixe leur nom de role avec le langage (ex: "runtime_python",
    "install_deps_node") pour eviter toute collision quand plusieurs
    groupes de serveurs utilisent des langages differents (mode multi-serveurs).
    """
    if kind == "provisioning" and step == "runtime":
        language = config.get("runtime_language") or "inconnu"
        return f"runtime_{language}"
    if kind == "provisioning" and step == "database":
        engine = config.get("database_engine") or "inconnu"
        return f"database_{engine}"
    if kind == "deployment" and step == "install_deps":
        language = config.get("deployment_language") or "inconnu"
        return f"install_deps_{language}"
    return step


def _selected_steps(config):
    """
    Retourne deux listes ordonnees : (etapes_provisioning, etapes_deploiement)
    selon ce qui a ete coche dans la config, en respectant l'ordre logique
    d'execution defini par PROVISIONING_STEPS / DEPLOYMENT_STEPS.
    """
    provisioning_selected = config.get("provisioning", [])
    deployment_selected = config.get("deployment", [])

    provisioning = [s for s in PROVISIONING_STEPS if s in provisioning_selected]
    deployment = [s for s in DEPLOYMENT_STEPS if s in deployment_selected]
    return provisioning, deployment


def _step_template_content(kind, step, config):
    """
    Charge le contenu brut du template Ansible correspondant a une etape.
    Gere les deux cas speciaux ("runtime" et "install_deps") dont le fichier
    depend du langage choisi.

    Args:
        kind (str): "provisioning" ou "deployment"
        step (str): nom de l'etape (ex: "docker", "runtime", "git_clone")
        config (dict): configuration complete

    Returns:
        str|None: contenu brut du template, ou None si non applicable
    """
    if kind == "provisioning" and step == "runtime":
        language = config.get("runtime_language")
        if not language:
            return None
        return _load_template(f"provisioning/runtime/{language}.yml")

    if kind == "provisioning" and step == "database":
        engine = config.get("database_engine")
        if not engine:
            return None
        return _load_template(f"provisioning/database/{engine}.yml")

    if kind == "deployment" and step == "install_deps":
        language = config.get("deployment_language")
        if not language:
            return None
        return _load_template(f"deployment/install_deps/{language}.yml")

    prefix = "provisioning" if kind == "provisioning" else "deployment"
    return _load_template(f"{prefix}/{step}.yml")


def _shift_indent(content, spaces):
    """Ajoute 'spaces' espaces au debut de chaque ligne non vide."""
    pad = " " * spaces
    lines = content.rstrip("\n").split("\n")
    return "\n".join((pad + line if line.strip() else line) for line in lines) + "\n"


def _tags_for_step(kind, step, config):
    """
    Liste des tags Ansible a associer a une etape, pour permettre de
    rejouer une partie du playbook avec `--tags <nom>` sans tout refaire.

    Inclut le nom generique de l'etape (ex: "runtime") et, si different,
    le nom specifique au langage (ex: "runtime_python"), pour pouvoir
    cibler l'un ou l'autre.
    """
    specific = _role_name_for_step(kind, step, config)
    tags = [step]
    if specific != step:
        tags.append(specific)
    return tags


def _wrap_block_with_tags(kind, step, content, config):
    """
    Enveloppe le contenu brut d'un template dans un bloc Ansible `block:`
    tagge, pour le mode "flat" (permet `ansible-playbook --tags <etape>`).
    """
    tags = _tags_for_step(kind, step, config)
    tags_yaml = ", ".join(f'"{t}"' for t in tags)
    shifted = _shift_indent(content, 4)
    return (
        f'    - name: "Étape : {step}"\n'
        f"      block:\n"
        f"{shifted}"
        f"      tags: [{tags_yaml}]\n"
    )


def _build_provisioning_tasks(config):
    """Construit la liste des blocs de taches de provisioning selectionnees (tagges)."""
    provisioning, _ = _selected_steps(config)
    blocks = []
    for step in provisioning:
        content = _step_template_content("provisioning", step, config)
        if content is not None:
            blocks.append(_wrap_block_with_tags("provisioning", step, content, config))
    return blocks


def _build_deployment_tasks(config):
    """Construit la liste des blocs de taches de deploiement selectionnees (tagges)."""
    _, deployment = _selected_steps(config)
    blocks = []
    for step in deployment:
        content = _step_template_content("deployment", step, config)
        if content is not None:
            blocks.append(_wrap_block_with_tags("deployment", step, content, config))
    return blocks


def _build_vars(config):
    """
    Construit le dictionnaire des variables globales (non secretes) utilisees
    par les templates : app_dir, branch, service_name, repo_url, build_cmd,
    runtime_version. Ces variables sont referencees en Jinja ({{ app_dir }},
    etc.) directement dans les templates de tache.
    """
    language = config.get("runtime_language") or config.get("deployment_language")
    default_version = DEFAULT_VERSIONS.get(language, "")

    return {
        "app_dir": config.get("app_dir") or DEFAULTS["app_dir"],
        "branch": config.get("branch") or DEFAULTS["branch"],
        "service_name": config.get("service_name") or DEFAULTS["service_name"],
        "repo_url": config.get("repo_url") or "",
        "build_cmd": config.get("build_cmd") or "echo 'Aucune commande de build definie'",
        "runtime_version": config.get("runtime_version") or default_version,
        "health_check_port": config.get("health_check_port") or "80",
        "domain_name": config.get("domain_name") or "example.com",
        "letsencrypt_email": config.get("letsencrypt_email") or "admin@example.com",
        "db_name": config.get("db_name") or "app_db",
        "db_user": config.get("db_user") or "app_user",
        "notify_webhook_url": config.get("notify_webhook_url") or "",
    }


def _vars_to_yaml_lines(vars_dict):
    """Serialise un dict de variables en lignes YAML simples 'cle: "valeur"'."""
    lines = []
    for key, value in vars_dict.items():
        safe_value = str(value).replace('"', '\\"')
        lines.append(f'{key}: "{safe_value}"')
    return lines


def generate_playbook(config):
    """
    Genere le contenu complet d'un playbook Ansible "flat" (toutes les taches
    dans un seul fichier) a partir de la config fournie.

    Args:
        config (dict): voir docstring du module pour un exemple complet.

    Returns:
        str: contenu YAML complet du playbook, pret a etre ecrit dans playbook.yml
    """
    provisioning_blocks = _build_provisioning_tasks(config)
    deployment_blocks = _build_deployment_tasks(config)

    all_blocks = provisioning_blocks + deployment_blocks

    if not all_blocks:
        raise ValueError(
            "Aucune tache generee : selectionne au moins une etape "
            "de provisioning ou de deploiement."
        )

    hosts_group = config.get("hosts_group") or DEFAULTS["hosts_group"]
    vars_dict = _build_vars(config)

    tasks_section = "\n\n".join(all_blocks)
    vars_lines = "\n".join(f"    {line}" for line in _vars_to_yaml_lines(vars_dict))

    vars_files_section = ""
    if config.get("vault_vars"):
        vars_files_section = "  vars_files:\n    - vault.yml\n\n"

    playbook = (
        "---\n"
        f"- name: Provisioning et deploiement\n"
        f"  hosts: {hosts_group}\n"
        f"  become: false\n"
        f"  vars:\n"
        f"{vars_lines}\n\n"
        f"{vars_files_section}"
        f"  tasks:\n"
        f"{tasks_section}\n"
    )

    return playbook


def _format_role_entry(role_name, tags):
    """Formatte une entree de la liste 'roles:' d'un playbook, avec ses tags."""
    tags_yaml = ", ".join(f'"{t}"' for t in tags)
    return f"    - role: {role_name}\n      tags: [{tags_yaml}]"


def generate_role_based_project(config):
    """
    Genere un projet Ansible organise en roles (un role independant par
    etape selectionnee), conformement aux bonnes pratiques Ansible.

    Args:
        config (dict): meme format que pour generate_playbook.

    Returns:
        dict: mapping {chemin_relatif: contenu} de tous les fichiers du
            projet, par exemple :
            {
                "playbook.yml": "...",
                "vars.yml": "...",
                "ansible.cfg": "...",
                "roles/docker/tasks/main.yml": "...",
                "roles/docker/meta/main.yml": "...",
                ...
            }

    Raises:
        ValueError: si aucune etape n'est selectionnee
    """
    provisioning, deployment = _selected_steps(config)
    all_steps = [("provisioning", s) for s in provisioning] + [
        ("deployment", s) for s in deployment
    ]

    files = {}
    role_entries = []

    for kind, step in all_steps:
        content = _step_template_content(kind, step, config)
        if content is None:
            continue

        role_name = _role_name_for_step(kind, step, config)
        role_entries.append(_format_role_entry(role_name, _tags_for_step(kind, step, config)))
        files[f"roles/{role_name}/tasks/main.yml"] = content
        files[f"roles/{role_name}/meta/main.yml"] = (
            "---\n"
            "galaxy_info:\n"
            f'  description: "{ROLE_DESCRIPTIONS.get(step, step)}"\n'
            '  min_ansible_version: "2.15"\n'
            "dependencies: []\n"
        )

    if not role_entries:
        raise ValueError(
            "Aucune tache generee : selectionne au moins une etape "
            "de provisioning ou de deploiement."
        )

    vars_dict = _build_vars(config)
    vars_lines = "\n".join(_vars_to_yaml_lines(vars_dict))
    files["vars.yml"] = "---\n" + vars_lines + "\n"

    hosts_group = config.get("hosts_group") or DEFAULTS["hosts_group"]

    vars_files_lines = ["    - vars.yml"]
    if config.get("vault_vars"):
        vars_files_lines.append("    - vault.yml")
    vars_files_section = "\n".join(vars_files_lines)

    roles_section = "\n".join(role_entries)

    files["playbook.yml"] = (
        "---\n"
        "- name: Provisioning et deploiement\n"
        f"  hosts: {hosts_group}\n"
        "  become: false\n"
        "  vars_files:\n"
        f"{vars_files_section}\n\n"
        "  roles:\n"
        f"{roles_section}\n"
    )

    files["ansible.cfg"] = (
        "[defaults]\n"
        "roles_path = ./roles\n"
        "inventory = ./inventory.ini\n"
        "host_key_checking = False\n"
        "stdout_callback = yaml\n"
    )

    return files


def generate_inventory(hosts_group, host, ssh_user="deploy", ssh_key_path=None):
    """
    Genere un fichier d'inventaire Ansible minimal (format INI).

    Args:
        hosts_group (str): nom du groupe (doit correspondre a celui du playbook)
        host (str): IP ou nom d'hote du serveur cible
        ssh_user (str): utilisateur SSH utilise pour se connecter
        ssh_key_path (str|None): chemin vers la cle privee SSH, optionnel

    Returns:
        str: contenu du fichier inventory.ini
    """
    line = f"{host} ansible_user={ssh_user}"
    if ssh_key_path:
        line += f" ansible_ssh_private_key_file={ssh_key_path}"

    return f"[{hosts_group}]\n{line}\n"


# ==============================================================================
# MODE MULTI-SERVEURS : plusieurs groupes d'hotes, chacun avec son propre
# provisioning/deploiement (ex : un groupe "web" + un groupe "db").
# ==============================================================================
def _normalize_group(group):
    """Applique les valeurs par defaut a un groupe de la config multi-serveurs."""
    normalized = dict(group)
    normalized.setdefault("hosts_group", DEFAULTS["hosts_group"])
    normalized.setdefault("provisioning", [])
    normalized.setdefault("deployment", [])
    normalized.setdefault("hosts", [])
    normalized.setdefault("ssh_user", "deploy")
    return normalized


def _validate_groups(groups):
    if not groups:
        raise ValueError("Aucun groupe fourni : au moins un groupe de serveurs est requis.")

    seen_names = set()
    for group in groups:
        name = group.get("hosts_group")
        if not name:
            raise ValueError("Chaque groupe doit avoir un 'hosts_group' (nom du groupe).")
        if name in seen_names:
            raise ValueError(f"Nom de groupe en double : '{name}'. Chaque groupe doit avoir un nom unique.")
        seen_names.add(name)

        provisioning, deployment = _selected_steps(group)
        if not provisioning and not deployment:
            raise ValueError(
                f"Le groupe '{name}' n'a aucune etape de provisioning ni de deploiement selectionnee."
            )


def generate_multi_group_playbook(groups, vault_vars=None):
    """
    Genere un playbook Ansible "flat" avec plusieurs plays, un par groupe
    de serveurs (mode multi-serveurs).

    Args:
        groups (list[dict]): liste de configs, une par groupe. Meme format
            que la config de generate_playbook, plus une cle "hosts_group"
            obligatoire (nom du groupe, doit correspondre a l'inventaire).
        vault_vars (dict|None): secrets partages entre tous les groupes

    Returns:
        str: contenu YAML complet du playbook multi-plays
    """
    groups = [_normalize_group(g) for g in groups]
    _validate_groups(groups)

    plays = []
    for group in groups:
        provisioning_blocks = _build_provisioning_tasks(group)
        deployment_blocks = _build_deployment_tasks(group)
        all_blocks = provisioning_blocks + deployment_blocks

        vars_dict = _build_vars(group)
        vars_lines = "\n".join(f"    {line}" for line in _vars_to_yaml_lines(vars_dict))
        tasks_section = "\n\n".join(all_blocks)

        vars_files_section = ""
        if vault_vars:
            vars_files_section = "  vars_files:\n    - vault.yml\n\n"

        plays.append(
            f"- name: \"Provisioning et deploiement — groupe {group['hosts_group']}\"\n"
            f"  hosts: {group['hosts_group']}\n"
            f"  become: false\n"
            f"  vars:\n"
            f"{vars_lines}\n\n"
            f"{vars_files_section}"
            f"  tasks:\n"
            f"{tasks_section}\n"
        )

    return "---\n" + "\n\n".join(plays) + "\n"


def generate_multi_group_roles_project(groups, vault_vars=None):
    """
    Genere un projet Ansible organise en roles pour plusieurs groupes de
    serveurs. Les roles identiques utilises par plusieurs groupes (ex :
    "update_system", "docker") ne sont generes qu'une seule fois et
    partages entre les plays.

    Args:
        groups (list[dict]): voir generate_multi_group_playbook
        vault_vars (dict|None): secrets partages entre tous les groupes

    Returns:
        dict: mapping {chemin_relatif: contenu}, avec un
            "playbook.yml" (multi-plays), un "vars_<groupe>.yml" par groupe,
            et un dossier "roles/" partage/dedupliques entre groupes.
    """
    groups = [_normalize_group(g) for g in groups]
    _validate_groups(groups)

    files = {}
    plays = []

    for group in groups:
        provisioning, deployment = _selected_steps(group)
        all_steps = [("provisioning", s) for s in provisioning] + [
            ("deployment", s) for s in deployment
        ]

        role_entries = []
        for kind, step in all_steps:
            content = _step_template_content(kind, step, group)
            if content is None:
                continue

            role_name = _role_name_for_step(kind, step, group)
            role_entries.append(_format_role_entry(role_name, _tags_for_step(kind, step, group)))

            # Dedup : si un role identique existe deja (meme nom => meme
            # contenu, car le nom inclut deja le langage pour runtime/install_deps),
            # on ne l'ecrit qu'une fois.
            role_key = f"roles/{role_name}/tasks/main.yml"
            if role_key not in files:
                files[role_key] = content
                files[f"roles/{role_name}/meta/main.yml"] = (
                    "---\n"
                    "galaxy_info:\n"
                    f'  description: "{ROLE_DESCRIPTIONS.get(step, step)}"\n'
                    '  min_ansible_version: "2.15"\n'
                    "dependencies: []\n"
                )

        vars_dict = _build_vars(group)
        vars_lines = "\n".join(_vars_to_yaml_lines(vars_dict))
        vars_filename = f"vars_{group['hosts_group']}.yml"
        files[vars_filename] = "---\n" + vars_lines + "\n"

        vars_files_lines = [f"    - {vars_filename}"]
        if vault_vars:
            vars_files_lines.append("    - vault.yml")
        vars_files_section = "\n".join(vars_files_lines)

        roles_section = "\n".join(role_entries)

        plays.append(
            f"- name: \"Provisioning et deploiement — groupe {group['hosts_group']}\"\n"
            f"  hosts: {group['hosts_group']}\n"
            "  become: false\n"
            "  vars_files:\n"
            f"{vars_files_section}\n\n"
            "  roles:\n"
            f"{roles_section}\n"
        )

    files["playbook.yml"] = "---\n" + "\n\n".join(plays) + "\n"

    files["ansible.cfg"] = (
        "[defaults]\n"
        "roles_path = ./roles\n"
        "inventory = ./inventory.ini\n"
        "host_key_checking = False\n"
        "stdout_callback = yaml\n"
    )

    return files


def generate_multi_group_inventory(groups):
    """
    Genere un inventory.ini avec une section par groupe de serveurs.

    Args:
        groups (list[dict]): chaque groupe doit avoir "hosts_group",
            "hosts" (liste d'IP/hostnames) et optionnellement "ssh_user".

    Returns:
        str: contenu complet du fichier inventory.ini
    """
    groups = [_normalize_group(g) for g in groups]
    sections = []
    for group in groups:
        lines = [f"[{group['hosts_group']}]"]
        ssh_user = group.get("ssh_user") or "deploy"
        for host in group.get("hosts", []):
            lines.append(f"{host} ansible_user={ssh_user}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"


def write_multi_group_project(groups, output_dir, vault_vars=None, vault_password=None):
    """
    Genere le projet multi-serveurs organise en roles et ecrit tous les
    fichiers dans output_dir.

    Returns:
        list[str]: chemins absolus de tous les fichiers ecrits
    """
    files = generate_multi_group_roles_project(groups, vault_vars=vault_vars)

    if vault_vars:
        files["vault.yml"] = generate_vault_file(vault_vars, vault_password)

    written = []
    for relative_path, content in files.items():
        full_path = os.path.join(output_dir, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(full_path)
    return written


def generate_vault_vars_yaml(secrets):
    """
    Construit le contenu YAML en clair a partir d'un dict de secrets.
    Ex: {"db_password": "hunter2"} -> 'db_password: "hunter2"\n'
    """
    if not secrets:
        return ""
    return "\n".join(_vars_to_yaml_lines(secrets)) + "\n"


def encrypt_vault_content(plaintext_yaml, vault_password):
    """
    Chiffre un contenu YAML en clair avec Ansible Vault (AES256), en utilisant
    le meme format que `ansible-vault encrypt`.

    Args:
        plaintext_yaml (str): contenu YAML non chiffre (ex: sortie de
            generate_vault_vars_yaml)
        vault_password (str): mot de passe du vault

    Returns:
        str: contenu chiffre, pret a etre ecrit dans un fichier vault.yml

    Raises:
        ImportError: si le paquet ansible-core n'est pas installe
        ValueError: si le mot de passe est vide
    """
    if not vault_password:
        raise ValueError("Un mot de passe de vault est requis pour chiffrer les secrets.")

    try:
        from ansible.parsing.vault import VaultLib, VaultSecret
        from ansible.constants import DEFAULT_VAULT_ID_MATCH
    except ImportError as e:
        raise ImportError(
            "Le paquet 'ansible-core' est requis pour chiffrer les secrets "
            "(pip install ansible-core --break-system-packages)."
        ) from e

    secret = VaultSecret(vault_password.encode("utf-8"))
    vault = VaultLib(secrets=[(DEFAULT_VAULT_ID_MATCH, secret)])
    encrypted = vault.encrypt(plaintext_yaml.encode("utf-8"))
    return encrypted.decode("utf-8")


def generate_vault_file(secrets, vault_password):
    """
    Genere le contenu chiffre d'un fichier vault.yml a partir d'un dict de
    secrets et d'un mot de passe.

    Args:
        secrets (dict): paires cle/valeur des secrets (ex: mots de passe,
            tokens d'API) a stocker dans le vault
        vault_password (str): mot de passe utilise pour chiffrer le fichier

    Returns:
        str: contenu chiffre du fichier vault.yml
    """
    plaintext_yaml = generate_vault_vars_yaml(secrets)
    return encrypt_vault_content(plaintext_yaml, vault_password)


def write_vault_file(secrets, vault_password, output_path):
    """Genere le vault.yml chiffre et l'ecrit directement dans un fichier."""
    content = generate_vault_file(secrets, vault_password)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def write_playbook(config, output_path):
    """Genere le playbook (mode flat) et l'ecrit directement dans un fichier."""
    content = generate_playbook(config)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def write_role_based_project(config, output_dir):
    """
    Genere le projet organise en roles et ecrit tous les fichiers dans
    output_dir (arborescence complete : playbook.yml, vars.yml, ansible.cfg,
    roles/<etape>/tasks/main.yml, roles/<etape>/meta/main.yml).

    Returns:
        list[str]: chemins absolus de tous les fichiers ecrits
    """
    files = generate_role_based_project(config)
    written = []
    for relative_path, content in files.items():
        full_path = os.path.join(output_dir, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(full_path)
    return written
