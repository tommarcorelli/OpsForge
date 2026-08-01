"""
core.py
-------
Generation de configuration SSH a partir d'une config JSON. Deux roles,
symetriques aux deux bouts d'une connexion :

  - "client" : le fichier ~/.ssh/config de ta machine. Des blocs Host
               nommes (alias, user, port, cle dediee, rebond via bastion,
               redirections de ports) plutot que des lignes de commande
               interminables retapees a chaque fois.
  - "server" : le durcissement du demon sshd. Genere un fragment
               /etc/ssh/sshd_config.d/99-*.conf (mecanisme d'inclusion
               standard depuis Debian 12 / Ubuntu 22.04) plutot que de
               reecrire le sshd_config complet de la distribution : on
               n'ecrase rien, et le fichier se retire en le supprimant.

Le role "server" peut aussi produire un fichier authorized_keys avec des
restrictions par cle (from=, command=, no-port-forwarding...) : c'est la
seule facon d'appliquer des limites a UNE cle donnee, sshd_config ne sait
travailler que par utilisateur ou par groupe.

Usage basique :
    from modules.ssh.core import generate_ssh

    config = {"preset": "serveur-durci", "role": "server"}
    files = generate_ssh(config)   # {"sshd_config.d/99-durcissement.conf": "..."}
"""

import copy
import os
import re

SUPPORTED_ROLES = ["client", "server"]

# Nom du fragment sshd. Le prefixe numerique compte : sshd lit les fichiers
# de sshd_config.d/ dans l'ordre alphabetique et garde la PREMIERE valeur
# rencontree pour chaque directive. Un 99 arriverait donc apres les fragments
# de la distribution (50-cloud-init.conf, etc.) et serait ignore sur les
# directives qu'ils definissent deja. On prefixe volontairement en 10 pour
# passer devant, tout en laissant la place a un 00 fait main.
SSHD_FRAGMENT_NAME = "sshd_config.d/10-opsforge-durcissement.conf"
CLIENT_CONFIG_NAME = "ssh_config"
AUTHORIZED_KEYS_NAME = "authorized_keys"

# Valeurs acceptees par sshd pour les directives a choix ferme.
PERMIT_ROOT_LOGIN_VALUES = ["no", "prohibit-password", "forced-commands-only", "yes"]
ALLOW_TCP_FORWARDING_VALUES = ["no", "yes", "local", "remote", "all"]
LOG_LEVEL_VALUES = ["QUIET", "FATAL", "ERROR", "INFO", "VERBOSE", "DEBUG"]

# Algorithmes retenus quand "modern_crypto" est actif : uniquement des
# primitives sans faiblesse connue (pas de CBC, pas de SHA-1, pas de
# courbes NIST). Aligne sur les recommandations ANSSI/Mozilla "modern".
MODERN_CIPHERS = [
    "chacha20-poly1305@openssh.com",
    "aes256-gcm@openssh.com",
    "aes128-gcm@openssh.com",
    "aes256-ctr",
]
MODERN_MACS = [
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com",
    "umac-128-etm@openssh.com",
]
MODERN_KEX = [
    "sntrup761x25519-sha512@openssh.com",
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "diffie-hellman-group16-sha512",
]

# Restrictions applicables a une cle dans authorized_keys.
KEY_RESTRICTIONS = {
    "no_port_forwarding": "no-port-forwarding",
    "no_agent_forwarding": "no-agent-forwarding",
    "no_x11_forwarding": "no-X11-forwarding",
    "no_pty": "no-pty",
    "restrict": "restrict",
}

# Prefixes de cles publiques acceptes (le reste est refuse : une "cle"
# qui ne commence pas par un type connu est presque toujours une cle
# PRIVEE collee par erreur, ou un copier-coller tronque).
PUBLIC_KEY_PREFIXES = (
    "ssh-ed25519",
    "sk-ssh-ed25519@openssh.com",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)

ALIAS_RE = re.compile(r"^[A-Za-z0-9._*?\-]+$")
NAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
# host:port, user@host, user@host:port, ou simple alias defini plus haut
PROXY_JUMP_RE = re.compile(r"^[A-Za-z0-9._\-]+(@[A-Za-z0-9._\-]+)?(:\d{1,5})?$")

# --------------------------------------------------------------------------
# Presets : un point de depart realiste par situation courante. Les valeurs
# sont volontairement completes (pas de "TODO") pour que le fichier genere
# soit utilisable tel quel apres remplacement des noms d'hotes.
# --------------------------------------------------------------------------
PRESETS = {
    "poste-de-travail": {
        "label": "Poste de travail (plusieurs serveurs, une cle par serveur)",
        "role": "client",
        "config": {
            "defaults": {
                "server_alive_interval": 60,
                "server_alive_count_max": 3,
                "add_keys_to_agent": True,
                "identities_only": True,
                "hash_known_hosts": True,
                "compression": False,
                "forward_agent": False,
            },
            "hosts": [
                {
                    "alias": "prod-web",
                    "hostname": "203.0.113.10",
                    "user": "deploy",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_prod",
                },
                {
                    "alias": "dev-box",
                    "hostname": "192.168.1.42",
                    "user": "tom",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_dev",
                },
                {
                    "alias": "github.com",
                    "hostname": "github.com",
                    "user": "git",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_github",
                },
            ],
        },
    },
    "acces-bastion": {
        "label": "Acces via bastion (rebond ProxyJump vers un reseau prive)",
        "role": "client",
        "config": {
            "defaults": {
                "server_alive_interval": 60,
                "server_alive_count_max": 3,
                "add_keys_to_agent": True,
                "identities_only": True,
                "hash_known_hosts": True,
                "compression": False,
                "forward_agent": False,
            },
            "hosts": [
                {
                    "alias": "bastion",
                    "hostname": "bastion.exemple.com",
                    "user": "jump",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_bastion",
                },
                {
                    "alias": "app-01",
                    "hostname": "10.0.1.11",
                    "user": "deploy",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_prod",
                    "proxy_jump": "bastion",
                },
                {
                    "alias": "db-01",
                    "hostname": "10.0.2.21",
                    "user": "deploy",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_prod",
                    "proxy_jump": "bastion",
                    "local_forwards": ["5432:localhost:5432"],
                },
            ],
        },
    },
    "tunnels": {
        "label": "Tunnels (redirections de ports vers des services prives)",
        "role": "client",
        "config": {
            "defaults": {
                "server_alive_interval": 30,
                "server_alive_count_max": 3,
                "add_keys_to_agent": True,
                "identities_only": True,
                "hash_known_hosts": True,
                "compression": True,
                "forward_agent": False,
            },
            "hosts": [
                {
                    "alias": "tunnel-db",
                    "hostname": "203.0.113.10",
                    "user": "deploy",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_prod",
                    "local_forwards": ["5432:localhost:5432", "6379:localhost:6379"],
                    "exit_on_forward_failure": True,
                },
                {
                    "alias": "socks-proxy",
                    "hostname": "203.0.113.10",
                    "user": "deploy",
                    "port": 22,
                    "identity_file": "~/.ssh/id_ed25519_prod",
                    "dynamic_forward": 1080,
                },
            ],
        },
    },
    "serveur-durci": {
        "label": "Serveur durci (cles uniquement, root desactive)",
        "role": "server",
        "config": {
            "port": 22,
            "permit_root_login": "no",
            "password_authentication": False,
            "pubkey_authentication": True,
            "kbd_interactive_authentication": False,
            "permit_empty_passwords": False,
            "allow_groups": ["ssh-users"],
            "max_auth_tries": 3,
            "max_sessions": 5,
            "login_grace_time": 30,
            "client_alive_interval": 300,
            "client_alive_count_max": 2,
            "x11_forwarding": False,
            "allow_tcp_forwarding": "no",
            "allow_agent_forwarding": False,
            "gateway_ports": False,
            "permit_tunnel": False,
            "use_dns": False,
            "modern_crypto": True,
            "log_level": "VERBOSE",
            "banner": "/etc/issue.net",
        },
    },
    "bastion": {
        "label": "Bastion / hote de rebond (forwarding autorise, shell interdit)",
        "role": "server",
        "config": {
            "port": 22,
            "permit_root_login": "no",
            "password_authentication": False,
            "pubkey_authentication": True,
            "kbd_interactive_authentication": False,
            "permit_empty_passwords": False,
            "allow_groups": ["bastion-users"],
            "max_auth_tries": 3,
            "max_sessions": 10,
            "login_grace_time": 20,
            "client_alive_interval": 120,
            "client_alive_count_max": 3,
            "x11_forwarding": False,
            # Un bastion sert justement a rebondir : le forwarding TCP est
            # sa raison d'etre, contrairement au preset serveur-durci.
            "allow_tcp_forwarding": "yes",
            "allow_agent_forwarding": False,
            "gateway_ports": False,
            "permit_tunnel": False,
            "use_dns": False,
            "modern_crypto": True,
            "log_level": "VERBOSE",
            "banner": "/etc/issue.net",
        },
    },
    "sftp-only": {
        "label": "Depot SFTP (groupe chroote, aucun acces shell)",
        "role": "server",
        "config": {
            "port": 22,
            "permit_root_login": "no",
            "password_authentication": False,
            "pubkey_authentication": True,
            "kbd_interactive_authentication": False,
            "permit_empty_passwords": False,
            "max_auth_tries": 3,
            "max_sessions": 5,
            "login_grace_time": 30,
            "client_alive_interval": 300,
            "client_alive_count_max": 2,
            "x11_forwarding": False,
            "allow_tcp_forwarding": "no",
            "allow_agent_forwarding": False,
            "gateway_ports": False,
            "permit_tunnel": False,
            "use_dns": False,
            "modern_crypto": True,
            "log_level": "VERBOSE",
            "sftp_only_group": "sftponly",
            "sftp_chroot_dir": "/srv/sftp/%u",
        },
    },
    "cle-restreinte": {
        "label": "Cle de deploiement restreinte (authorized_keys + sshd durci)",
        "role": "server",
        "config": {
            "port": 22,
            "permit_root_login": "no",
            "password_authentication": False,
            "pubkey_authentication": True,
            "kbd_interactive_authentication": False,
            "permit_empty_passwords": False,
            "allow_groups": ["ssh-users"],
            "max_auth_tries": 3,
            "max_sessions": 5,
            "login_grace_time": 30,
            "client_alive_interval": 300,
            "client_alive_count_max": 2,
            "x11_forwarding": False,
            "allow_tcp_forwarding": "no",
            "allow_agent_forwarding": False,
            "gateway_ports": False,
            "permit_tunnel": False,
            "use_dns": False,
            "modern_crypto": True,
            "log_level": "VERBOSE",
            "authorized_keys": [
                {
                    "comment": "cle du runner CI (deploiement automatise)",
                    "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIREMPLACE_PAR_TA_CLE ci@runner",
                    "from": ["203.0.113.0/24"],
                    "command": "/usr/local/bin/deploy.sh",
                    "restrict": True,
                },
                {
                    "comment": "cle d'administration (poste de travail)",
                    "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIREMPLACE_PAR_TA_CLE tom@laptop",
                    "no_agent_forwarding": True,
                    "no_x11_forwarding": True,
                },
            ],
        },
    },
    "custom": {
        "label": "Personnalise (config fournie manuellement)",
        "role": "client",
        "config": {"hosts": []},
    },
}


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def list_presets_by_role(role):
    """Liste les presets d'un role donne ('client' ou 'server')."""
    return [name for name, p in PRESETS.items() if p["role"] == role]


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
    config["role"] = preset_def["role"]
    return config


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _validate_port(value, label, errors):
    try:
        port = int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} : port invalide ('{value}'), un entier est attendu.")
        return
    if not 1 <= port <= 65535:
        errors.append(f"{label} : port hors plage ({port}), attendu entre 1 et 65535.")


def _validate_forward(spec, label, errors):
    """
    Verifie une redirection de port au format accepte par OpenSSH :
        port:hote:port_distant           (3 champs)
        adresse:port:hote:port_distant   (4 champs, bind explicite)
    """
    parts = str(spec).split(":")
    if len(parts) not in (3, 4):
        errors.append(
            f"{label} : redirection invalide ('{spec}'). Format attendu : "
            "'port_local:hote_distant:port_distant' (ou "
            "'adresse_locale:port_local:hote_distant:port_distant')."
        )
        return
    # Le premier champ est un port sauf en forme 4 champs (adresse de bind).
    port_fields = parts[1::2] if len(parts) == 4 else [parts[0], parts[2]]
    for field in port_fields:
        if not field.isdigit() or not 1 <= int(field) <= 65535:
            errors.append(
                f"{label} : redirection invalide ('{spec}'), '{field}' n'est pas un port valide."
            )
            return


def _validate_client(config, errors):
    hosts = config.get("hosts") or []
    if not hosts:
        errors.append("Aucun hote defini : ajoute au moins un bloc Host.")
        return

    aliases = []
    for index, host in enumerate(hosts, start=1):
        label = f"Hote #{index}"
        alias = (host.get("alias") or "").strip()
        if not alias:
            errors.append(f"{label} : alias manquant (le nom que tu tapes apres 'ssh').")
        elif not ALIAS_RE.match(alias):
            errors.append(
                f"{label} : alias invalide ('{alias}'). Lettres, chiffres, "
                "point, tiret, underscore et jokers * ? uniquement."
            )
        else:
            label = f"Hote '{alias}'"
            aliases.append(alias)

        hostname = (host.get("hostname") or "").strip()
        if not hostname:
            errors.append(f"{label} : hostname manquant (nom DNS ou adresse IP reelle).")

        user = (host.get("user") or "").strip()
        if user and not NAME_RE.match(user):
            errors.append(f"{label} : nom d'utilisateur invalide ('{user}').")

        if host.get("port"):
            _validate_port(host["port"], label, errors)

        proxy_jump = (host.get("proxy_jump") or "").strip()
        if proxy_jump and proxy_jump != "none" and not PROXY_JUMP_RE.match(proxy_jump):
            errors.append(
                f"{label} : ProxyJump invalide ('{proxy_jump}'). Attendu : un alias "
                "defini plus haut, ou 'utilisateur@hote', ou 'utilisateur@hote:port'."
            )

        for forward in host.get("local_forwards") or []:
            _validate_forward(forward, f"{label} (LocalForward)", errors)
        for forward in host.get("remote_forwards") or []:
            _validate_forward(forward, f"{label} (RemoteForward)", errors)
        if host.get("dynamic_forward"):
            _validate_port(host["dynamic_forward"], f"{label} (DynamicForward)", errors)

    duplicates = {a for a in aliases if aliases.count(a) > 1}
    for alias in sorted(duplicates):
        errors.append(
            f"Alias '{alias}' defini plusieurs fois : OpenSSH ne garderait que "
            "les options du premier bloc rencontre."
        )

    # Un ProxyJump qui pointe sur un simple nom (sans @) est cense etre un
    # alias declare dans le meme fichier ; sinon SSH tenterait de resoudre ce
    # nom en DNS, ce qui n'est presque jamais l'intention.
    for host in hosts:
        proxy_jump = (host.get("proxy_jump") or "").strip()
        if not proxy_jump or "@" in proxy_jump or "." in proxy_jump or proxy_jump == "none":
            continue
        if proxy_jump not in aliases:
            errors.append(
                f"Hote '{host.get('alias')}' : ProxyJump '{proxy_jump}' ne correspond "
                "a aucun alias defini dans cette config."
            )


def _validate_authorized_keys(entries, errors):
    for index, entry in enumerate(entries, start=1):
        label = f"Cle autorisee #{index}"
        key = (entry.get("key") or "").strip()
        if not key:
            errors.append(f"{label} : cle publique manquante.")
            continue
        if key.startswith("-----BEGIN"):
            errors.append(
                f"{label} : ceci est une cle PRIVEE. Colle la cle publique "
                "(fichier .pub, une seule ligne commencant par ssh-ed25519 ou ssh-rsa)."
            )
            continue
        if not key.startswith(PUBLIC_KEY_PREFIXES):
            errors.append(
                f"{label} : type de cle non reconnu. Attendu une ligne commencant par "
                f"{', '.join(PUBLIC_KEY_PREFIXES[:3])}…"
            )
            continue
        if len(key.split()) < 2:
            errors.append(f"{label} : cle publique incomplete (type et donnees attendus).")

        command = entry.get("command")
        if command and '"' in str(command):
            errors.append(
                f"{label} : la commande forcee ne peut pas contenir de guillemet double "
                "(elle est elle-meme entre guillemets dans authorized_keys)."
            )


def _validate_server(config, errors):
    _validate_port(config.get("port", 22), "sshd", errors)

    permit_root = config.get("permit_root_login", "no")
    if permit_root not in PERMIT_ROOT_LOGIN_VALUES:
        errors.append(
            f"PermitRootLogin invalide : '{permit_root}'. "
            f"Valeurs acceptees : {', '.join(PERMIT_ROOT_LOGIN_VALUES)}."
        )

    tcp_fwd = config.get("allow_tcp_forwarding", "no")
    if str(tcp_fwd) not in ALLOW_TCP_FORWARDING_VALUES:
        errors.append(
            f"AllowTcpForwarding invalide : '{tcp_fwd}'. "
            f"Valeurs acceptees : {', '.join(ALLOW_TCP_FORWARDING_VALUES)}."
        )

    log_level = config.get("log_level", "INFO")
    if log_level not in LOG_LEVEL_VALUES:
        errors.append(
            f"LogLevel invalide : '{log_level}'. "
            f"Valeurs acceptees : {', '.join(LOG_LEVEL_VALUES)}."
        )

    for key, label in (("max_auth_tries", "MaxAuthTries"),
                       ("max_sessions", "MaxSessions"),
                       ("login_grace_time", "LoginGraceTime"),
                       ("client_alive_interval", "ClientAliveInterval"),
                       ("client_alive_count_max", "ClientAliveCountMax")):
        if key not in config:
            continue
        try:
            value = int(config[key])
        except (TypeError, ValueError):
            errors.append(f"{label} : entier attendu, recu '{config[key]}'.")
            continue
        if value < 0:
            errors.append(f"{label} : valeur negative ({value}).")

    for key, label in (("allow_users", "AllowUsers"), ("allow_groups", "AllowGroups")):
        for name in config.get(key) or []:
            if not NAME_RE.match(str(name)):
                errors.append(f"{label} : nom invalide ('{name}').")

    if not config.get("pubkey_authentication", True) and not config.get("password_authentication", False):
        errors.append(
            "Ni l'authentification par cle ni celle par mot de passe ne sont "
            "activees : plus personne ne pourrait se connecter."
        )

    sftp_group = config.get("sftp_only_group")
    if sftp_group:
        if not NAME_RE.match(str(sftp_group)):
            errors.append(f"Groupe SFTP invalide : '{sftp_group}'.")
        chroot = config.get("sftp_chroot_dir") or ""
        if chroot and not str(chroot).startswith("/"):
            errors.append(
                f"ChrootDirectory invalide : '{chroot}'. Un chemin absolu est attendu "
                "(le repertoire doit appartenir a root et n'etre inscriptible que par lui)."
            )

    _validate_authorized_keys(config.get("authorized_keys") or [], errors)


def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    preset = config.get("preset", "custom")
    if preset not in PRESETS:
        errors.append(
            f"Preset non supporte : '{preset}'. Disponibles : {', '.join(PRESETS)}."
        )

    role = config.get("role", "client")
    if role not in SUPPORTED_ROLES:
        errors.append(
            f"Role non supporte : '{role}'. Disponibles : {', '.join(SUPPORTED_ROLES)}."
        )
        return errors

    if role == "client":
        _validate_client(config, errors)
    else:
        _validate_server(config, errors)

    return errors


# --------------------------------------------------------------------------
# Role client : ~/.ssh/config
# --------------------------------------------------------------------------
def _yesno(value):
    return "yes" if value else "no"


def _build_defaults_block(defaults):
    """
    Bloc 'Host *' place en FIN de fichier : OpenSSH applique la premiere
    valeur trouvee pour chaque option, donc les reglages generaux doivent
    venir apres les blocs specifiques pour ne pas les court-circuiter.
    """
    lines = [
        "# Reglages communs a tous les hotes.",
        "# OpenSSH garde la PREMIERE valeur rencontree pour chaque option :",
        "# ce bloc doit rester en fin de fichier pour ne pas ecraser les blocs ci-dessus.",
        "Host *",
    ]
    if defaults.get("server_alive_interval"):
        lines.append(f"    ServerAliveInterval {int(defaults['server_alive_interval'])}")
    if defaults.get("server_alive_count_max"):
        lines.append(f"    ServerAliveCountMax {int(defaults['server_alive_count_max'])}")
    if defaults.get("add_keys_to_agent"):
        lines.append("    AddKeysToAgent yes")
    if defaults.get("identities_only"):
        # Sans ca, ssh propose TOUTES les cles de l'agent une par une et peut
        # depasser MaxAuthTries avant d'arriver a la bonne.
        lines.append("    IdentitiesOnly yes")
    if defaults.get("hash_known_hosts"):
        lines.append("    HashKnownHosts yes")
    lines.append(f"    Compression {_yesno(defaults.get('compression'))}")
    lines.append(f"    ForwardAgent {_yesno(defaults.get('forward_agent'))}")
    if defaults.get("control_master"):
        # Multiplexage : les connexions suivantes vers le meme hote reutilisent
        # la premiere (plus rapide, une seule authentification).
        lines.append("    ControlMaster auto")
        lines.append("    ControlPath ~/.ssh/control-%r@%h:%p")
        lines.append(f"    ControlPersist {defaults.get('control_persist') or '10m'}")
    return "\n".join(lines)


def _build_host_block(host):
    alias = host["alias"].strip()
    lines = []

    comment = (host.get("comment") or "").strip()
    if comment:
        lines.append(f"# {comment}")

    lines.append(f"Host {alias}")
    lines.append(f"    HostName {host['hostname'].strip()}")

    user = (host.get("user") or "").strip()
    if user:
        lines.append(f"    User {user}")

    port = host.get("port")
    if port and int(port) != 22:
        lines.append(f"    Port {int(port)}")

    identity_file = (host.get("identity_file") or "").strip()
    if identity_file:
        lines.append(f"    IdentityFile {identity_file}")
        lines.append("    IdentitiesOnly yes")

    proxy_jump = (host.get("proxy_jump") or "").strip()
    if proxy_jump:
        lines.append(f"    ProxyJump {proxy_jump}")

    if host.get("forward_agent"):
        lines.append("    ForwardAgent yes")

    for forward in host.get("local_forwards") or []:
        lines.append(f"    LocalForward {_format_forward(forward)}")
    for forward in host.get("remote_forwards") or []:
        lines.append(f"    RemoteForward {_format_forward(forward)}")
    if host.get("dynamic_forward"):
        lines.append(f"    DynamicForward {int(host['dynamic_forward'])}")

    if host.get("exit_on_forward_failure"):
        # Sans ca, ssh ouvre quand meme la session si un port local est deja
        # pris : le tunnel semble monte alors qu'il ne l'est pas.
        lines.append("    ExitOnForwardFailure yes")

    if host.get("request_tty") is False:
        lines.append("    RequestTTY no")

    return "\n".join(lines)


def _format_forward(spec):
    """
    Passe de 'port:hote:port_distant' a 'port hote:port_distant', la forme
    attendue dans un fichier de config (la forme compacte avec ':' partout
    n'est valide qu'en ligne de commande derriere -L/-R).
    """
    parts = str(spec).split(":")
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]} {parts[2]}:{parts[3]}"
    return f"{parts[0]} {parts[1]}:{parts[2]}"


def generate_client_config(config):
    """Genere le contenu d'un fichier ~/.ssh/config."""
    hosts = config.get("hosts") or []
    defaults = config.get("defaults") or {}

    blocks = [
        "# Genere par OpsForge (module ssh).\n"
        "# A placer dans ~/.ssh/config (permissions 600).\n"
        "# Chaque bloc Host cree un raccourci : 'ssh <alias>' suffit ensuite."
    ]
    blocks.extend(_build_host_block(host) for host in hosts)
    if defaults:
        blocks.append(_build_defaults_block(defaults))

    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------
# Role serveur : fragment sshd_config.d/
# --------------------------------------------------------------------------
def generate_sshd_config(config):
    """Genere le contenu d'un fragment /etc/ssh/sshd_config.d/*.conf."""
    lines = [
        "# Genere par OpsForge (module ssh).",
        f"# A placer dans /etc/ssh/{SSHD_FRAGMENT_NAME} (root:root, 644).",
        "# Verifie la syntaxe avec 'sshd -t' AVANT de recharger le service,",
        "# et garde une session ouverte le temps de tester une nouvelle connexion.",
        "",
        "# --- Reseau ---",
    ]

    port = int(config.get("port", 22))
    lines.append(f"Port {port}")

    listen_addresses = config.get("listen_addresses") or []
    for address in listen_addresses:
        lines.append(f"ListenAddress {address}")

    lines.append(f"AddressFamily {config.get('address_family', 'any')}")
    lines.append(f"UseDNS {_yesno(config.get('use_dns', False))}")

    lines.append("")
    lines.append("# --- Authentification ---")
    lines.append(f"PermitRootLogin {config.get('permit_root_login', 'no')}")
    lines.append(f"PubkeyAuthentication {_yesno(config.get('pubkey_authentication', True))}")
    lines.append(f"PasswordAuthentication {_yesno(config.get('password_authentication', False))}")
    lines.append(
        f"KbdInteractiveAuthentication {_yesno(config.get('kbd_interactive_authentication', False))}"
    )
    lines.append(f"PermitEmptyPasswords {_yesno(config.get('permit_empty_passwords', False))}")
    lines.append(f"MaxAuthTries {int(config.get('max_auth_tries', 3))}")
    lines.append(f"MaxSessions {int(config.get('max_sessions', 5))}")
    lines.append(f"LoginGraceTime {int(config.get('login_grace_time', 30))}")

    allow_users = config.get("allow_users") or []
    allow_groups = config.get("allow_groups") or []
    if allow_users:
        lines.append(f"AllowUsers {' '.join(allow_users)}")
    if allow_groups:
        lines.append(f"AllowGroups {' '.join(allow_groups)}")
    if allow_users or allow_groups:
        lines.append(
            "# Tout compte hors de cette liste est refuse, meme avec une cle valide."
        )

    lines.append("")
    lines.append("# --- Sessions ---")
    lines.append(f"ClientAliveInterval {int(config.get('client_alive_interval', 300))}")
    lines.append(f"ClientAliveCountMax {int(config.get('client_alive_count_max', 2))}")
    lines.append(f"X11Forwarding {_yesno(config.get('x11_forwarding', False))}")
    lines.append(f"AllowTcpForwarding {config.get('allow_tcp_forwarding', 'no')}")
    lines.append(f"AllowAgentForwarding {_yesno(config.get('allow_agent_forwarding', False))}")
    lines.append(f"GatewayPorts {_yesno(config.get('gateway_ports', False))}")
    lines.append(f"PermitTunnel {_yesno(config.get('permit_tunnel', False))}")

    lines.append("")
    lines.append("# --- Journalisation ---")
    lines.append(f"LogLevel {config.get('log_level', 'INFO')}")
    banner = (config.get("banner") or "").strip()
    if banner:
        lines.append(f"Banner {banner}")
        lines.append("# Le fichier de banniere doit exister, sinon sshd refuse de demarrer.")
    if config.get("print_last_log", True):
        lines.append("PrintLastLog yes")

    if config.get("modern_crypto", True):
        lines.append("")
        lines.append("# --- Algorithmes ---")
        lines.append("# Primitives sans faiblesse connue uniquement : ni CBC, ni SHA-1,")
        lines.append("# ni courbes NIST. Des clients tres anciens peuvent ne plus passer.")
        lines.append(f"Ciphers {','.join(MODERN_CIPHERS)}")
        lines.append(f"MACs {','.join(MODERN_MACS)}")
        lines.append(f"KexAlgorithms {','.join(MODERN_KEX)}")

    lines.append("")
    lines.append("# --- Sous-systeme SFTP ---")
    lines.append("Subsystem sftp internal-sftp")

    sftp_group = config.get("sftp_only_group")
    if sftp_group:
        chroot_dir = config.get("sftp_chroot_dir") or "/srv/sftp/%u"
        lines.append("")
        lines.append(f"# --- Depot SFTP : le groupe '{sftp_group}' n'obtient aucun shell ---")
        lines.append("# Le repertoire de chroot doit appartenir a root et n'etre")
        lines.append("# inscriptible que par lui, sinon sshd refuse la connexion.")
        lines.append("# Les blocs Match doivent rester en fin de fichier : tout ce qui suit")
        lines.append("# un Match lui appartient jusqu'au Match suivant ou la fin du fichier.")
        lines.append(f"Match Group {sftp_group}")
        lines.append(f"    ChrootDirectory {chroot_dir}")
        lines.append("    ForceCommand internal-sftp")
        lines.append("    AllowTcpForwarding no")
        lines.append("    AllowAgentForwarding no")
        lines.append("    X11Forwarding no")
        lines.append("    PermitTTY no")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Role serveur (option) : authorized_keys avec restrictions par cle
# --------------------------------------------------------------------------
def generate_authorized_keys(entries):
    """
    Genere un fichier authorized_keys ou chaque cle porte ses propres
    restrictions. C'est le seul endroit ou une limite s'applique a UNE cle :
    sshd_config ne sait raisonner que par utilisateur ou par groupe.
    """
    lines = [
        "# Genere par OpsForge (module ssh).",
        "# A placer dans ~/.ssh/authorized_keys du compte cible (600, proprietaire = ce compte).",
        "",
    ]

    for entry in entries:
        comment = (entry.get("comment") or "").strip()
        if comment:
            lines.append(f"# {comment}")

        options = []
        from_patterns = entry.get("from") or []
        if from_patterns:
            joined = ",".join(str(p) for p in from_patterns)
            options.append(f'from="{joined}"')

        command = (entry.get("command") or "").strip()
        if command:
            options.append(f'command="{command}"')

        # 'restrict' coupe tout (forwarding, TTY, agent...) et rend les
        # options no-* redondantes : on ne les cumule pas.
        if entry.get("restrict"):
            options.append(KEY_RESTRICTIONS["restrict"])
        else:
            for key, flag in KEY_RESTRICTIONS.items():
                if key == "restrict":
                    continue
                if entry.get(key):
                    options.append(flag)

        key = entry["key"].strip()
        lines.append(f"{','.join(options)} {key}" if options else key)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# Point d'entree principal.
# --------------------------------------------------------------------------
def generate_ssh(config):
    """
    Genere le(s) fichier(s) SSH a partir d'une config validee.
    Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)
    role = config.get("role", "client")

    if role == "client":
        return {CLIENT_CONFIG_NAME: generate_client_config(config)}

    files = {SSHD_FRAGMENT_NAME: generate_sshd_config(config)}

    authorized_keys = config.get("authorized_keys") or []
    if authorized_keys:
        files[AUTHORIZED_KEYS_NAME] = generate_authorized_keys(authorized_keys)

    return files


def write_ssh(config, output_dir):
    """Ecrit le(s) fichier(s) genere(s) dans output_dir. Retourne la liste des chemins ecrits."""
    files = generate_ssh(config)
    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        # ~/.ssh/config et authorized_keys sont ignores par OpenSSH s'ils sont
        # lisibles par d'autres comptes : on pose les bonnes permissions des
        # la generation (sans effet sur Windows, ou ce modele n'existe pas).
        if filename in (CLIENT_CONFIG_NAME, AUTHORIZED_KEYS_NAME):
            os.chmod(path, 0o600)
        written.append(path)

    return written
