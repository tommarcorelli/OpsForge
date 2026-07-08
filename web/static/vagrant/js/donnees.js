/* VagrantForge — données de référence (catalogue OS, compat, niveaux, presets).
   Chargé en global (pas de module ES) pour fonctionner aussi en file://. */

/* ── Catalogue d'OS (noms lisibles) ─────────────────────────── */
const CATALOGUE = [
  { famille:'Debian', boxes:[
    { id:'debian/bookworm64', nom:'Debian 12 « Bookworm » — stable (recommandé)' },
    { id:'debian/bullseye64', nom:'Debian 11 « Bullseye » — oldstable' },
    { id:'debian/buster64',   nom:'Debian 10 « Buster » — oldoldstable' },
    { id:'debian/testing64',  nom:'Debian testing « Trixie »' },
  ]},
  { famille:'Ubuntu', boxes:[
    { id:'ubuntu/noble64',  nom:'Ubuntu 24.04 LTS « Noble »' },
    { id:'ubuntu/jammy64',  nom:'Ubuntu 22.04 LTS « Jammy »' },
    { id:'ubuntu/focal64',  nom:'Ubuntu 20.04 LTS « Focal »' },
    { id:'ubuntu/bionic64', nom:'Ubuntu 18.04 LTS « Bionic »' },
  ]},
  { famille:'RHEL-like (Rocky / Alma / CentOS / Oracle)', boxes:[
    { id:'generic/rocky9', nom:'Rocky Linux 9' },
    { id:'generic/rocky8', nom:'Rocky Linux 8' },
    { id:'generic/alma9',  nom:'AlmaLinux 9' },
    { id:'generic/alma8',  nom:'AlmaLinux 8' },
    { id:'generic/oracle9', nom:'Oracle Linux 9' },
    { id:'generic/oracle8', nom:'Oracle Linux 8' },
    { id:'bento/centos-stream-9', nom:'CentOS Stream 9' },
    { id:'bento/centos-stream-8', nom:'CentOS Stream 8' },
  ]},
  { famille:'Fedora', boxes:[
    { id:'generic/fedora39', nom:'Fedora 39' },
    { id:'generic/fedora38', nom:'Fedora 38' },
    { id:'bento/fedora-39',  nom:'Fedora 39 (bento — multi-provider)' },
  ]},
  { famille:'Compatible VMware/Parallels (bento)', boxes:[
    { id:'bento/debian-12',    nom:'Debian 12 (bento — multi-provider)' },
    { id:'bento/debian-11',    nom:'Debian 11 (bento — multi-provider)' },
    { id:'bento/debian-10',    nom:'Debian 10 (bento — multi-provider)' },
    { id:'bento/ubuntu-24.04', nom:'Ubuntu 24.04 (bento — multi-provider)' },
    { id:'bento/ubuntu-22.04', nom:'Ubuntu 22.04 (bento — multi-provider)' },
    { id:'bento/ubuntu-20.04', nom:'Ubuntu 20.04 (bento — multi-provider)' },
  ]},
  { famille:'Autres distributions', boxes:[
    { id:'generic/alpine319', nom:'Alpine Linux 3.19 — ultra-léger' },
    { id:'generic/alpine318', nom:'Alpine Linux 3.18 — ultra-léger' },
    { id:'archlinux/archlinux', nom:'Arch Linux — rolling release' },
    { id:'opensuse/Leap-15.5.x86_64', nom:'openSUSE Leap 15.5' },
    { id:'opensuse/Leap-15.4.x86_64', nom:'openSUSE Leap 15.4' },
    { id:'generic/ubuntu2204', nom:'Ubuntu 22.04 (generic)' },
  ]},
  { famille:'Spécialisées', boxes:[
    { id:'kalilinux/rolling', nom:'Kali Linux — pentest' },
    { id:'generic/freebsd14', nom:'FreeBSD 14 — BSD' },
    { id:'generic/freebsd13', nom:'FreeBSD 13 — BSD' },
  ]},
  { famille:'Windows (WinRM)', boxes:[
    { id:'gusztavvargadr/windows-server', nom:'Windows Server — WinRM' },
    { id:'gusztavvargadr/windows-11',     nom:'Windows 11 — WinRM' },
    { id:'gusztavvargadr/windows-10',     nom:'Windows 10 — WinRM' },
  ]},
];
const NOM_BOX = {};
CATALOGUE.forEach(g => g.boxes.forEach(b => NOM_BOX[b.id] = b.nom));

/* ── Compatibilité box <-> providers (validation) ───────────── */
const BOX_PROVIDERS = {
  'debian/bookworm64':['virtualbox','libvirt','hyperv','qemu'],
  'debian/bullseye64':['virtualbox','libvirt','hyperv','qemu'],
  'debian/buster64':['virtualbox','libvirt','hyperv','qemu'],
  'debian/testing64':['virtualbox','libvirt','hyperv','qemu'],
  'ubuntu/noble64':['virtualbox','libvirt','hyperv'],
  'ubuntu/jammy64':['virtualbox','libvirt','hyperv'],
  'ubuntu/focal64':['virtualbox','libvirt','hyperv'],
  'ubuntu/bionic64':['virtualbox','libvirt','hyperv'],
  'bento/debian-12':['virtualbox','vmware_desktop','parallels'],
  'bento/debian-11':['virtualbox','vmware_desktop','parallels'],
  'bento/debian-10':['virtualbox','vmware_desktop','parallels'],
  'bento/ubuntu-24.04':['virtualbox','vmware_desktop','parallels'],
  'bento/ubuntu-22.04':['virtualbox','vmware_desktop','parallels'],
  'bento/ubuntu-20.04':['virtualbox','vmware_desktop','parallels'],
  'bento/centos-stream-9':['virtualbox','vmware_desktop','parallels'],
  'bento/centos-stream-8':['virtualbox','vmware_desktop','parallels'],
  'bento/fedora-39':['virtualbox','vmware_desktop','parallels'],
  'generic/rocky9':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/rocky8':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/alma9':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/alma8':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/fedora39':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/fedora38':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/oracle9':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/oracle8':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/ubuntu2204':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/freebsd14':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/freebsd13':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/alpine319':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'generic/alpine318':['virtualbox','vmware_desktop','libvirt','hyperv','parallels'],
  'kalilinux/rolling':['virtualbox','vmware_desktop'],
  'archlinux/archlinux':['virtualbox','libvirt','hyperv','vmware_desktop'],
  'opensuse/Leap-15.5.x86_64':['virtualbox','libvirt','hyperv'],
  'opensuse/Leap-15.4.x86_64':['virtualbox','libvirt','hyperv'],
  'gusztavvargadr/windows-10':['virtualbox','hyperv','vmware_desktop'],
  'gusztavvargadr/windows-11':['virtualbox','hyperv','vmware_desktop'],
  'gusztavvargadr/windows-server':['virtualbox','hyperv','vmware_desktop'],
};
function boxSupportsProvider(box, provider){
  const l = BOX_PROVIDERS[box];
  return l ? l.includes(provider) : null;
}

/* ── Niveaux de RAM & CPU ───────────────────────────────────── */
const RAM_NIVEAUX = [
  [512,'512 Mo — minimal'],
  [1024,'1 Go — léger'],
  [2048,'2 Go — confort (recommandé)'],
  [3072,'3 Go'],
  [4096,'4 Go — costaud'],
  [6144,'6 Go'],
  [8192,'8 Go — lourd'],
  [12288,'12 Go'],
  [16384,'16 Go — très lourd'],
  [24576,'24 Go'],
  [32768,'32 Go — poste de dev/build'],
];
const CPU_NIVEAUX = [[1,'1 cœur'],[2,'2 cœurs'],[3,'3 cœurs'],[4,'4 cœurs'],
  [6,'6 cœurs'],[8,'8 cœurs'],[12,'12 cœurs'],[16,'16 cœurs']];

/* ── Langues (locale + clavier) ─────────────────────────────── */
const LOCALES = [
  ['', '', 'Ne pas changer (défaut de la box)'],
  ['fr_FR.UTF-8','fr','Français — clavier AZERTY (fr)'],
  ['en_US.UTF-8','us','Anglais US — clavier QWERTY (us)'],
  ['en_GB.UTF-8','gb','Anglais UK'],
  ['es_ES.UTF-8','es','Espagnol'],
  ['de_DE.UTF-8','de','Allemand'],
  ['it_IT.UTF-8','it','Italien'],
  ['pt_BR.UTF-8','br','Portugais (Brésil)'],
];

/* ── Bibliothèque de commandes shell (aide provisioning) ────── */
const SNIPPETS = [
  ['Système', [
    ['MàJ complète du système', 'apt-get update -y && apt-get upgrade -y\n'],
    ['Outils de base (git, curl, vim…)', 'apt-get install -y curl wget git vim htop unzip ca-certificates\n'],
    ['Fuseau horaire Paris', 'timedatectl set-timezone Europe/Paris\n'],
    ['Fichier swap 2 Go', 'fallocate -l 2G /swapfile\nchmod 600 /swapfile\nmkswap /swapfile\nswapon /swapfile\necho "/swapfile none swap sw 0 0" >> /etc/fstab\n'],
    ['Nettoyage cache apt', 'apt-get autoremove -y && apt-get clean\n'],
  ]],
  ['Serveurs web & proxy', [
    ['Nginx', 'apt-get install -y nginx\nsystemctl enable --now nginx\n'],
    ['Apache', 'apt-get install -y apache2\nsystemctl enable --now apache2\n'],
    ['Caddy (HTTPS auto)', 'apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl\ncurl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/gpg.key" | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg\ncurl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt" > /etc/apt/sources.list.d/caddy-stable.list\napt-get update -y && apt-get install -y caddy\n'],
    ['Traefik (binaire)', 'curl -L https://github.com/traefik/traefik/releases/latest/download/traefik_v2.11.0_linux_amd64.tar.gz -o /tmp/traefik.tar.gz\ntar -xzf /tmp/traefik.tar.gz -C /usr/local/bin traefik\n'],
    ['Certbot (Let\'s Encrypt)', 'apt-get install -y certbot python3-certbot-nginx\n# certbot --nginx -d mondomaine.fr\n'],
  ]],
  ['Bases de données', [
    ['MariaDB', 'apt-get install -y mariadb-server\nsystemctl enable --now mariadb\n'],
    ['PostgreSQL', 'apt-get install -y postgresql\nsystemctl enable --now postgresql\n'],
    ['Redis', 'apt-get install -y redis-server\nsystemctl enable --now redis-server\n'],
    ['MongoDB', 'apt-get install -y gnupg curl\ncurl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb.gpg\necho "deb [signed-by=/usr/share/keyrings/mongodb.gpg] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main" > /etc/apt/sources.list.d/mongodb-org-7.0.list\napt-get update -y && apt-get install -y mongodb-org\nsystemctl enable --now mongod\n'],
  ]],
  ['Conteneurs & orchestration', [
    ['Docker + Compose', 'curl -fsSL https://get.docker.com | sh\nusermod -aG docker vagrant\n'],
    ['kubectl', 'curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"\ninstall -o root -g root -m 0755 kubectl /usr/local/bin/kubectl\n'],
    ['Helm', 'curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash\n'],
    ['Minikube', 'curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64\ninstall minikube-linux-amd64 /usr/local/bin/minikube\n'],
  ]],
  ['Langages & outils de build', [
    ['Node.js (LTS)', 'curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -\napt-get install -y nodejs\n'],
    ['Python 3 + pip + venv', 'apt-get install -y python3 python3-pip python3-venv\n'],
    ['Go (langage)', 'curl -L https://go.dev/dl/go1.22.0.linux-amd64.tar.gz -o /tmp/go.tar.gz\ntar -C /usr/local -xzf /tmp/go.tar.gz\necho \'export PATH=$PATH:/usr/local/go/bin\' >> /etc/profile.d/go.sh\n'],
    ['Rust', 'curl --proto \'=https\' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y\n'],
    ['PHP + extensions courantes', 'apt-get install -y php php-cli php-mbstring php-xml php-curl php-mysql\n'],
    ['OpenJDK 21', 'apt-get install -y openjdk-21-jdk\n'],
    ['Ansible', 'apt-get install -y ansible\n'],
    ['Terraform', 'apt-get install -y gnupg software-properties-common curl\ncurl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg\necho "deb [signed-by=/usr/share/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" > /etc/apt/sources.list.d/hashicorp.list\napt-get update -y && apt-get install -y terraform\n'],
  ]],
  ['Files de messages', [
    ['RabbitMQ', 'apt-get install -y rabbitmq-server\nsystemctl enable --now rabbitmq-server\n'],
  ]],
  ['Réseau & VPN', [
    ['WireGuard', 'apt-get install -y wireguard\n'],
    ['OpenVPN', 'apt-get install -y openvpn easy-rsa\n'],
    ['Serveur DNS Bind9', 'apt-get install -y bind9 bind9utils\nsystemctl enable --now bind9\n'],
  ]],
  ['Supervision & logs', [
    ['Node Exporter (Prometheus)', 'apt-get install -y prometheus-node-exporter\nsystemctl enable --now prometheus-node-exporter\n'],
    ['Filebeat', 'apt-get install -y apt-transport-https\ncurl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elastic.gpg\necho "deb [signed-by=/usr/share/keyrings/elastic.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main" > /etc/apt/sources.list.d/elastic-8.x.list\napt-get update -y && apt-get install -y filebeat\n'],
    ['rsyslog vers serveur distant', 'echo "*.* @@LOG_SERVER_IP:514" >> /etc/rsyslog.conf\nsystemctl restart rsyslog\n'],
  ]],
  ['Sauvegarde', [
    ['rsync', 'apt-get install -y rsync\n'],
    ['restic (sauvegarde chiffrée)', 'apt-get install -y restic\n'],
    ['Cron de sauvegarde quotidienne', 'echo "0 3 * * * root tar czf /backup/$(date +\\%F).tar.gz /var/www" > /etc/cron.d/backup-quotidien\n'],
  ]],
  ['Sécurité', [
    ['Pare-feu UFW (SSH ouvert)', 'apt-get install -y ufw\nufw allow OpenSSH\nufw --force enable\n'],
    ['fail2ban', 'apt-get install -y fail2ban\nsystemctl enable --now fail2ban\n'],
    ['Utilisateur sudo « devops »', "useradd -m -s /bin/bash devops\necho 'devops ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/devops\n"],
    ['Désactiver la connexion SSH root', "sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config\nsystemctl restart sshd\n"],
    ['Mises à jour de sécurité automatiques', 'apt-get install -y unattended-upgrades\ndpkg-reconfigure -f noninteractive unattended-upgrades\n'],
  ]],
];

/* ── Presets ────────────────────────────────────────────────── */
function _vmp(nom, box, memory, cpus, sr, ip, ports, script, extra){
  return Object.assign({name:nom, box, memory, cpus, ip: ip?sr+'.'+ip:'',
    syncedFolder:'./'+nom, ports:ports||[],
    provisionType: script?'shell':'none', provisionScript: script||''}, extra||{});
}
const PRESETS = {
  solo: {t:'VM unique', d:'Une Debian 12 minimale pour bidouiller.', build:sr=>[
    _vmp('box','debian/bookworm64',1024,1,sr,10,[], 'apt-get update -y\n')]},
  k3s: {t:'Cluster K3s', d:'1 master + 2 workers Kubernetes léger.', build:sr=>[
    _vmp('k3s-master','debian/bookworm64',2048,2,sr,10,[], 'apt-get update -y\ncurl -sfL https://get.k3s.io | sh -\ncat /var/lib/rancher/k3s/server/node-token\n'),
    _vmp('k3s-worker1','debian/bookworm64',1536,1,sr,11,[], 'apt-get update -y\n# Rejoindre : K3S_URL=https://'+sr+'.10:6443 K3S_TOKEN=<token> curl -sfL https://get.k3s.io | sh -\n'),
    _vmp('k3s-worker2','debian/bookworm64',1536,1,sr,12,[], 'apt-get update -y\n# Rejoindre : K3S_URL=https://'+sr+'.10:6443 K3S_TOKEN=<token> curl -sfL https://get.k3s.io | sh -\n')]},
  lamp: {t:'LAMP + pfSense', d:'Serveur web/PHP/MySQL derrière un pare-feu.', build:sr=>[
    _vmp('pfsense','generic/freebsd14',1024,1,sr,1,[], '# pfSense : configuration via console/web GUI\n'),
    _vmp('lamp','debian/bookworm64',1024,1,sr,20,[{guest:80,host:8080}], 'apt-get update -y\napt-get install -y apache2 mariadb-server php libapache2-mod-php php-mysql\nsystemctl enable --now apache2 mariadb\n')]},
  devsecops: {t:'DevSecOps CI/CD', d:'GitLab + SonarQube + Vault/monitoring.', build:sr=>[
    _vmp('gitlab-ci','debian/bookworm64',2048,2,sr,30,[{guest:80,host:8090}], 'apt-get update -y\n# Runner GitLab CI à configurer\n'),
    _vmp('sonarqube','debian/bookworm64',2048,2,sr,31,[{guest:9000,host:9000}], 'apt-get update -y\nsysctl -w vm.max_map_count=524288\n'),
    _vmp('vault-monitoring','debian/bookworm64',1536,1,sr,32,[{guest:8200,host:8200},{guest:3000,host:3000}], 'apt-get update -y\n# Vault + Grafana/Prometheus\n')]},
  pentest: {t:'Lab pentest', d:'Kali attaquant + cible vulnérable isolée.', build:sr=>[
    _vmp('kali','kalilinux/rolling',3072,2,sr,5,[], 'apt-get update -y\n# Kali déjà outillée\n', {locale:'fr_FR.UTF-8',keymap:'fr'}),
    _vmp('cible','debian/bookworm64',1024,1,sr,6,[{guest:80,host:8081}], 'apt-get update -y\n# ATTENTION : volontairement faible, réseau privé UNIQUEMENT\napt-get install -y apache2 vsftpd\n', {rootPassword:'toor'})]},
  monitoring: {t:'Monitoring', d:'Prometheus + Grafana + Node Exporter.', build:sr=>[
    _vmp('prometheus','debian/bookworm64',1024,1,sr,40,[{guest:9090,host:9090}], 'apt-get update -y\napt-get install -y prometheus prometheus-node-exporter\nsystemctl enable --now prometheus prometheus-node-exporter\n'),
    _vmp('grafana','debian/bookworm64',1024,1,sr,41,[{guest:3000,host:3000}], "apt-get update -y\napt-get install -y apt-transport-https software-properties-common wget\nwget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key\necho 'deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main' > /etc/apt/sources.list.d/grafana.list\napt-get update -y && apt-get install -y grafana\nsystemctl enable --now grafana-server\n# Source de données Prometheus : http://"+sr+".40:9090\n")]},
  elk: {t:'ELK Stack', d:'Elasticsearch + Kibana pour centraliser des logs.', build:sr=>[
    _vmp('elasticsearch','debian/bookworm64',2560,2,sr,50,[{guest:9200,host:9200}], "apt-get update -y\napt-get install -y apt-transport-https gnupg\nwget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elastic.gpg\necho 'deb [signed-by=/usr/share/keyrings/elastic.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main' > /etc/apt/sources.list.d/elastic-8.x.list\napt-get update -y && apt-get install -y elasticsearch\necho 'discovery.type: single-node' >> /etc/elasticsearch/elasticsearch.yml\necho 'xpack.security.enabled: false' >> /etc/elasticsearch/elasticsearch.yml\nsystemctl enable --now elasticsearch\n"),
    _vmp('kibana','debian/bookworm64',1536,1,sr,51,[{guest:5601,host:5601}], "apt-get update -y\napt-get install -y apt-transport-https gnupg\nwget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elastic.gpg\necho 'deb [signed-by=/usr/share/keyrings/elastic.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main' > /etc/apt/sources.list.d/elastic-8.x.list\napt-get update -y && apt-get install -y kibana\nsed -i 's/#server.host: \"localhost\"/server.host: \"0.0.0.0\"/' /etc/kibana/kibana.yml\necho 'elasticsearch.hosts: [\"http://"+sr+".50:9200\"]' >> /etc/kibana/kibana.yml\nsystemctl enable --now kibana\n")]},
  wordpress: {t:'WordPress', d:'WordPress + MariaDB sur une VM, pour prototyper vite.', build:sr=>[
    _vmp('wordpress','debian/bookworm64',1536,1,sr,60,[{guest:80,host:8082}], "apt-get update -y\napt-get install -y apache2 mariadb-server php php-mysql php-curl php-gd php-mbstring php-xml php-zip\nsystemctl enable --now apache2 mariadb\nmysql -e \"CREATE DATABASE wordpress; CREATE USER 'wp'@'localhost' IDENTIFIED BY 'wp';\nGRANT ALL PRIVILEGES ON wordpress.* TO 'wp'@'localhost'; FLUSH PRIVILEGES;\"\ncd /tmp && wget -q https://wordpress.org/latest.tar.gz && tar xzf latest.tar.gz\ncp -r wordpress/* /var/www/html/ && chown -R www-data:www-data /var/www/html\n# wp-config.php à compléter à la première connexion (DB : wordpress/wp/wp)\n")]},
  'gitlab-runner': {t:'GitLab Runner', d:'Runner CI + Docker, pour exécuter des pipelines hors SaaS.', build:sr=>[
    _vmp('gitlab-runner','debian/bookworm64',2048,2,sr,70,[], 'apt-get update -y\napt-get install -y curl ca-certificates\ncurl -fsSL https://get.docker.com | sh\ncurl -L "https://gitlab-runner-downloads.s3.amazonaws.com/latest/deb/gitlab-runner_amd64.deb" -o /tmp/gitlab-runner.deb\ndpkg -i /tmp/gitlab-runner.deb\n# Enregistrement : gitlab-runner register --url <url_gitlab> --registration-token <token>\n')]},
  nextcloud: {t:'Nextcloud', d:'Cloud personnel (stockage/partage) + MariaDB.', build:sr=>[
    _vmp('nextcloud','debian/bookworm64',2048,2,sr,80,[{guest:443,host:8443},{guest:80,host:8083}], "apt-get update -y\napt-get install -y apache2 mariadb-server php libapache2-mod-php php-mysql php-gd php-curl php-mbstring php-xml php-zip php-intl\nsystemctl enable --now apache2 mariadb\nmysql -e \"CREATE DATABASE nextcloud; CREATE USER 'nc'@'localhost' IDENTIFIED BY 'nc';\nGRANT ALL PRIVILEGES ON nextcloud.* TO 'nc'@'localhost'; FLUSH PRIVILEGES;\"\ncd /tmp && wget -q https://download.nextcloud.com/server/releases/latest.zip\napt-get install -y unzip && unzip -q latest.zip -d /var/www/\nchown -R www-data:www-data /var/www/nextcloud\n")]},
};
