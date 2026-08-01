"""
core.py
-------
Generation de configuration d'authentification en frontal d'une application
web deja servie par un reverse proxy (le module nginx s'occupe du proxy en
lui-meme ; celui-ci s'occupe de savoir QUI a le droit d'y entrer). Comble un
trou courant du homelab/self-hosting : une appli exposee via Nginx/Traefik
sans aucune barriere d'authentification devant.

Deux moteurs :

  - "oauth2-proxy" : delegue l'authentification a un fournisseur externe
                     (GitHub, Google, OIDC generique). Leger, un seul
                     fichier de config + un snippet Nginx (auth_request).
                     Ideal pour une appli, restreinte a une organisation
                     GitHub ou un domaine Google.
  - "authelia"      : portail d'authentification autonome (utilisateurs
                       locaux, MFA TOTP, regles d'acces PAR DOMAINE avec
                       plusieurs niveaux de politique). Plus lourd a
                       deployer, mais gere plusieurs applications et
                       plusieurs utilisateurs sans dependre d'un tiers.

Deux secrets locaux (cookie/session) sont generes aleatoirement a la volee :
contrairement a une cle privee SSH ou un jeton OAuth (lies a une identite
externe, donc impossibles a deviner correctement), un secret de session n'a
pas de "bonne" valeur a part "aleatoire et unique" — le generer directement
rend la config utilisable sans etape manuelle supplementaire.

Usage basique :
    from modules.authproxy.core import generate_authproxy

    config = {"preset": "github-org", "engine": "oauth2-proxy"}
    files = generate_authproxy(config)   # {"oauth2-proxy.cfg": "...", ...}
"""

import copy
import os
import re
import secrets

SUPPORTED_ENGINES = ["oauth2-proxy", "authelia"]

OAUTH2_PROXY_PROVIDERS = ["github", "google", "oidc", "gitlab"]
AUTHELIA_POLICIES = ["bypass", "one_factor", "two_factor", "deny"]
AUTHELIA_STORAGE_BACKENDS = ["sqlite", "postgres"]

DOMAIN_RE = re.compile(r"^(\*\.)?[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$", re.I)
USERNAME_RE = re.compile(r"^[a-z0-9._-]+$", re.I)


def _random_secret(length=32):
    """
    Secret local aleatoire (session/cookie), encode en base64 urlsafe.
    Jamais une identite externe : rien a placeholder-iser, la seule
    exigence est d'etre aleatoire et de la bonne longueur.
    """
    return secrets.token_urlsafe(length)


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------
PRESETS = {
    "github-org": {
        "label": "Restreint a une organisation GitHub (oauth2-proxy)",
        "engine": "oauth2-proxy",
        "config": {
            "provider": "github",
            "upstream": "http://127.0.0.1:8080",
            "cookie_domain": ".exemple.com",
            "redirect_url": "https://auth.exemple.com/oauth2/callback",
            "client_id": "REMPLACE_PAR_TON_CLIENT_ID_GITHUB",
            "client_secret": "REMPLACE_PAR_TON_CLIENT_SECRET_GITHUB",
            "github_org": "mon-organisation",
            "github_team": "",
        },
    },
    "google-domain": {
        "label": "Restreint a un domaine Google Workspace (oauth2-proxy)",
        "engine": "oauth2-proxy",
        "config": {
            "provider": "google",
            "upstream": "http://127.0.0.1:8080",
            "cookie_domain": ".exemple.com",
            "redirect_url": "https://auth.exemple.com/oauth2/callback",
            "client_id": "REMPLACE_PAR_TON_CLIENT_ID_GOOGLE.apps.googleusercontent.com",
            "client_secret": "REMPLACE_PAR_TON_CLIENT_SECRET_GOOGLE",
            "email_domains": ["exemple.com"],
        },
    },
    "generic-oidc": {
        "label": "Fournisseur OIDC generique (Keycloak, Authentik, Auth0…)",
        "engine": "oauth2-proxy",
        "config": {
            "provider": "oidc",
            "upstream": "http://127.0.0.1:8080",
            "cookie_domain": ".exemple.com",
            "redirect_url": "https://auth.exemple.com/oauth2/callback",
            "client_id": "REMPLACE_PAR_TON_CLIENT_ID",
            "client_secret": "REMPLACE_PAR_TON_CLIENT_SECRET",
            "oidc_issuer_url": "https://idp.exemple.com/realms/mon-realm",
            "email_domains": ["*"],
        },
    },
    "homelab-simple": {
        "label": "Homelab simple : un compte, un facteur (Authelia)",
        "engine": "authelia",
        "config": {
            "domain": "exemple.com",
            "storage_backend": "sqlite",
            "notifier": "filesystem",
            "users": [
                {"username": "admin", "display_name": "Admin", "groups": ["admins"]},
            ],
            "access_rules": [
                {"domain": "*.exemple.com", "policy": "one_factor"},
            ],
        },
    },
    "two-factor-sensitive": {
        "label": "Deux facteurs sur les routes sensibles (Authelia)",
        "engine": "authelia",
        "config": {
            "domain": "exemple.com",
            "storage_backend": "sqlite",
            "notifier": "filesystem",
            "users": [
                {"username": "admin", "display_name": "Admin", "groups": ["admins"]},
                {"username": "invite", "display_name": "Invite", "groups": ["invites"]},
            ],
            "access_rules": [
                {"domain": "admin.exemple.com", "policy": "two_factor", "subject": "group:admins"},
                {"domain": "*.exemple.com", "policy": "one_factor"},
            ],
        },
    },
    "multi-domain": {
        "label": "Politiques differenciees par sous-domaine (Authelia)",
        "engine": "authelia",
        "config": {
            "domain": "exemple.com",
            "storage_backend": "sqlite",
            "notifier": "filesystem",
            "users": [
                {"username": "admin", "display_name": "Admin", "groups": ["admins"]},
            ],
            "access_rules": [
                {"domain": "public.exemple.com", "policy": "bypass"},
                {"domain": "admin.exemple.com", "policy": "two_factor", "subject": "group:admins"},
                {"domain": "*.exemple.com", "policy": "one_factor"},
            ],
        },
    },
    "custom": {
        "label": "Personnalise (config fournie manuellement)",
        "engine": "oauth2-proxy",
        "config": {"provider": "oidc"},
    },
}


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def list_presets_by_engine(engine):
    """Liste les presets d'un moteur donne ('oauth2-proxy' ou 'authelia')."""
    return [name for name, p in PRESETS.items() if p["engine"] == engine]


def get_preset(name):
    """
    Retourne une config de depart prete a generer pour le preset donne
    (copie profonde : modifiable sans affecter PRESETS).
    """
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Disponibles : {', '.join(PRESETS)}."
        )
    preset_def = PRESETS[name]
    config = copy.deepcopy(preset_def["config"])
    config["preset"] = name
    config["engine"] = preset_def["engine"]
    return config


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _validate_oauth2_proxy(config, errors):
    provider = config.get("provider", "")
    if provider not in OAUTH2_PROXY_PROVIDERS:
        errors.append(
            f"Fournisseur non supporte : '{provider}'. "
            f"Disponibles : {', '.join(OAUTH2_PROXY_PROVIDERS)}."
        )

    if not (config.get("upstream") or "").strip():
        errors.append("Upstream manquant : l'adresse locale de l'appli a proteger (ex: http://127.0.0.1:8080).")

    if not (config.get("redirect_url") or "").strip():
        errors.append("URL de redirection manquante (ex: https://auth.tondomaine.com/oauth2/callback).")

    if not (config.get("client_id") or "").strip():
        errors.append("Client ID manquant (fourni par le fournisseur OAuth choisi).")
    if not (config.get("client_secret") or "").strip():
        errors.append("Client secret manquant (fourni par le fournisseur OAuth choisi).")

    if provider == "github":
        if not (config.get("github_org") or "").strip():
            errors.append("Organisation GitHub manquante (github_org) : sans elle, TOUT compte GitHub serait accepte.")
    elif provider == "google":
        if not config.get("email_domains"):
            errors.append("Aucun domaine email autorise (email_domains) : sans lui, aucun compte ne serait accepte.")
    elif provider == "oidc":
        if not (config.get("oidc_issuer_url") or "").strip():
            errors.append("URL de l'emetteur OIDC manquante (oidc_issuer_url).")
        if not config.get("email_domains"):
            errors.append("Aucun domaine email autorise (email_domains) : utilise ['*'] pour n'importe quel compte du fournisseur.")


def _validate_authelia(config, errors):
    domain = (config.get("domain") or "").strip()
    if not domain:
        errors.append("Domaine de base manquant (ex: exemple.com).")
    elif not DOMAIN_RE.match(domain):
        errors.append(f"Domaine invalide : '{domain}'.")

    storage = config.get("storage_backend", "sqlite")
    if storage not in AUTHELIA_STORAGE_BACKENDS:
        errors.append(
            f"Backend de stockage non supporte : '{storage}'. "
            f"Disponibles : {', '.join(AUTHELIA_STORAGE_BACKENDS)}."
        )

    users = config.get("users") or []
    if not users:
        errors.append("Aucun utilisateur defini : ajoute au moins un compte.")
    usernames = []
    for index, user in enumerate(users, start=1):
        label = f"Utilisateur #{index}"
        username = (user.get("username") or "").strip()
        if not username:
            errors.append(f"{label} : nom d'utilisateur manquant.")
        elif not USERNAME_RE.match(username):
            errors.append(f"{label} : nom d'utilisateur invalide ('{username}').")
        else:
            usernames.append(username)
        if not user.get("groups"):
            errors.append(f"{label} ('{username or '?'}') : aucun groupe — les regles d'acces par groupe ne pourraient pas s'appliquer.")

    duplicates = {u for u in usernames if usernames.count(u) > 1}
    for username in sorted(duplicates):
        errors.append(f"Utilisateur '{username}' defini plusieurs fois.")

    rules = config.get("access_rules") or []
    if not rules:
        errors.append("Aucune regle d'acces definie : ajoute au moins une regle (domaine + politique).")
    for index, rule in enumerate(rules, start=1):
        label = f"Regle d'acces #{index}"
        rule_domain = (rule.get("domain") or "").strip()
        if not rule_domain:
            errors.append(f"{label} : domaine manquant.")
        elif not DOMAIN_RE.match(rule_domain):
            errors.append(f"{label} : domaine invalide ('{rule_domain}').")

        policy = rule.get("policy", "")
        if policy not in AUTHELIA_POLICIES:
            errors.append(
                f"{label} : politique invalide ('{policy}'). "
                f"Disponibles : {', '.join(AUTHELIA_POLICIES)}."
            )

        subject = (rule.get("subject") or "").strip()
        if subject:
            kind, _, name = subject.partition(":")
            if kind not in ("user", "group") or not name:
                errors.append(
                    f"{label} : sujet invalide ('{subject}'). Format attendu : "
                    "'user:nom' ou 'group:nom'."
                )
            elif kind == "group" and not any(name in (u.get("groups") or []) for u in users):
                errors.append(f"{label} : le groupe '{name}' n'est attribue a aucun utilisateur defini.")
            elif kind == "user" and name not in usernames:
                errors.append(f"{label} : l'utilisateur '{name}' n'est pas defini plus haut.")

    if not any(r.get("policy") != "deny" for r in rules if r.get("policy") in AUTHELIA_POLICIES):
        errors.append("Toutes les regles refusent l'acces (deny) : ajoute au moins une regle qui laisse quelqu'un entrer.")


def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    engine = config.get("engine", "oauth2-proxy")
    if engine not in SUPPORTED_ENGINES:
        errors.append(
            f"Moteur non supporte : '{engine}'. Disponibles : {', '.join(SUPPORTED_ENGINES)}."
        )
        return errors

    if engine == "oauth2-proxy":
        _validate_oauth2_proxy(config, errors)
    else:
        _validate_authelia(config, errors)

    return errors


# --------------------------------------------------------------------------
# Moteur oauth2-proxy : oauth2-proxy.cfg + snippet Nginx
# --------------------------------------------------------------------------
def generate_oauth2_proxy_cfg(config):
    """Genere le contenu de oauth2-proxy.cfg."""
    provider = config["provider"]
    cookie_secret = config.get("cookie_secret") or _random_secret(32)

    lines = [
        "# Genere par OpsForge (module authproxy).",
        "# A placer a cote du binaire oauth2-proxy, lance avec --config=oauth2-proxy.cfg",
        "",
        f'provider = "{provider}"',
        f'upstreams = ["{config["upstream"]}"]',
        f'redirect_url = "{config["redirect_url"]}"',
        f'client_id = "{config["client_id"]}"',
        f'client_secret = "{config["client_secret"]}"',
        f'cookie_secret = "{cookie_secret}"',
        f'cookie_domains = ["{config.get("cookie_domain") or ""}"]',
        'cookie_secure = true',
        'http_address = "127.0.0.1:4180"',
        'email_domains = ' + _toml_string_list(config.get("email_domains") or ["*"]),
        "",
    ]

    if provider == "github":
        lines.append("# Restreint l'acces aux membres de cette organisation GitHub")
        lines.append(f'github_org = "{config["github_org"]}"')
        team = (config.get("github_team") or "").strip()
        if team:
            lines.append(f'github_team = "{team}"')
        lines.append("")
    elif provider == "oidc":
        lines.append("# Emetteur OIDC (Keycloak / Authentik / Auth0 / autre)")
        lines.append(f'oidc_issuer_url = "{config["oidc_issuer_url"]}"')
        lines.append("")

    lines.append("# Genere par cette meme config a chaque redemarrage si absent :")
    lines.append("# pas de fichier de session persistant necessaire pour un seul serveur.")
    lines.append('session_store_type = "cookie"')

    return "\n".join(lines) + "\n"


def _toml_string_list(values):
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


def generate_oauth2_proxy_nginx_snippet(config):
    """
    Genere le fragment Nginx a inclure dans le server{} de l'appli protegee
    (auth_request vers oauth2-proxy, redirection vers /oauth2/sign_in si
    non authentifie). A coller dans le bloc genere par le module nginx.
    """
    lines = [
        "# Genere par OpsForge (module authproxy).",
        "# A coller DANS le bloc server{} de l'appli a proteger (module nginx),",
        "# avant les autres 'location /'. Necessite oauth2-proxy demarre en local",
        "# (http_address du fichier oauth2-proxy.cfg).",
        "",
        "location /oauth2/ {",
        "    proxy_pass       http://127.0.0.1:4180;",
        "    proxy_set_header Host                    $host;",
        "    proxy_set_header X-Real-IP               $remote_addr;",
        "    proxy_set_header X-Auth-Request-Redirect $request_uri;",
        "}",
        "",
        "location = /oauth2/auth {",
        "    proxy_pass       http://127.0.0.1:4180;",
        "    proxy_set_header Host             $host;",
        "    proxy_set_header X-Real-IP        $remote_addr;",
        "    proxy_set_header X-Forwarded-Uri  $request_uri;",
        "    proxy_set_header Content-Length   \"\";",
        "    proxy_pass_request_body off;",
        "}",
        "",
        "location / {",
        "    auth_request /oauth2/auth;",
        "    error_page 401 = /oauth2/sign_in?rd=$scheme://$host$request_uri;",
        "",
        "    auth_request_set $user  $upstream_http_x_auth_request_user;",
        "    auth_request_set $email $upstream_http_x_auth_request_email;",
        "    proxy_set_header X-User  $user;",
        "    proxy_set_header X-Email $email;",
        "",
        f'    proxy_pass {config["upstream"]};',
        "}",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Moteur authelia : configuration.yml + users_database.yml
# --------------------------------------------------------------------------
def generate_authelia_configuration(config):
    """Genere le contenu de configuration.yml (Authelia)."""
    domain = config["domain"]
    storage = config.get("storage_backend", "sqlite")
    notifier = config.get("notifier", "filesystem")
    session_secret = config.get("session_secret") or _random_secret(32)
    jwt_secret = config.get("jwt_secret") or _random_secret(32)
    storage_key = config.get("storage_encryption_key") or _random_secret(32)

    lines = [
        "# Genere par OpsForge (module authproxy).",
        "# A placer dans /etc/authelia/configuration.yml",
        "",
        "theme: light",
        "",
        "server:",
        "  address: 'tcp://127.0.0.1:9091'",
        "",
        "log:",
        "  level: info",
        "",
        f"jwt_secret: {jwt_secret}",
        "",
        "default_redirection_url: " + f"https://auth.{domain}",
        "",
        "authentication_backend:",
        "  file:",
        "    path: /etc/authelia/users_database.yml",
        "    password:",
        "      algorithm: argon2",
        "      argon2:",
        "        variant: argon2id",
        "        iterations: 3",
        "        memory: 65536",
        "        parallelism: 4",
        "",
        "access_control:",
        "  default_policy: deny",
        "  rules:",
    ]

    for rule in config.get("access_rules") or []:
        lines.append(f"    - domain: '{rule['domain']}'")
        lines.append(f"      policy: {rule['policy']}")
        subject = (rule.get("subject") or "").strip()
        if subject:
            kind, _, name = subject.partition(":")
            lines.append(f"      subject: '{kind}:{name}'")

    lines += [
        "",
        "session:",
        f"  secret: {session_secret}",
        "  cookies:",
        f"    - domain: '{domain}'",
        f"      authelia_url: 'https://auth.{domain}'",
        "",
        "regulation:",
        "  max_retries: 3",
        "  find_time: 2m",
        "  ban_time: 5m",
        "",
        "storage:",
        f"  encryption_key: {storage_key}",
    ]

    if storage == "sqlite":
        lines.append("  local:")
        lines.append("    path: /etc/authelia/db.sqlite3")
    else:
        lines.append("  postgres:")
        lines.append("    address: 'tcp://127.0.0.1:5432'")
        lines.append("    database: authelia")
        lines.append("    username: authelia")
        lines.append("    password: REMPLACE_PAR_TON_MOT_DE_PASSE_POSTGRES")

    lines.append("")
    lines.append("notifier:")
    if notifier == "smtp":
        lines.append("  smtp:")
        lines.append("    address: 'submission://smtp.exemple.com:587'")
        lines.append("    sender: 'authelia@exemple.com'")
        lines.append("    username: REMPLACE_PAR_TON_UTILISATEUR_SMTP")
        lines.append("    password: REMPLACE_PAR_TON_MOT_DE_PASSE_SMTP")
    else:
        lines.append("  filesystem:")
        lines.append("    filename: /etc/authelia/notification.txt")
        lines.append("    # Notifications ecrites dans un fichier local : suffisant pour un")
        lines.append("    # homelab solo. Passe a 'smtp:' pour recevoir un vrai email.")

    return "\n".join(lines) + "\n"


def generate_authelia_users_database(config):
    """
    Genere users_database.yml (backend fichier). Les mots de passe ne sont
    PAS generes ici : Authelia exige un hash argon2, qui se produit avec
    `authelia crypto hash generate argon2 --password 'ton-mot-de-passe'`.
    Mettre un mot de passe en clair dans un fichier genere serait pire que
    de laisser un placeholder explicite.
    """
    lines = [
        "# Genere par OpsForge (module authproxy).",
        "# A placer dans /etc/authelia/users_database.yml",
        "#",
        "# Les hash ci-dessous sont des PLACEHOLDERS : genere le vrai hash avec",
        "#   authelia crypto hash generate argon2 --password 'ton-mot-de-passe'",
        "# et remplace la valeur avant de deployer.",
        "",
        "users:",
    ]
    for user in config.get("users") or []:
        username = user["username"]
        display_name = user.get("display_name") or username.capitalize()
        lines.append(f"  {username}:")
        lines.append(f"    displayname: '{display_name}'")
        lines.append("    password: \"$argon2id$v=19$m=65536,t=3,p=4$REMPLACE_PAR_TON_HASH\"")
        lines.append(f"    email: {username}@{config['domain']}")
        groups = user.get("groups") or []
        groups_yaml = ", ".join(groups)
        lines.append(f"    groups: [{groups_yaml}]")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Point d'entree principal.
# --------------------------------------------------------------------------
def generate_authproxy(config):
    """
    Genere le(s) fichier(s) d'authentification a partir d'une config validee.
    Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)
    engine = config.get("engine", "oauth2-proxy")

    if engine == "oauth2-proxy":
        return {
            "oauth2-proxy.cfg": generate_oauth2_proxy_cfg(config),
            "nginx-auth-snippet.conf": generate_oauth2_proxy_nginx_snippet(config),
        }

    return {
        "configuration.yml": generate_authelia_configuration(config),
        "users_database.yml": generate_authelia_users_database(config),
    }


def write_authproxy(config, output_dir):
    """Ecrit le(s) fichier(s) genere(s) dans output_dir. Retourne la liste des chemins ecrits."""
    files = generate_authproxy(config)
    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(path)

    return written
