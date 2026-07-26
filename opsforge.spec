# -*- mode: python ; coding: utf-8 -*-
# Empaquette OpsForge en un executable desktop unique (Windows) :
# Flask (app.py) lance en arriere-plan + fenetre native pywebview (desktop.py).
#
# Usage :
#   pip install -r requirements-desktop.txt
#   pyinstaller opsforge.spec
#   -> dist/OpsForge.exe
#
# ansible-core est volontairement exclu du bundle : le module Ansible ne
# l'importe que paresseusement, pour le chiffrement Vault (deja indisponible
# sous Windows natif faute de `fcntl`, voir README). L'inclure alourdirait
# et fragiliserait l'empaquetage (des centaines de plugins internes) pour une
# fonctionnalite deja gracieusement desactivee sur cette plateforme.

datas = [
    ("web/templates", "web/templates"),
    ("web/static", "web/static"),
    ("modules/cicd/templates", "modules/cicd/templates"),
    ("modules/ansible/templates", "modules/ansible/templates"),
    ("modules/dockerfile/templates", "modules/dockerfile/templates"),
    ("modules/k8s/templates", "modules/k8s/templates"),
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["ansible", "ansible_core", "pytest", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OpsForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="web/static/favicon.ico",
)
