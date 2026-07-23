"""
core.py
-------
Generation de blocs de configuration Nginx (server{} + upstream{}) a partir
d'une config JSON. Trois modes :

  - "static"          : site statique (root + index), avec option SPA
                        (fallback try_files vers index.html)
  - "reverse_proxy"    : proxy_pass vers un backend unique (avec option
                        websocket : Upgrade/Connection)
  - "load_balancer"    : upstream{} avec plusieurs backends + algorithme
                        (round_robin par defaut, least_conn, ip_hash)

Options transverses : HTTPS (redirection 80->443 + bloc ssl_certificate
Let's Encrypt, pense-bete certbot en commentaire), gzip, en-tetes de
securite, client_max_body_size.

Usage basique :
    from modules.nginx.core import generate_config

    config = {
        "mode": "reverse_proxy",
        "server_name": "app.example.com",
        "backend_host": "127.0.0.1",
        "backend_port": 3000,
    }
    conf_text = generate_config(config)
"""

import copy
import os
import re

import yaml

SUPPORTED_MODES = ["static", "reverse_proxy", "load_balancer"]
LB_ALGORITHMS = ["round_robin", "least_conn", "ip_hash"]
SUPPORTED_TARGETS = ["nginx", "caddy", "traefik"]
# Traefik est un reverse proxy / load balancer : pas de mode "static" (pas de
# serveur de fichiers integre a la config dynamique).
TARGET_MODES = {
    "nginx": SUPPORTED_MODES,
    "caddy": SUPPORTED_MODES,
    "traefik": ["reverse_proxy", "load_balancer"],
}

DEFAULT_LISTEN_PORT = 80
DEFAULT_HTTPS_PORT = 443
DEFAULT_INDEX = "index.html"
DEFAULT_CLIENT_MAX_BODY_SIZE = "1m"

_SIZE_RE = re.compile(r"^\d+[kKmMgG]?$")
# Nom de domaine ou IPv4, tolerant (pas une RFC complete, juste un garde-fou).
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_.\-]*[A-Za-z0-9_])?$")


def _indent(text, spaces=4):
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.split("\n"))


def validate_config(config, target="nginx"):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).

    `target` : 'nginx' (defaut), 'caddy' ou 'traefik' — certaines cibles ne
    supportent pas tous les modes (ex. Traefik n'a pas de mode 'static').
    """
    errors = []
    mode = config.get("mode")

    if target not in SUPPORTED_TARGETS:
        errors.append(f"Cible non supportee : '{target}'. Cibles disponibles : {', '.join(SUPPORTED_TARGETS)}.")
        return errors

    if mode not in SUPPORTED_MODES:
        errors.append(
            f"Mode non supporte : '{mode}'. Modes disponibles : {', '.join(SUPPORTED_MODES)}."
        )
        return errors  # le reste des verifications depend du mode, inutile d'aller plus loin

    if mode not in TARGET_MODES[target]:
        errors.append(
            f"Le mode '{mode}' n'est pas supporte par la cible '{target}' "
            f"(modes disponibles pour {target} : {', '.join(TARGET_MODES[target])})."
        )
        return errors

    server_name = (config.get("server_name") or "").strip()
    if not server_name:
        errors.append("Le nom de domaine (server_name) est requis.")
    elif not _SERVER_NAME_RE.match(server_name):
        errors.append(f"Nom de domaine invalide : '{server_name}'.")

    listen_port = config.get("listen_port", DEFAULT_LISTEN_PORT)
    if not isinstance(listen_port, int) or not (1 <= listen_port <= 65535):
        errors.append(f"Port d'ecoute invalide : '{listen_port}' (attendu : 1-65535).")

    size = config.get("client_max_body_size", DEFAULT_CLIENT_MAX_BODY_SIZE)
    if not _SIZE_RE.match(str(size)):
        errors.append(
            f"client_max_body_size invalide : '{size}' (ex. valides : 1m, 500k, 2g)."
        )

    if mode == "static":
        if not (config.get("root") or "").strip():
            errors.append("Le dossier racine (root) est requis en mode 'static'.")

    elif mode == "reverse_proxy":
        if not (config.get("backend_host") or "").strip():
            errors.append("L'hote du backend (backend_host) est requis en mode 'reverse_proxy'.")
        port = config.get("backend_port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            errors.append(f"Port de backend invalide : '{port}' (attendu : 1-65535).")

    elif mode == "load_balancer":
        backends = config.get("backends") or []
        if len(backends) < 2:
            errors.append("Au moins 2 backends sont requis en mode 'load_balancer'.")
        for i, b in enumerate(backends):
            if not (b.get("host") or "").strip():
                errors.append(f"Backend #{i + 1} : hote manquant.")
            bport = b.get("port")
            if not isinstance(bport, int) or not (1 <= bport <= 65535):
                errors.append(f"Backend #{i + 1} : port invalide '{bport}'.")
        algo = config.get("lb_algorithm", "round_robin")
        if algo not in LB_ALGORITHMS:
            errors.append(
                f"Algorithme de repartition invalide : '{algo}'. "
                f"Disponibles : {', '.join(LB_ALGORITHMS)}."
            )

    if config.get("https"):
        if not server_name:
            errors.append("HTTPS necessite un server_name (utilise pour le chemin des certificats).")

    return errors


def _proxy_headers_block(websocket):
    lines = [
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
    ]
    if websocket:
        lines += [
            "proxy_http_version 1.1;",
            "proxy_set_header Upgrade $http_upgrade;",
            'proxy_set_header Connection "upgrade";',
        ]
    return "\n".join(lines)


def _security_headers_block():
    return "\n".join([
        'add_header X-Frame-Options "SAMEORIGIN" always;',
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header X-XSS-Protection "1; mode=block" always;',
        'add_header Referrer-Policy "strict-origin-when-cross-origin" always;',
    ])


def _gzip_block():
    return "\n".join([
        "gzip on;",
        "gzip_vary on;",
        "gzip_min_length 256;",
        "gzip_comp_level 5;",
        "gzip_types text/plain text/css application/json application/javascript "
        "text/xml application/xml application/xml+rss text/javascript;",
    ])


def _location_block(config):
    mode = config["mode"]

    if mode == "static":
        index_file = config.get("index_file") or DEFAULT_INDEX
        if config.get("spa"):
            try_files = f"try_files $uri $uri/ /{index_file};"
        else:
            try_files = "try_files $uri $uri/ =404;"
        return f"location / {{\n{_indent(try_files)}\n}}"

    if mode == "reverse_proxy":
        host = config["backend_host"]
        port = config["backend_port"]
        headers = _proxy_headers_block(config.get("websocket", False))
        body = f"proxy_pass http://{host}:{port};\n{headers}"
        return f"location / {{\n{_indent(body)}\n}}"

    # load_balancer
    upstream_name = config.get("upstream_name") or "backend_pool"
    headers = _proxy_headers_block(config.get("websocket", False))
    body = f"proxy_pass http://{upstream_name};\n{headers}"
    return f"location / {{\n{_indent(body)}\n}}"


def _upstream_block(config):
    upstream_name = config.get("upstream_name") or "backend_pool"
    algo = config.get("lb_algorithm", "round_robin")
    lines = []
    if algo == "least_conn":
        lines.append("least_conn;")
    elif algo == "ip_hash":
        lines.append("ip_hash;")
    # round_robin est le comportement par defaut de Nginx : rien a ecrire.

    for b in config["backends"]:
        weight = b.get("weight")
        weight_str = f" weight={weight}" if weight else ""
        lines.append(f"server {b['host']}:{b['port']}{weight_str};")

    body = "\n".join(lines)
    return f"upstream {upstream_name} {{\n{_indent(body)}\n}}"


def _server_body(config, listen_directive, ssl_lines=None):
    """Construit le corps commun d'un bloc server{} (hors listen/ssl deja fournis)."""
    parts = [listen_directive, f"server_name {config['server_name']};"]

    if ssl_lines:
        parts.append("\n".join(ssl_lines))

    size = config.get("client_max_body_size", DEFAULT_CLIENT_MAX_BODY_SIZE)
    parts.append(f"client_max_body_size {size};")

    if config.get("gzip"):
        parts.append(_gzip_block())

    if config.get("security_headers"):
        parts.append(_security_headers_block())

    if config["mode"] == "static":
        root = config["root"]
        index_file = config.get("index_file") or DEFAULT_INDEX
        parts.append(f"root {root};")
        parts.append(f"index {index_file};")

    parts.append(_location_block(config))

    return "\n\n".join(parts)


def generate_config(config):
    """
    Genere le contenu complet d'un fichier de config Nginx (server{} et,
    en mode load_balancer, upstream{} associe) pour la config fournie.

    Args:
        config (dict): voir validate_config() pour le detail des cles
            attendues selon le mode.

    Returns:
        str: contenu pret a etre ecrit dans /etc/nginx/sites-available/<nom>

    Raises:
        ValueError: si la config est invalide (voir validate_config()).
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    mode = config["mode"]
    https = bool(config.get("https"))
    listen_port = config.get("listen_port", DEFAULT_LISTEN_PORT)
    server_name = config["server_name"]

    blocks = []

    if mode == "load_balancer":
        blocks.append(_upstream_block(config))

    if https:
        # Bloc HTTP : redirection permanente vers HTTPS.
        http_redirect = (
            f"listen {listen_port};\n"
            f"server_name {server_name};\n\n"
            "return 301 https://$host$request_uri;"
        )
        blocks.append(f"server {{\n{_indent(http_redirect)}\n}}")

        ssl_lines = [
            f"ssl_certificate /etc/letsencrypt/live/{server_name}/fullchain.pem;",
            f"ssl_certificate_key /etc/letsencrypt/live/{server_name}/privkey.pem;",
            "ssl_protocols TLSv1.2 TLSv1.3;",
            "ssl_ciphers HIGH:!aNULL:!MD5;",
            "ssl_prefer_server_ciphers on;",
        ]
        body = _server_body(config, f"listen {DEFAULT_HTTPS_PORT} ssl http2;", ssl_lines)
        blocks.append(f"server {{\n{_indent(body)}\n}}")
    else:
        body = _server_body(config, f"listen {listen_port};")
        blocks.append(f"server {{\n{_indent(body)}\n}}")

    header_comment = (
        f"# Genere par OpsForge — module nginx (mode: {mode})\n"
        f"# Pour activer : sudo ln -s /etc/nginx/sites-available/{server_name} "
        f"/etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx"
    )
    if https:
        header_comment += (
            f"\n# HTTPS : genere le certificat AVANT de recharger nginx avec ce fichier :\n"
            f"#   sudo certbot certonly --nginx -d {server_name}"
        )

    return header_comment + "\n\n" + "\n\n".join(blocks) + "\n"


def write_config(config, output_path):
    """Genere la config et l'ecrit directement dans un fichier."""
    content = generate_config(config)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


# --------------------------------------------------------------------------
# Cible Caddy — meme formulaire, sortie en Caddyfile
# --------------------------------------------------------------------------
_CADDY_UNITS = {"": "B", "k": "KB", "K": "KB", "m": "MB", "M": "MB", "g": "GB", "G": "GB"}


def _caddy_size(size):
    """Convertit une taille style Nginx ('10m', '500k', '2g') en unite Caddy ('10MB', '500KB', '2GB')."""
    m = re.match(r"^(\d+)([kKmMgG]?)$", str(size))
    if not m:
        return None
    number, unit = m.groups()
    return f"{number}{_CADDY_UNITS.get(unit, 'B')}"


def _caddy_security_headers_block():
    return (
        "header {\n"
        '    X-Frame-Options "SAMEORIGIN"\n'
        '    X-Content-Type-Options "nosniff"\n'
        '    X-XSS-Protection "1; mode=block"\n'
        '    Referrer-Policy "strict-origin-when-cross-origin"\n'
        "}"
    )


def generate_caddy(config):
    """
    Genere un Caddyfile (bloc de site) equivalent a la config Nginx fournie.

    Caddy gere le HTTPS automatiquement (Let's Encrypt) des qu'un nom de
    domaine est utilise comme adresse de site ; `https: false` force l'ecoute
    en clair via le prefixe `http://`.
    """
    errors = validate_config(config, target="caddy")
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    mode = config["mode"]
    server_name = config["server_name"]
    https = bool(config.get("https"))
    address = server_name if https else f"http://{server_name}"

    directives = []

    if mode == "static":
        root = config["root"]
        index_file = config.get("index_file") or DEFAULT_INDEX
        directives.append(f"root * {root}")
        if config.get("spa"):
            directives.append(f"try_files {{path}} /{index_file}")
        directives.append("file_server")

    elif mode == "reverse_proxy":
        host = config["backend_host"]
        port = config["backend_port"]
        # Caddy gere nativement les upgrades WebSocket sur reverse_proxy, sans directive dediee.
        directives.append(f"reverse_proxy {host}:{port}")

    else:  # load_balancer
        backends = " ".join(f"{b['host']}:{b['port']}" for b in config["backends"])
        algo = config.get("lb_algorithm", "round_robin")
        if any(b.get("weight") for b in config["backends"]):
            directives.append(
                "# Ponderation par backend ignoree pour la cible Caddy "
                "(non transposable telle quelle depuis Nginx)."
            )
        directives.append(f"reverse_proxy {backends} {{\n    lb_policy {algo}\n}}")

    if config.get("gzip"):
        directives.append("encode gzip")

    size = config.get("client_max_body_size", DEFAULT_CLIENT_MAX_BODY_SIZE)
    caddy_size = _caddy_size(size)
    if caddy_size:
        directives.append(f"request_body {{\n    max_size {caddy_size}\n}}")

    if config.get("security_headers"):
        directives.append(_caddy_security_headers_block())

    corps = "\n\n".join(directives)
    site_block = f"{address} {{\n{_indent(corps)}\n}}"

    header_comment = (
        f"# Genere par OpsForge — module nginx (cible: caddy, mode: {mode})\n"
        f"# Pour activer : place ce bloc dans ton Caddyfile puis `caddy reload`"
        f" (ou `caddy fmt --overwrite` pour reformater)."
    )
    if https:
        header_comment += (
            "\n# HTTPS automatique : Caddy obtient et renouvelle le certificat "
            "Let's Encrypt tout seul au premier demarrage (aucune commande certbot requise)."
        )

    return header_comment + "\n\n" + site_block + "\n"


# --------------------------------------------------------------------------
# Cible Traefik — meme formulaire, sortie en config dynamique YAML (file provider)
# --------------------------------------------------------------------------
def _traefik_router_name(server_name):
    return re.sub(r"[^A-Za-z0-9_]", "_", server_name)


def generate_traefik(config):
    """
    Genere un fichier de config dynamique Traefik (provider "file", format
    YAML) : un router + un service loadBalancer equivalents a la config
    Nginx fournie.

    Traefik n'a pas de mode 'static' (ce n'est pas un serveur de fichiers) :
    seuls 'reverse_proxy' et 'load_balancer' sont disponibles pour cette
    cible (voir TARGET_MODES).
    """
    errors = validate_config(config, target="traefik")
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    mode = config["mode"]
    server_name = config["server_name"]
    https = bool(config.get("https"))
    nom = _traefik_router_name(server_name)

    if mode == "reverse_proxy":
        servers = [{"url": f"http://{config['backend_host']}:{config['backend_port']}"}]
        algo = None
    else:  # load_balancer
        servers = [{"url": f"http://{b['host']}:{b['port']}"} for b in config["backends"]]
        algo = config.get("lb_algorithm", "round_robin")

    service = {"loadBalancer": {"servers": servers}}
    if algo == "ip_hash":
        # Equivalent le plus proche d'ip_hash cote Traefik : sessions collantes par cookie.
        service["loadBalancer"]["sticky"] = {"cookie": {"name": "opsforge_lb"}}

    router = {
        "rule": f"Host(`{server_name}`)",
        "service": nom,
        "entryPoints": ["websecure"] if https else ["web"],
    }
    if https:
        router["tls"] = {"certResolver": "letsencrypt"}

    doc = {"http": {"routers": {nom: router}, "services": {nom: service}}}
    yaml_text = yaml.dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True)

    header = (
        f"# Genere par OpsForge — module nginx (cible: traefik, mode: {mode})\n"
        "# Fichier de config dynamique (provider \"file\") : place-le dans le dossier\n"
        "# surveille (ex: /etc/traefik/dynamic/) et declare-le dans traefik.yml :\n"
        "#   providers:\n"
        "#     file:\n"
        "#       directory: /etc/traefik/dynamic\n"
        "#       watch: true\n"
    )
    if algo == "least_conn":
        header += (
            "# Note : Traefik ne propose pas d'equivalent direct a 'least_conn' ; "
            "seul le round-robin (pondere) est disponible nativement.\n"
        )
    if https:
        header += (
            "# HTTPS : necessite un certResolver \"letsencrypt\" configure dans traefik.yml "
            "(certificatesResolvers) et l'entryPoint \"websecure\" (443).\n"
        )

    return header + "\n" + yaml_text


def generate(config, target="nginx"):
    """Dispatcher : genere la config pour la cible demandee ('nginx' [defaut], 'caddy', 'traefik')."""
    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"Cible non supportee : '{target}'. Cibles disponibles : {', '.join(SUPPORTED_TARGETS)}.")
    if target == "nginx":
        return generate_config(config)
    if target == "caddy":
        return generate_caddy(config)
    return generate_traefik(config)


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "spa": {
        "mode": "static",
        "server_name": "app.example.com",
        "root": "/var/www/app",
        "index_file": "index.html",
        "spa": True,
        "gzip": True,
        "security_headers": True,
    },
    "static-site": {
        "mode": "static",
        "server_name": "site.example.com",
        "root": "/var/www/site",
        "index_file": "index.html",
        "spa": False,
        "gzip": True,
        "security_headers": True,
    },
    "api-reverse-proxy": {
        "mode": "reverse_proxy",
        "server_name": "api.example.com",
        "backend_host": "127.0.0.1",
        "backend_port": 3000,
        "websocket": True,
        "gzip": True,
        "security_headers": True,
        "client_max_body_size": "10m",
    },
    "load-balanced-app": {
        "mode": "load_balancer",
        "server_name": "app.example.com",
        "upstream_name": "app_pool",
        "backends": [
            {"host": "127.0.0.1", "port": 3001},
            {"host": "127.0.0.1", "port": 3002},
        ],
        "lb_algorithm": "least_conn",
        "gzip": True,
        "security_headers": True,
    },
    "https-reverse-proxy": {
        "mode": "reverse_proxy",
        "server_name": "app.example.com",
        "backend_host": "127.0.0.1",
        "backend_port": 8080,
        "https": True,
        "websocket": True,
        "gzip": True,
        "security_headers": True,
    },
}


def list_presets():
    return list(PRESETS.keys())


def get_preset(name):
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Presets disponibles : {', '.join(PRESETS.keys())}."
        )
    return copy.deepcopy(PRESETS[name])
