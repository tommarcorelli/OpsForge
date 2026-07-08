"""
app.py
------
OpsForge — application web locale (Flask) reunissant deux modules :

  - CI/CD  (/cicd)    : generation de pipelines GitHub Actions / GitLab CI
  - Ansible (/ansible): generation de playbooks de provisioning + deploiement

La page d'accueil (/) est un hub qui renvoie vers les deux modules.
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

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

app.register_blueprint(cicd_bp)
app.register_blueprint(ansible_bp)


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
    print(f"OpsForge disponible sur : http://127.0.0.1:{port}")
    app.run(debug=True, port=port)
