"""Tests du cœur VagrantForge — génération, validation, presets.

Lancement :
    python -m pytest tests/ -v
    (ou sans pytest : python tests/test_generateur.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modules.vagrant.core.generateur import construire_vagrantfile, nom_variable, echapper, construire_sections
from modules.vagrant.core.schema import valider_config
from modules.vagrant.core.presets import PRESETS, obtenir_preset
from modules.vagrant.core.lint import linter_vagrantfile


def test_nom_variable_prefixe_les_chiffres():
    assert nom_variable("3proxy") == "vm_3proxy"
    assert nom_variable("web-01") == "web_01"
    assert nom_variable("") == "vm"


def test_echapper_guillemets():
    assert echapper('a"b') == 'a\\"b'


def test_generation_minimale():
    config = {"provider": "virtualbox", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 1024, "cpus": 1}
    ]}
    vf = construire_vagrantfile(config)
    assert 'Vagrant.configure("2")' in vf
    assert 'config.vm.define "web"' in vf
    assert 'vb.memory = 1024' in vf
    assert vf.strip().endswith("end")


def test_generation_ports_et_ip():
    config = {"provider": "virtualbox", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 512, "cpus": 1,
         "ip": "192.168.56.10", "ports": [{"guest": 80, "host": 8080}]}
    ]}
    vf = construire_vagrantfile(config)
    assert 'private_network", ip: "192.168.56.10"' in vf
    assert 'forwarded_port", guest: 80, host: 8080' in vf


def test_provision_shell_avec_root_password():
    config = {"provider": "virtualbox", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 512, "cpus": 1,
         "root_password": "secret", "provision": {"type": "shell", "script": "echo salut\n"}}
    ]}
    vf = construire_vagrantfile(config)
    assert 'echo "root:secret" | chpasswd' in vf
    assert "echo salut" in vf


def test_generation_locale_et_clavier():
    config = {"provider": "virtualbox", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 1024, "cpus": 1,
         "locale": "fr_FR.UTF-8", "keymap": "fr"}
    ]}
    vf = construire_vagrantfile(config)
    assert "update-locale LANG=fr_FR.UTF-8" in vf
    assert 'XKBLAYOUT=fr' in vf
    assert "Langue & clavier" in vf


def test_validation_detecte_noms_dupliques():
    config = {"provider": "virtualbox", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 1024, "cpus": 1},
        {"name": "web", "box": "debian/bookworm64", "memory": 1024, "cpus": 1},
    ]}
    erreurs, _ = valider_config(config)
    assert any("déjà utilisé" in e for e in erreurs)


def test_validation_detecte_ip_dupliquee():
    config = {"provider": "virtualbox", "vms": [
        {"name": "a", "box": "debian/bookworm64", "memory": 1024, "cpus": 1, "ip": "192.168.56.10"},
        {"name": "b", "box": "debian/bookworm64", "memory": 1024, "cpus": 1, "ip": "192.168.56.10"},
    ]}
    erreurs, _ = valider_config(config)
    assert any("déjà attribuée" in e for e in erreurs)


def test_validation_provider_incompatible_avertit():
    # debian/bookworm64 ne publie pas de variante vmware_desktop
    config = {"provider": "vmware_desktop", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 1024, "cpus": 1},
    ]}
    _, avertissements = valider_config(config)
    assert any("vmware_desktop" in a for a in avertissements)


def test_validation_memoire_invalide():
    config = {"provider": "virtualbox", "vms": [
        {"name": "web", "box": "debian/bookworm64", "memory": 32, "cpus": 1},
    ]}
    erreurs, _ = valider_config(config)
    assert any("memory" in e for e in erreurs)


def test_tous_les_presets_sont_valides():
    for nom in PRESETS:
        config = obtenir_preset(nom)
        erreurs, _ = valider_config(config)
        assert erreurs == [], f"Preset « {nom} » invalide : {erreurs}"
        # et il doit se générer sans exploser
        assert construire_vagrantfile(config).strip().endswith("end")


def test_catalogue_presets_attendu():
    # Verrou anti-régression : si un preset disparaît sans le vouloir, ce test le dit.
    attendus = {"solo", "k3s", "lamp", "devsecops", "pentest",
                "monitoring", "elk", "wordpress", "gitlab-runner", "nextcloud"}
    assert attendus <= set(PRESETS)


def test_gabarit_par_defaut_identique_a_lhistorique():
    config = obtenir_preset("solo")
    assert construire_vagrantfile(config) == construire_vagrantfile(config, gabarit=None)


def test_gabarit_personnalise_insere_les_sections():
    config = obtenir_preset("solo")
    gabarit = "# Mon en-tête maison\n$ENTETE\n$VMS\n$PIED\n# Généré le $DATE, $NB_VMS VM(s)\n"
    resultat = construire_vagrantfile(config, gabarit=gabarit)
    assert resultat.startswith("# Mon en-tête maison\n")
    assert "Vagrant.configure" in resultat
    assert resultat.rstrip().endswith("VM(s)")


def test_gabarit_variable_inconnue_ne_plante_pas():
    config = obtenir_preset("solo")
    resultat = construire_vagrantfile(config, gabarit="$ENTETE $VMS $PIED $CECI_NEXISTE_PAS")
    assert "$CECI_NEXISTE_PAS" in resultat  # laissé tel quel (safe_substitute)


def test_construire_sections_expose_les_metadonnees():
    config = obtenir_preset("k3s")
    sections = construire_sections(config)
    assert sections["NB_VMS"] == "3"
    assert sections["PROVIDER"] == "virtualbox"
    assert "k3s-master" in sections["VMS"]


def test_lint_valide_tous_les_presets():
    for nom in PRESETS:
        contenu = construire_vagrantfile(obtenir_preset(nom))
        erreurs, _ = linter_vagrantfile(contenu, utiliser_ruby=False)
        assert erreurs == [], f"Preset « {nom} » : Vagrantfile généré invalide : {erreurs}"


def test_lint_detecte_bloc_do_non_ferme():
    casse = 'Vagrant.configure("2") do |config|\n  config.vm.box = "x"\n'
    erreurs, _ = linter_vagrantfile(casse, utiliser_ruby=False)
    assert any("jamais refermé" in e for e in erreurs)


def test_lint_detecte_heredoc_non_ferme():
    casse = 'config.vm.provision "shell", inline: <<-SHELL\n  echo hi\n'
    erreurs, _ = linter_vagrantfile(casse, utiliser_ruby=False)
    assert any("heredoc" in e for e in erreurs)


def test_lint_ignore_do_end_dans_un_heredoc():
    # "do" et "end" à l'intérieur d'un heredoc shell ne doivent pas fausser le compte.
    contenu = (
        'Vagrant.configure("2") do |config|\n'
        '  config.vm.provision "shell", inline: <<-SHELL\n'
        '    for i in 1 2 3; do echo $i; end\n'
        '  SHELL\n'
        'end\n'
    )
    erreurs, _ = linter_vagrantfile(contenu, utiliser_ruby=False)
    assert erreurs == []


def test_lint_vagrantfile_vide():
    erreurs, _ = linter_vagrantfile("", utiliser_ruby=False)
    assert erreurs == ["le Vagrantfile généré est vide."]


if __name__ == "__main__":
    fonctions = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    echecs = 0
    for f in fonctions:
        try:
            f()
            print(f"  ok   {f.__name__}")
        except AssertionError as e:
            echecs += 1
            print(f"  FAIL {f.__name__} : {e}")
    print(f"\n{len(fonctions) - echecs}/{len(fonctions)} tests passés.")
    sys.exit(1 if echecs else 0)
