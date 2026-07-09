"""
app.py
------
OpsForge — application web locale (Flask) reunissant plusieurs modules :

  - CI/CD     (/cicd)      : pipelines GitHub Actions / GitLab CI
  - Ansible   (/ansible)   : playbooks de provisioning + deploiement
  - Vagrant   (/vagrant)   : Vagrantfile multi-VM (portage de VagrantForge)
  - Terraform (/terraform) : main.tf (v0, a enrichir)

La page d'accueil (/) est un hub qui renvoie vers les modules.
Tout tourne 100% en local, rien n'est envoye sur un serveur externe.

Lancement :
    pip install -r requirements.txt --break-system-packages
    python app.py
Puis ouvre http://127.0.0.1:5050
"""

import os

from flask import Flask, render_template, send_from_directory

from modules.cicd.routes import bp as cicd_bp
from modules.ansible.routes import bp as ansible_bp
from modules.vagrant.routes import bp as vagrant_bp
from modules.terraform.routes import bp as terraform_bp
from modules.dockerfile.routes import bp as dockerfile_bp

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

app.register_blueprint(cicd_bp)
app.register_blueprint(ansible_bp)
app.register_blueprint(vagrant_bp)
app.register_blueprint(terraform_bp)
app.register_blueprint(dockerfile_bp)


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
    port = int(os.environ.get("PORT", 5050))
    # Debug desactive par defaut : le debugger Werkzeug expose une console
    # Python interactive (RCE potentielle). Active uniquement en dev explicite :
    # FLASK_DEBUG=1 python app.py
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"OpsForge disponible sur : http://127.0.0.1:{port}")
    app.run(debug=debug, port=port)
