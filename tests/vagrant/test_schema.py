"""Tests complementaires de schema.valider_config — branches non couvertes
par tests/vagrant/test_generateur.py (ports, provisioning, mots de passe,
compatibilite box/provider, RAM totale, IP hors RFC 1918).
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modules.vagrant.core.schema import valider_config


def _vm_minimale(**overrides):
    vm = {"name": "vm1", "box": "debian/bookworm64", "memory": 1024, "cpus": 1}
    vm.update(overrides)
    return vm


# --------------------------------------------------------------------------
# Structure generale
# --------------------------------------------------------------------------

def test_config_non_dict_rejetee():
    erreurs, avertissements = valider_config(["pas", "un", "dict"])
    assert erreurs and avertissements == []


def test_vms_non_liste_rejetee():
    erreurs, _ = valider_config({"vms": "pas-une-liste"})
    assert any("liste" in e for e in erreurs)


def test_vms_vide_avertit_sans_erreur():
    erreurs, avertissements = valider_config({"vms": []})
    assert erreurs == []
    assert any("Aucune VM" in a for a in avertissements)


def test_vm_non_dict_rejetee():
    erreurs, _ = valider_config({"vms": ["pas-un-objet"]})
    assert any("objet JSON" in e for e in erreurs)


def test_box_manquante_rejetee():
    vm = _vm_minimale()
    del vm["box"]
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("box" in e and "obligatoire" in e for e in erreurs)


def test_cpus_invalides_rejetes():
    erreurs, _ = valider_config({"vms": [_vm_minimale(cpus=0)]})
    assert any("cpus" in e for e in erreurs)


def test_provider_vm_inconnu_rejete():
    erreurs, _ = valider_config({"vms": [_vm_minimale(provider="hyperviseur-exotique")]})
    assert any("provider inconnu" in e for e in erreurs)


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------

def test_ports_format_invalide_rejete():
    vm = _vm_minimale(ports=[{"guest": 80}])  # host manquant
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("ports[0]" in e for e in erreurs)


def test_ports_hors_plage_rejetes():
    vm = _vm_minimale(ports=[{"guest": 80, "host": 99999}])
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("entre 1 et 65535" in e for e in erreurs)


def test_ports_non_liste_rejetee():
    vm = _vm_minimale(ports="pas-une-liste")
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("ports" in e and "liste" in e for e in erreurs)


def test_port_hote_duplique_avertit():
    vm1 = _vm_minimale(name="vm1", ports=[{"guest": 80, "host": 8080}])
    vm2 = _vm_minimale(name="vm2", ports=[{"guest": 80, "host": 8080}])
    erreurs, avertissements = valider_config({"vms": [vm1, vm2]})
    assert erreurs == []
    assert any("8080" in a and "déjà utilisé" in a for a in avertissements)


# --------------------------------------------------------------------------
# Provisioning
# --------------------------------------------------------------------------

def test_provision_type_inconnu_rejete():
    vm = _vm_minimale(provision={"type": "chef"})
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("provisioning inconnu" in e for e in erreurs)


def test_provision_ansible_sans_script_rejete():
    vm = _vm_minimale(provision={"type": "ansible"})
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("playbook" in e for e in erreurs)


def test_provision_ansible_avec_script_valide():
    vm = _vm_minimale(provision={"type": "ansible", "script": "site.yml"})
    erreurs, _ = valider_config({"vms": [vm]})
    assert erreurs == []


def test_provision_non_dict_rejetee():
    vm = _vm_minimale(provision="pas-un-objet")
    erreurs, _ = valider_config({"vms": [vm]})
    assert any("provision" in e and "objet JSON" in e for e in erreurs)


# --------------------------------------------------------------------------
# Securite / avertissements divers
# --------------------------------------------------------------------------

def test_mot_de_passe_en_clair_avertit():
    vm = _vm_minimale(ssh_password="hunter2")
    _, avertissements = valider_config({"vms": [vm]})
    assert any("mot de passe en clair" in a for a in avertissements)


def test_ip_hors_rfc1918_avertit():
    vm = _vm_minimale(ip="8.8.8.8")
    _, avertissements = valider_config({"vms": [vm]})
    assert any("RFC 1918" in a for a in avertissements)


def test_ip_privee_192_168_pas_davertissement_rfc():
    vm = _vm_minimale(ip="192.168.56.10")
    _, avertissements = valider_config({"vms": [vm]})
    assert not any("RFC 1918" in a for a in avertissements)


def test_ram_totale_excessive_avertit():
    vms = [_vm_minimale(name=f"vm{i}", memory=20000) for i in range(2)]
    _, avertissements = valider_config({"vms": vms})
    assert any("RAM totale du lab" in a for a in avertissements)


def test_box_provider_incompatible_avertit_sans_alternative():
    # debian/bookworm64 ne publie pas de variante vmware_desktop.
    vm = _vm_minimale(box="debian/bookworm64", provider="vmware_desktop")
    _, avertissements = valider_config({"vms": [vm]})
    assert any("ne publie pas de variante" in a for a in avertissements)


def test_box_provider_incompatible_suggere_une_alternative():
    catalogue_test = {
        "debian/bookworm64": ["virtualbox", "libvirt"],
        "generic/bookworm64": ["virtualbox", "vmware_desktop"],
    }
    with patch("modules.vagrant.core.schema.BOX_PROVIDERS", catalogue_test):
        vm = _vm_minimale(box="debian/bookworm64", provider="vmware_desktop")
        _, avertissements = valider_config({"vms": [vm]})
    assert any("generic/bookworm64" in a for a in avertissements)
