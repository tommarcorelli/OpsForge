"""
desktop.py
----------
Lance OpsForge comme application desktop : demarre le serveur Flask en
arriere-plan (thread) et ouvre une fenetre native (pywebview) dessus.
Zero terminal a garder ouvert, zero navigateur a lancer a la main.

Usage en dev :
    pip install -r requirements-desktop.txt
    python desktop.py

Une fois empaquete (voir opsforge.spec, `pyinstaller opsforge.spec`) :
    dist/OpsForge/OpsForge.exe
"""

import os
import socket
import sys
import threading
import time

import webview

from app import app

DEFAULT_PORT = int(os.environ.get("PORT", 5050))


def _port_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _trouver_port(depart):
    """Cherche un port libre a partir de `depart` : si l'utilisateur a deja
    `python app.py` ouvert sur 5050, le desktop n'ecrase pas ce serveur."""
    port = depart
    while not _port_libre(port):
        port += 1
    return port


def _demarrer_flask(port):
    # use_reloader=False : le reloader Werkzeug redemarre le process via un
    # sous-processus, incompatible avec un executable PyInstaller gele (et
    # inutile ici, l'app desktop ne recharge pas le code a chaud).
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def _attendre_serveur(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


def main():
    port = _trouver_port(DEFAULT_PORT)

    thread = threading.Thread(target=_demarrer_flask, args=(port,), daemon=True)
    thread.start()

    if not _attendre_serveur(port):
        print("Erreur : le serveur local n'a pas demarre a temps.", file=sys.stderr)
        sys.exit(1)

    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "web", "static", "favicon.ico")

    webview.create_window(
        "OpsForge",
        f"http://127.0.0.1:{port}",
        width=1440,
        height=900,
        min_size=(1024, 700),
        background_color="#0b0d14",
    )
    webview.start(icon=icon_path if os.path.isfile(icon_path) else None)


if __name__ == "__main__":
    main()
