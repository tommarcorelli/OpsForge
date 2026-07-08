"""VagrantForge — validation de la config et diagnostics en français.

`valider_config(config)` retourne un tuple `(erreurs, avertissements)` :
- erreurs : bloquantes, le Vagrantfile généré serait cassé ou incohérent ;
- avertissements : le fichier fonctionnera, mais quelque chose mérite un œil.
"""

import re

from .generateur import PROVIDERS_CONNUS

# Compatibilité connue box <-> providers Vagrant Cloud.
# Basé sur les providers réellement publiés pour chaque box (app.vagrantup.com).
# Cette table est figée à la main et peut se périmer : lance
# « forge verifier-box » (core/verif_box.py) de temps en temps pour la
# comparer à Vagrant Cloud.
# 'generic/*' (roboxes) et 'bento/*' (Chef Bento) supportent plusieurs providers,
# dont vmware_desktop — contrairement aux box officielles debian/* et ubuntu/*.
BOX_PROVIDERS = {
    "debian/bookworm64":         ["virtualbox", "libvirt", "hyperv", "qemu"],
    "debian/bullseye64":         ["virtualbox", "libvirt", "hyperv", "qemu"],
    "debian/buster64":           ["virtualbox", "libvirt", "hyperv", "qemu"],
    "debian/testing64":          ["virtualbox", "libvirt", "hyperv", "qemu"],
    "ubuntu/noble64":            ["virtualbox", "libvirt", "hyperv"],
    "ubuntu/jammy64":            ["virtualbox", "libvirt", "hyperv"],
    "ubuntu/focal64":            ["virtualbox", "libvirt", "hyperv"],
    "ubuntu/bionic64":           ["virtualbox", "libvirt", "hyperv"],
    "bento/debian-12":           ["virtualbox", "vmware_desktop", "parallels"],
    "bento/debian-11":           ["virtualbox", "vmware_desktop", "parallels"],
    "bento/debian-10":           ["virtualbox", "vmware_desktop", "parallels"],
    "bento/ubuntu-24.04":        ["virtualbox", "vmware_desktop", "parallels"],
    "bento/ubuntu-22.04":        ["virtualbox", "vmware_desktop", "parallels"],
    "bento/ubuntu-20.04":        ["virtualbox", "vmware_desktop", "parallels"],
    "bento/centos-stream-9":     ["virtualbox", "vmware_desktop", "parallels"],
    "bento/centos-stream-8":     ["virtualbox", "vmware_desktop", "parallels"],
    "bento/fedora-39":           ["virtualbox", "vmware_desktop", "parallels"],
    "generic/rocky9":            ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/rocky8":            ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/alma9":             ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/alma8":             ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/fedora39":          ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/fedora38":          ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/oracle9":           ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/oracle8":           ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/debian12":          ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/debian11":          ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/ubuntu2204":        ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/freebsd14":         ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/freebsd13":         ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/alpine319":         ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "generic/alpine318":         ["virtualbox", "vmware_desktop", "libvirt", "hyperv", "parallels"],
    "kalilinux/rolling":         ["virtualbox", "vmware_desktop"],
    "archlinux/archlinux":       ["virtualbox", "libvirt", "hyperv", "vmware_desktop"],
    "opensuse/Leap-15.5.x86_64": ["virtualbox", "libvirt", "hyperv"],
    "opensuse/Leap-15.4.x86_64": ["virtualbox", "libvirt", "hyperv"],
}

REGEX_NOM = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
REGEX_IPV4 = re.compile(
    r"^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$"
)
TYPES_PROVISION = ("shell", "ansible", "none")


def _est_entier(valeur):
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def valider_config(config):
    """Valide une config VagrantForge. Retourne (erreurs, avertissements)."""
    erreurs = []
    avertissements = []

    if not isinstance(config, dict):
        return (["La config doit être un objet JSON (dictionnaire)."], [])

    provider_global = config.get("provider", "virtualbox")
    if provider_global not in PROVIDERS_CONNUS:
        erreurs.append(
            f"Provider global inconnu : « {provider_global} » "
            f"(attendu : {', '.join(PROVIDERS_CONNUS)})."
        )

    vms = config.get("vms", [])
    if not isinstance(vms, list):
        return (erreurs + ["Le champ « vms » doit être une liste."], avertissements)
    if not vms:
        avertissements.append("Aucune VM définie : le Vagrantfile généré sera vide.")

    noms_vus = {}
    ips_vues = {}
    ports_hote_vus = {}
    total_ram = 0

    for i, vm in enumerate(vms):
        ou = f"vms[{i}]"
        if not isinstance(vm, dict):
            erreurs.append(f"{ou} : chaque VM doit être un objet JSON.")
            continue

        nom = vm.get("name", "")
        if not nom or not REGEX_NOM.match(str(nom)):
            erreurs.append(
                f"{ou} : nom de VM invalide « {nom} » "
                "(lettres/chiffres, puis lettres/chiffres/tirets/underscores)."
            )
        elif nom in noms_vus:
            erreurs.append(f"{ou} : nom « {nom} » déjà utilisé par vms[{noms_vus[nom]}].")
        else:
            noms_vus[nom] = i

        if not vm.get("box"):
            erreurs.append(f"{ou} ({nom}) : le champ « box » est obligatoire.")

        memoire = vm.get("memory", 1024)
        if not _est_entier(memoire) or memoire < 128:
            erreurs.append(f"{ou} ({nom}) : « memory » doit être un entier ≥ 128 (Mo).")
        else:
            total_ram += memoire
            if memoire < 512:
                avertissements.append(
                    f"{nom} : {memoire} Mo de RAM, c'est très peu pour la plupart des OS."
                )

        cpus = vm.get("cpus", 1)
        if not _est_entier(cpus) or cpus < 1:
            erreurs.append(f"{ou} ({nom}) : « cpus » doit être un entier ≥ 1.")

        ip = vm.get("ip", "")
        if ip:
            if not REGEX_IPV4.match(str(ip)):
                erreurs.append(f"{ou} ({nom}) : IP invalide « {ip} ».")
            elif ip in ips_vues:
                erreurs.append(f"{ou} ({nom}) : IP {ip} déjà attribuée à « {ips_vues[ip]} ».")
            else:
                ips_vues[ip] = nom
                if not (ip.startswith("10.") or ip.startswith("192.168.")
                        or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", ip)):
                    avertissements.append(
                        f"{nom} : {ip} n'est pas une IP privée (RFC 1918), "
                        "risque de conflit avec le vrai réseau."
                    )

        provider_vm = vm.get("provider", "")
        if provider_vm and provider_vm not in PROVIDERS_CONNUS:
            erreurs.append(f"{ou} ({nom}) : provider inconnu « {provider_vm} ».")
        provider_effectif = provider_vm or provider_global

        box = vm.get("box", "")
        publies = BOX_PROVIDERS.get(box)
        if publies and provider_effectif not in publies:
            alternative = next(
                (b for b in BOX_PROVIDERS
                 if provider_effectif in BOX_PROVIDERS[b]
                 and "/" in box and b.split("/")[-1] == box.split("/")[-1]),
                None,
            )
            msg = (
                f"{nom} : la box « {box} » ne publie pas de variante "
                f"{provider_effectif} sur Vagrant Cloud."
            )
            if alternative:
                msg += f" Essaie plutôt « {alternative} »."
            avertissements.append(msg)

        ports = vm.get("ports", [])
        if not isinstance(ports, list):
            erreurs.append(f"{ou} ({nom}) : « ports » doit être une liste.")
            ports = []
        for j, port in enumerate(ports):
            if not isinstance(port, dict) or "guest" not in port or "host" not in port:
                erreurs.append(f"{ou}.ports[{j}] ({nom}) : format attendu {{\"guest\": N, \"host\": N}}.")
                continue
            for cle in ("guest", "host"):
                valeur = port[cle]
                if not _est_entier(valeur) or not (1 <= valeur <= 65535):
                    erreurs.append(
                        f"{ou}.ports[{j}] ({nom}) : « {cle} » doit être un entier entre 1 et 65535."
                    )
            hote = port.get("host")
            if _est_entier(hote):
                if hote in ports_hote_vus:
                    avertissements.append(
                        f"{nom} : port hôte {hote} déjà utilisé par « {ports_hote_vus[hote]} » "
                        "(auto_correct le déplacera au vagrant up)."
                    )
                else:
                    ports_hote_vus[hote] = nom

        provision = vm.get("provision") or {}
        if not isinstance(provision, dict):
            erreurs.append(f"{ou} ({nom}) : « provision » doit être un objet JSON.")
        else:
            type_prov = provision.get("type", "none")
            if type_prov not in TYPES_PROVISION:
                erreurs.append(
                    f"{ou} ({nom}) : type de provisioning inconnu « {type_prov} » "
                    f"(attendu : {', '.join(TYPES_PROVISION)})."
                )
            if type_prov == "ansible" and not provision.get("script"):
                erreurs.append(f"{ou} ({nom}) : provisioning ansible sans chemin de playbook.")

        if vm.get("ssh_password") or vm.get("root_password"):
            avertissements.append(
                f"{nom} : mot de passe en clair dans la config — OK pour un lab jetable, "
                "à proscrire ailleurs."
            )

    if total_ram > 32768:
        avertissements.append(
            f"RAM totale du lab : {total_ram} Mo — vérifie que la machine hôte encaisse."
        )

    return (erreurs, avertissements)
