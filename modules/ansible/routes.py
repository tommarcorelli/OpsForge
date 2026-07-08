"""
modules/ansible/routes.py
-------------------------
Blueprint Flask du module Ansible (monte sous /ansible).
"""

import io
import zipfile

from flask import Blueprint, render_template, request, jsonify, send_file

from modules.ansible.core import (
    generate_playbook,
    generate_inventory,
    generate_vault_file,
    generate_role_based_project,
    generate_multi_group_roles_project,
    generate_multi_group_inventory,
    SUPPORTED_LANGUAGES,
)

bp = Blueprint("ansible", __name__, url_prefix="/ansible")


def _config_from_payload(data):
    """Construit le dict de config attendu par le core a partir du JSON recu."""
    vault_vars = data.get("vault_vars") or {}
    return {
        "hosts_group": data.get("hosts_group") or "webservers",
        "provisioning": data.get("provisioning") or [],
        "runtime_language": data.get("language"),
        "runtime_version": data.get("runtime_version"),
        "deployment": data.get("deployment") or [],
        "deployment_language": data.get("language"),
        "repo_url": data.get("repo_url", ""),
        "branch": data.get("branch") or "main",
        "app_dir": data.get("app_dir") or "/opt/mon-application",
        "service_name": data.get("service_name") or "mon-application",
        "build_cmd": data.get("build_cmd") or "echo 'Aucune commande de build definie'",
        "vault_vars": vault_vars or None,
        "health_check_port": data.get("health_check_port"),
        "domain_name": data.get("domain_name"),
        "letsencrypt_email": data.get("letsencrypt_email"),
        "database_engine": data.get("database_engine"),
        "db_name": data.get("db_name"),
        "db_user": data.get("db_user"),
        "notify_webhook_url": data.get("notify_webhook_url"),
    }, vault_vars


@bp.route("/")
def index():
    return render_template("ansible.html", languages=SUPPORTED_LANGUAGES)


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Mode 'flat' : un seul playbook.yml."""
    data = request.get_json(force=True) or {}
    config, vault_vars = _config_from_payload(data)

    try:
        yaml_text = generate_playbook(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    result = {"playbook": yaml_text}

    if vault_vars:
        vault_password = data.get("vault_password")
        if not vault_password:
            return jsonify({"error": "Un mot de passe de vault est requis pour chiffrer les secrets."}), 400
        try:
            result["vault"] = generate_vault_file(vault_vars, vault_password)
        except ImportError as e:
            return jsonify({"error": str(e)}), 500

    inventory_host = data.get("inventory_host")
    if inventory_host:
        result["inventory"] = generate_inventory(
            config["hosts_group"],
            inventory_host,
            data.get("ssh_user") or "deploy",
        )

    return jsonify(result)


@bp.route("/api/generate-roles", methods=["POST"])
def api_generate_roles():
    """Mode 'roles' : projet complet organise en roles, retourne sous forme de fichiers."""
    data = request.get_json(force=True) or {}
    config, vault_vars = _config_from_payload(data)

    try:
        files = generate_role_based_project(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if vault_vars:
        vault_password = data.get("vault_password")
        if not vault_password:
            return jsonify({"error": "Un mot de passe de vault est requis pour chiffrer les secrets."}), 400
        try:
            files["vault.yml"] = generate_vault_file(vault_vars, vault_password)
        except ImportError as e:
            return jsonify({"error": str(e)}), 500

    inventory_host = data.get("inventory_host")
    if inventory_host:
        files["inventory.ini"] = generate_inventory(
            config["hosts_group"],
            inventory_host,
            data.get("ssh_user") or "deploy",
        )

    return jsonify({"files": files})


@bp.route("/api/generate-roles-zip", methods=["POST"])
def api_generate_roles_zip():
    """Meme generation que /api/generate-roles, mais renvoyee en .zip telechargeable."""
    data = request.get_json(force=True) or {}
    config, vault_vars = _config_from_payload(data)

    try:
        files = generate_role_based_project(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if vault_vars:
        vault_password = data.get("vault_password")
        if not vault_password:
            return jsonify({"error": "Un mot de passe de vault est requis pour chiffrer les secrets."}), 400
        try:
            files["vault.yml"] = generate_vault_file(vault_vars, vault_password)
        except ImportError as e:
            return jsonify({"error": str(e)}), 500

    inventory_host = data.get("inventory_host")
    if inventory_host:
        files["inventory.ini"] = generate_inventory(
            config["hosts_group"],
            inventory_host,
            data.get("ssh_user") or "deploy",
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative_path, content in files.items():
            zf.writestr(relative_path, content)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="ansible-project.zip",
    )


@bp.route("/api/generate-multi", methods=["POST"])
def api_generate_multi():
    """Mode 'multi-serveurs' : plusieurs groupes, retournes sous forme de fichiers."""
    data = request.get_json(force=True) or {}
    groups = data.get("groups")
    vault_vars = data.get("vault_vars") or {}

    if not isinstance(groups, list) or not groups:
        return jsonify({"error": "Le champ 'groups' doit etre une liste non vide de groupes."}), 400

    try:
        files = generate_multi_group_roles_project(groups, vault_vars=vault_vars or None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if vault_vars:
        vault_password = data.get("vault_password")
        if not vault_password:
            return jsonify({"error": "Un mot de passe de vault est requis pour chiffrer les secrets."}), 400
        try:
            files["vault.yml"] = generate_vault_file(vault_vars, vault_password)
        except ImportError as e:
            return jsonify({"error": str(e)}), 500

    files["inventory.ini"] = generate_multi_group_inventory(groups)

    return jsonify({"files": files})


@bp.route("/api/generate-multi-zip", methods=["POST"])
def api_generate_multi_zip():
    """Meme generation que /api/generate-multi, renvoyee en .zip telechargeable."""
    data = request.get_json(force=True) or {}
    groups = data.get("groups")
    vault_vars = data.get("vault_vars") or {}

    if not isinstance(groups, list) or not groups:
        return jsonify({"error": "Le champ 'groups' doit etre une liste non vide de groupes."}), 400

    try:
        files = generate_multi_group_roles_project(groups, vault_vars=vault_vars or None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if vault_vars:
        vault_password = data.get("vault_password")
        if not vault_password:
            return jsonify({"error": "Un mot de passe de vault est requis pour chiffrer les secrets."}), 400
        try:
            files["vault.yml"] = generate_vault_file(vault_vars, vault_password)
        except ImportError as e:
            return jsonify({"error": str(e)}), 500

    files["inventory.ini"] = generate_multi_group_inventory(groups)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative_path, content in files.items():
            zf.writestr(relative_path, content)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="ansible-project-multi.zip",
    )
