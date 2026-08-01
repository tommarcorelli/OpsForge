"""
app.py
------
OpsForge — application web locale (Flask) reunissant plusieurs modules :

  - CI/CD     (/cicd)      : pipelines GitHub Actions / GitLab CI
  - Ansible   (/ansible)   : playbooks de provisioning + deploiement
  - Vagrant   (/vagrant)   : Vagrantfile multi-VM (portage de VagrantForge)
  - Terraform (/terraform) : main.tf (v0, a enrichir)
  - Packer    (/packer)    : build.pkr.hcl (image VM/AMI/conteneur)

La page d'accueil (/) est un hub qui renvoie vers les modules.
Tout tourne 100% en local, rien n'est envoye sur un serveur externe.

Lancement :
    pip install -r requirements.txt --break-system-packages
    python app.py
Puis ouvre http://127.0.0.1:5050
"""

import os
import sys

from flask import Flask, render_template, send_from_directory

from modules.ansible.routes import bp as ansible_bp
from modules.backup.routes import bp as backup_bp
from modules.cicd.routes import bp as cicd_bp
from modules.cloudinit.routes import bp as cloudinit_bp
from modules.dockerfile.routes import bp as dockerfile_bp
from modules.firewall.routes import bp as firewall_bp
from modules.gitops.routes import bp as gitops_bp
from modules.k8s.routes import bp as k8s_bp
from modules.monitoring.routes import bp as monitoring_bp
from modules.nginx.routes import bp as nginx_bp
from modules.packer.routes import bp as packer_bp
from modules.systemd.routes import bp as systemd_bp
from modules.terraform.routes import bp as terraform_bp
from modules.vagrant.routes import bp as vagrant_bp
from modules.vault.routes import bp as vault_bp

# Chemin de base des templates/static : en dev c'est le dossier de ce fichier,
# mais une fois empaquete par PyInstaller (voir desktop.py / opsforge.spec),
# les fichiers de donnees sont extraits sous sys._MEIPASS et non plus a cote
# du script. Sans ca, Flask ne retrouve pas web/templates et web/static dans
# l'executable (root_path se resout via l'introspection du module, qui ne
# fonctionne pas de la meme facon dans un bundle gele).
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "web", "templates"),
    static_folder=os.path.join(BASE_DIR, "web", "static"),
)

app.register_blueprint(cicd_bp)
app.register_blueprint(ansible_bp)
app.register_blueprint(vagrant_bp)
app.register_blueprint(terraform_bp)
app.register_blueprint(dockerfile_bp)
app.register_blueprint(k8s_bp)
app.register_blueprint(nginx_bp)
app.register_blueprint(systemd_bp)
app.register_blueprint(monitoring_bp)
app.register_blueprint(cloudinit_bp)
app.register_blueprint(packer_bp)
app.register_blueprint(vault_bp)
app.register_blueprint(gitops_bp)
app.register_blueprint(backup_bp)
app.register_blueprint(firewall_bp)


@app.route("/")
def hub():
    """Page d'accueil : choix du module (CI/CD ou Ansible)."""
    return render_template("hub.html")


@app.route("/service-worker.js")
def service_worker():
    """
    Sert le service worker a la racine (et non sous /static/) pour que
    son scope couvre toute l'application, pas seulement /static/.
    """
    response = send_from_directory(app.static_folder, "service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Content-Type"] = "application/javascript"
    return response


if __name__ == "__main__":
    # Port configurable via variable d'environnement : PORT=8080 python app.py
    port = int(os.environ.get("PORT", "5050"))
    # Debug desactive par defaut : le debugger Werkzeug expose une console
    # Python interactive (RCE potentielle). Active uniquement en dev explicite :
    # FLASK_DEBUG=1 python app.py
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"OpsForge disponible sur : http://127.0.0.1:{port}")
    app.run(debug=debug, port=port)
