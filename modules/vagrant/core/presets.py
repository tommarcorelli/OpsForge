"""VagrantForge — presets de labs prêts à l'emploi.

Chaque preset est une fonction qui prend le sous-réseau de base et retourne une
config complète. Le frontend web et la CLI partagent exactement ces définitions.
"""


def _vm(nom, box, memoire, cpus, sous_reseau, suffixe_ip, ports=None, script="", **extra):
    vm = {
        "name": nom,
        "box": box,
        "memory": memoire,
        "cpus": cpus,
        "ip": f"{sous_reseau}.{suffixe_ip}" if suffixe_ip else "",
        "synced_folder": f"./{nom}",
        "ports": ports or [],
        "provision": {"type": "shell", "script": script} if script else {"type": "none"},
    }
    vm.update(extra)
    return vm


def preset_k3s(sr="192.168.56"):
    """Cluster K3s : 1 master + 2 workers (Debian)."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("k3s-master", "debian/bookworm64", 2048, 2, sr, 10,
                script="apt-get update -y\ncurl -sfL https://get.k3s.io | sh -\n"
                       "cat /var/lib/rancher/k3s/server/node-token  # token pour joindre les workers\n"),
            _vm("k3s-worker1", "debian/bookworm64", 1536, 1, sr, 11,
                script="apt-get update -y\n"
                       "# Rejoindre : curl -sfL https://get.k3s.io | K3S_URL=https://" + sr + ".10:6443 K3S_TOKEN=<token> sh -\n"),
            _vm("k3s-worker2", "debian/bookworm64", 1536, 1, sr, 12,
                script="apt-get update -y\n"
                       "# Rejoindre : curl -sfL https://get.k3s.io | K3S_URL=https://" + sr + ".10:6443 K3S_TOKEN=<token> sh -\n"),
        ],
    }


def preset_lamp(sr="192.168.56"):
    """Stack LAMP derrière un pare-feu pfSense."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("pfsense", "generic/freebsd14", 1024, 1, sr, 1,
                script="# pfSense : configuration via console/web GUI, pas de shell classique\n"),
            _vm("lamp-server", "debian/bookworm64", 1024, 1, sr, 20,
                ports=[{"guest": 80, "host": 8080}],
                script="apt-get update -y\n"
                       "apt-get install -y apache2 mariadb-server php libapache2-mod-php php-mysql\n"
                       "systemctl enable --now apache2 mariadb\n"),
        ],
    }


def preset_devsecops(sr="192.168.56"):
    """Chaîne CI/CD DevSecOps : GitLab + SonarQube + Vault/monitoring."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("gitlab-ci", "debian/bookworm64", 2048, 2, sr, 30,
                ports=[{"guest": 80, "host": 8090}],
                script="apt-get update -y\n# Runner GitLab CI + configuration à ajouter ici\n"),
            _vm("sonarqube", "debian/bookworm64", 2048, 2, sr, 31,
                ports=[{"guest": 9000, "host": 9000}],
                script="apt-get update -y\n"
                       "# SonarQube exige un vm.max_map_count élevé\nsysctl -w vm.max_map_count=524288\n"),
            _vm("vault-monitoring", "debian/bookworm64", 1536, 1, sr, 32,
                ports=[{"guest": 8200, "host": 8200}, {"guest": 3000, "host": 3000}],
                script="apt-get update -y\n# HashiCorp Vault + Grafana/Prometheus à installer ici\n"),
        ],
    }


def preset_pentest(sr="192.168.56"):
    """Lab de pentest : Kali attaquant + cible Debian volontairement vulnérable."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("kali", "kalilinux/rolling", 3072, 2, sr, 5,
                script="apt-get update -y\n# Kali arrive déjà outillée ; ajoute tes outils ici\n",
                locale="fr_FR.UTF-8", keymap="fr"),
            _vm("cible", "debian/bookworm64", 1024, 1, sr, 6,
                ports=[{"guest": 80, "host": 8081}],
                script="apt-get update -y\n"
                       "# ATTENTION : machine volontairement faible, réseau privé UNIQUEMENT\n"
                       "apt-get install -y apache2 vsftpd\n",
                root_password="toor"),
        ],
    }


def preset_solo(sr="192.168.56"):
    """VM Debian unique, minimale, pour bidouiller vite fait."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("box", "debian/bookworm64", 1024, 1, sr, 10,
                script="apt-get update -y\n"),
        ],
    }


def preset_monitoring(sr="192.168.56"):
    """Stack de supervision : Prometheus + Grafana + Node Exporter."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("prometheus", "debian/bookworm64", 1024, 1, sr, 40,
                ports=[{"guest": 9090, "host": 9090}],
                script="apt-get update -y\n"
                       "apt-get install -y prometheus prometheus-node-exporter\n"
                       "systemctl enable --now prometheus prometheus-node-exporter\n"),
            _vm("grafana", "debian/bookworm64", 1024, 1, sr, 41,
                ports=[{"guest": 3000, "host": 3000}],
                script="apt-get update -y\n"
                       "apt-get install -y apt-transport-https software-properties-common wget\n"
                       "wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key\n"
                       "echo 'deb [signed-by=/usr/share/keyrings/grafana.key] "
                       "https://apt.grafana.com stable main' > /etc/apt/sources.list.d/grafana.list\n"
                       "apt-get update -y && apt-get install -y grafana\n"
                       "systemctl enable --now grafana-server\n"
                       "# Source de données Prometheus à ajouter dans Grafana : http://" + sr + ".40:9090\n"),
        ],
    }


def preset_elk(sr="192.168.56"):
    """Stack de logs : Elasticsearch + Logstash + Kibana."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("elasticsearch", "debian/bookworm64", 2560, 2, sr, 50,
                ports=[{"guest": 9200, "host": 9200}],
                script="apt-get update -y\n"
                       "apt-get install -y apt-transport-https gnupg\n"
                       "wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor "
                       "-o /usr/share/keyrings/elastic.gpg\n"
                       "echo 'deb [signed-by=/usr/share/keyrings/elastic.gpg] "
                       "https://artifacts.elastic.co/packages/8.x/apt stable main' "
                       "> /etc/apt/sources.list.d/elastic-8.x.list\n"
                       "apt-get update -y && apt-get install -y elasticsearch\n"
                       "echo 'discovery.type: single-node' >> /etc/elasticsearch/elasticsearch.yml\n"
                       "echo 'xpack.security.enabled: false'  >> /etc/elasticsearch/elasticsearch.yml\n"
                       "systemctl enable --now elasticsearch\n"),
            _vm("kibana", "debian/bookworm64", 1536, 1, sr, 51,
                ports=[{"guest": 5601, "host": 5601}],
                script="apt-get update -y\n"
                       "apt-get install -y apt-transport-https gnupg\n"
                       "wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor "
                       "-o /usr/share/keyrings/elastic.gpg\n"
                       "echo 'deb [signed-by=/usr/share/keyrings/elastic.gpg] "
                       "https://artifacts.elastic.co/packages/8.x/apt stable main' "
                       "> /etc/apt/sources.list.d/elastic-8.x.list\n"
                       "apt-get update -y && apt-get install -y kibana\n"
                       "sed -i 's/#server.host: \"localhost\"/server.host: \"0.0.0.0\"/' "
                       "/etc/kibana/kibana.yml\n"
                       "echo 'elasticsearch.hosts: [\"http://" + sr + ".50:9200\"]' "
                       ">> /etc/kibana/kibana.yml\n"
                       "systemctl enable --now kibana\n"),
        ],
    }


def preset_wordpress(sr="192.168.56"):
    """WordPress + MariaDB sur une seule VM, pour prototyper vite."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("wordpress", "debian/bookworm64", 1536, 1, sr, 60,
                ports=[{"guest": 80, "host": 8082}],
                script="apt-get update -y\n"
                       "apt-get install -y apache2 mariadb-server php php-mysql php-curl php-gd "
                       "php-mbstring php-xml php-zip\n"
                       "systemctl enable --now apache2 mariadb\n"
                       "mysql -e \"CREATE DATABASE wordpress; "
                       "CREATE USER 'wp'@'localhost' IDENTIFIED BY 'wp';\n"
                       "GRANT ALL PRIVILEGES ON wordpress.* TO 'wp'@'localhost'; FLUSH PRIVILEGES;\"\n"
                       "cd /tmp && wget -q https://wordpress.org/latest.tar.gz && tar xzf latest.tar.gz\n"
                       "cp -r wordpress/* /var/www/html/ && chown -R www-data:www-data /var/www/html\n"
                       "# wp-config.php à compléter à la première connexion (DB : wordpress/wp/wp)\n"),
        ],
    }


def preset_gitlab_runner(sr="192.168.56"):
    """GitLab Runner + Docker, pour exécuter des pipelines CI en dehors du SaaS GitLab."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("gitlab-runner", "debian/bookworm64", 2048, 2, sr, 70,
                script="apt-get update -y\n"
                       "apt-get install -y curl ca-certificates\n"
                       "curl -fsSL https://get.docker.com | sh\n"
                       "curl -L \"https://gitlab-runner-downloads.s3.amazonaws.com/latest/deb/"
                       "gitlab-runner_amd64.deb\" -o /tmp/gitlab-runner.deb\n"
                       "dpkg -i /tmp/gitlab-runner.deb\n"
                       "# Enregistrement : gitlab-runner register "
                       "--url <url_gitlab> --registration-token <token>\n"),
        ],
    }


def preset_nextcloud(sr="192.168.56"):
    """Nextcloud (stockage/cloud perso) + MariaDB."""
    return {
        "provider": "virtualbox",
        "box_check_update": False,
        "vms": [
            _vm("nextcloud", "debian/bookworm64", 2048, 2, sr, 80,
                ports=[{"guest": 443, "host": 8443}, {"guest": 80, "host": 8083}],
                script="apt-get update -y\n"
                       "apt-get install -y apache2 mariadb-server php libapache2-mod-php "
                       "php-mysql php-gd php-curl php-mbstring php-xml php-zip php-intl\n"
                       "systemctl enable --now apache2 mariadb\n"
                       "mysql -e \"CREATE DATABASE nextcloud; "
                       "CREATE USER 'nc'@'localhost' IDENTIFIED BY 'nc';\n"
                       "GRANT ALL PRIVILEGES ON nextcloud.* TO 'nc'@'localhost'; FLUSH PRIVILEGES;\"\n"
                       "cd /tmp && wget -q https://download.nextcloud.com/server/releases/latest.zip\n"
                       "apt-get install -y unzip && unzip -q latest.zip -d /var/www/\n"
                       "chown -R www-data:www-data /var/www/nextcloud\n"),
        ],
    }


PRESETS = {
    "solo":           ("VM Debian unique", preset_solo),
    "k3s":            ("Cluster K3s (3 VMs)", preset_k3s),
    "lamp":           ("LAMP + pfSense", preset_lamp),
    "devsecops":      ("Chaîne CI/CD DevSecOps", preset_devsecops),
    "pentest":        ("Lab pentest Kali + cible", preset_pentest),
    "monitoring":     ("Prometheus + Grafana", preset_monitoring),
    "elk":            ("Elasticsearch + Kibana", preset_elk),
    "wordpress":      ("WordPress + MariaDB", preset_wordpress),
    "gitlab-runner":  ("GitLab Runner + Docker", preset_gitlab_runner),
    "nextcloud":      ("Nextcloud + MariaDB", preset_nextcloud),
}


def obtenir_preset(nom, sous_reseau="192.168.56"):
    """Retourne la config d'un preset par son nom, ou lève KeyError."""
    if nom not in PRESETS:
        raise KeyError(nom)
    return PRESETS[nom][1](sous_reseau)
