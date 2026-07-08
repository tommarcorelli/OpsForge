"""VagrantForge — vérification du catalogue de box face à Vagrant Cloud.

`core.schema.BOX_PROVIDERS` est une liste codée en dur des providers publiés
pour chaque box (utilisée pour avertir en cas d'incompatibilité box/provider).
Comme toute liste figée, elle peut se périmer : une box retirée, un nouveau
provider ajouté, une release renommée…

Ce module interroge l'API publique Vagrant Cloud (https://app.vagrantup.com)
pour comparer la liste locale à la réalité. Contrairement au reste du cœur
(génération, validation), il a besoin du réseau : c'est un outil de
maintenance à lancer ponctuellement (`forge verifier-box`) ou en CI, jamais
pendant une génération normale.
"""

import json
import urllib.error
import urllib.request

API_BOX = "https://app.vagrantup.com/api/v1/box/{nom}"


def recuperer_providers_distants(nom_box, timeout=10):
    """Interroge Vagrant Cloud pour une box.

    Retourne (providers, erreur) : `providers` est une liste triée de noms
    de providers si l'appel a réussi, sinon `None` ; `erreur` est un message
    lisible si quelque chose a échoué, sinon `None`.
    """
    url = API_BOX.format(nom=nom_box)
    try:
        requete = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            data = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (None, "introuvable sur Vagrant Cloud (404) — box retirée ou renommée ?")
        return (None, f"HTTP {e.code}")
    except urllib.error.URLError as e:
        return (None, f"réseau indisponible : {e.reason}")
    except (TimeoutError, OSError) as e:
        return (None, f"réseau indisponible : {e}")
    except json.JSONDecodeError:
        return (None, "réponse JSON invalide")

    providers = set()
    for version in data.get("versions", []):
        for provider in version.get("providers", []):
            nom_provider = provider.get("name")
            if nom_provider:
                providers.add(nom_provider)
    return (sorted(providers), None)


def verifier_catalogue(box_providers, timeout=10):
    """Compare le catalogue local `{box: [providers]}` à Vagrant Cloud.

    Retourne une liste de rapports (dicts) : box, locaux, distants, erreur,
    manquants_localement (publiés mais absents de notre liste), en_trop
    (dans notre liste mais plus publiés).
    """
    rapports = []
    for nom_box, providers_locaux in sorted(box_providers.items()):
        providers_distants, erreur = recuperer_providers_distants(nom_box, timeout)
        rapport = {
            "box": nom_box,
            "locaux": sorted(providers_locaux),
            "distants": providers_distants,
            "erreur": erreur,
            "manquants_localement": [],
            "en_trop": [],
        }
        if providers_distants is not None:
            locaux = set(providers_locaux)
            distants = set(providers_distants)
            rapport["manquants_localement"] = sorted(distants - locaux)
            rapport["en_trop"] = sorted(locaux - distants)
        rapports.append(rapport)
    return rapports
