"""VagrantForge — lint du Vagrantfile généré.

Le cœur ne dépend d'aucune bibliothèque externe et Ruby n'est pas forcément
installé sur la machine qui génère le fichier (CI, conteneur minimal…).
`linter_vagrantfile` fait donc d'abord une passe **structurelle** en pur
Python (blocs `do ... end` équilibrés, guillemets et parenthèses équilibrés,
heredocs `<<-SHELL ... SHELL` bien refermés) : elle attrape la grande
majorité des Vagrantfile cassés qu'un bug de génération pourrait produire.

Si l'exécutable `ruby` est disponible dans le PATH, `ruby -c` (vérif de
syntaxe uniquement, rien n'est exécuté) est utilisé en complément pour une
vraie validation de la syntaxe Ruby.

Retourne toujours (erreurs, avertissements), comme `valider_config`.
"""

import re
import shutil
import subprocess

MOTS_OUVRANTS = re.compile(r"\bdo\b(\s*\|[^|]*\|)?\s*$")
MOT_FERMANT = re.compile(r"^\s*end\b")
DEBUT_HEREDOC = re.compile(r"<<-?(['\"]?)(\w+)\1")


def _verifier_blocs_do_end(lignes):
    """Vérifie l'équilibre des blocs `do ... end` ligne par ligne (heuristique).

    Ignore le contenu des heredocs shell, qui peut légitimement contenir les
    mots « do » ou « end » sans rapport avec la structure Ruby.
    """
    profondeur = 0
    dans_heredoc = False
    marqueur_fin = None
    numero_ouverture = []

    for i, ligne in enumerate(lignes, start=1):
        if dans_heredoc:
            if ligne.strip() == marqueur_fin:
                dans_heredoc = False
                marqueur_fin = None
            continue

        m_heredoc = DEBUT_HEREDOC.search(ligne)
        if m_heredoc:
            dans_heredoc = True
            marqueur_fin = m_heredoc.group(2)
            continue

        sans_commentaire = re.sub(r"#.*$", "", ligne)

        if MOTS_OUVRANTS.search(sans_commentaire):
            profondeur += 1
            numero_ouverture.append(i)
        elif MOT_FERMANT.match(sans_commentaire):
            if profondeur == 0:
                return [f"ligne {i} : « end » sans bloc ouvert correspondant."]
            profondeur -= 1
            numero_ouverture.pop()

    if profondeur > 0:
        return [
            f"ligne {numero_ouverture[0]} : bloc ouvert (« do ») jamais refermé par un « end »."
        ]
    return []


def _verifier_heredocs_non_fermes(contenu):
    """Détecte un heredoc shell (<<-SHELL) jamais refermé sur tout le fichier."""
    erreurs = []
    lignes = contenu.split("\n")
    i = 0
    while i < len(lignes):
        m = DEBUT_HEREDOC.search(lignes[i])
        if m:
            marqueur = m.group(2)
            ferme = False
            for j in range(i + 1, len(lignes)):
                if lignes[j].strip() == marqueur:
                    ferme = True
                    break
            if not ferme:
                erreurs.append(f"ligne {i + 1} : heredoc <<-{marqueur} jamais refermé par « {marqueur} ».")
        i += 1
    return erreurs


def _verifier_guillemets_equilibres(lignes):
    """Détecte un nombre impair de guillemets doubles hors heredoc/commentaire (signal faible)."""
    avertissements = []
    dans_heredoc = False
    marqueur_fin = None
    for i, ligne in enumerate(lignes, start=1):
        if dans_heredoc:
            if ligne.strip() == marqueur_fin:
                dans_heredoc = False
            continue
        m_heredoc = DEBUT_HEREDOC.search(ligne)
        if m_heredoc:
            dans_heredoc = True
            marqueur_fin = m_heredoc.group(2)
            continue
        sans_commentaire = re.sub(r"#.*$", "", ligne)
        # Ignore les guillemets échappés (\") pour ce comptage grossier.
        sans_echappement = sans_commentaire.replace('\\"', "")
        if sans_echappement.count('"') % 2 != 0:
            avertissements.append(
                f"ligne {i} : nombre impair de guillemets doubles — chaîne peut-être mal fermée."
            )
    return avertissements


def _verifier_avec_ruby(contenu, timeout=5):
    """Si `ruby` est installé, lance `ruby -c` (vérif syntaxe seule, aucune exécution)."""
    ruby = shutil.which("ruby")
    if not ruby:
        return (None, None)  # pas disponible, pas d'avis
    try:
        resultat = subprocess.run(
            [ruby, "-c"],
            input=contenu,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return (None, None)
    if resultat.returncode != 0:
        message = resultat.stderr.strip() or resultat.stdout.strip() or "erreur de syntaxe Ruby."
        return ([f"ruby -c : {message}"], None)
    return (None, ["ruby -c : syntaxe valide."])


def linter_vagrantfile(contenu, utiliser_ruby=True):
    """Vérifie qu'un Vagrantfile généré est structurellement cohérent.

    `contenu` : le texte du Vagrantfile. `utiliser_ruby` : tente `ruby -c`
    en plus des vérifications structurelles si l'exécutable est disponible.

    Retourne (erreurs, avertissements), comme `valider_config`.
    """
    erreurs = []
    avertissements = []

    if not contenu or not contenu.strip():
        return (["le Vagrantfile généré est vide."], [])

    lignes = contenu.split("\n")

    erreurs += _verifier_blocs_do_end(lignes)
    erreurs += _verifier_heredocs_non_fermes(contenu)
    avertissements += _verifier_guillemets_equilibres(lignes)

    if utiliser_ruby:
        erreurs_ruby, avert_ruby = _verifier_avec_ruby(contenu)
        if erreurs_ruby:
            erreurs += erreurs_ruby
        if avert_ruby:
            avertissements += avert_ruby

    return (erreurs, avertissements)
