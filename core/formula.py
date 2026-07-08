"""
Évaluation de la formule de calcul du besoin théorique (section 6 du cahier).

Décision retenue : formule en texte libre, mais évaluée via un interpréteur
restreint (asteval) plutôt qu'un eval() Python natif. L'application étant
mono-utilisateur et sans exposition réseau, l'enjeu n'est pas la sécurité
(pas d'attaquant externe) mais la robustesse : une formule mal écrite doit
produire un message d'erreur clair, jamais un plantage ni un résultat
silencieusement faux.
"""
import math
import re
from asteval import Interpreter

# Variables that a formule_calcul is allowed to reference. Kept explicit so
# the "Tester la formule" screen can list them and validation can catch
# typos (unknown variable) before saving.
VARIABLES_DISPONIBLES = [
    "diametre",      # diamètre utilisé pour la campagne (mm)
    "longueur_zone",  # longueur de la zone (mm)
    "epaisseur",     # épaisseur de garnissage utilisée (mm)
    "longueur",      # longueur de la brique (mm)
    "largeur",       # largeur de la brique (mm)
    "hauteur",       # hauteur de la brique (mm)
    "taux_chute",    # coefficient de perte à la découpe (ex. 0.08)
    "PI",
]


class FormuleInvalide(Exception):
    pass


# Valeurs d'exemple utilisées par le bouton "Tester la formule" (section 6)
# et par la validation automatique au niveau du modèle (TypeBrique.clean()).
VALEURS_EXEMPLE = {
    "diametre": 3000,
    "longueur_zone": 1000,
    "epaisseur": 200,
}


def _make_interpreter():
    aeval = Interpreter(
        use_numpy=False,
        minimal=True,
        builtins_readonly=True,
    )
    # Strip everything, then whitelist a small safe symbol table.
    aeval.symtable.clear()
    aeval.symtable.update({
        "PI": math.pi,
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
    })
    return aeval


def _corriger_virgules_decimales(formule: str) -> str:
    """
    Convertit une virgule décimale à la française (3,14) en point (3.14).

    En Python (et donc pour asteval), une virgule est le séparateur de
    tuple : "3,14" est littéralement le tuple (3, 14), pas le nombre 3.14.
    C'est cette confusion qui produit l'erreur cryptique
    "unsupported operand type(s) for /: 'tuple' and 'float'" quand une
    formule est tapée avec des virgules décimales.

    Limite assumée : si la formule utilise un appel à plusieurs arguments
    sans espace entre deux nombres entiers (ex. min(3,14) voulant dire
    min(3, 14) et non min(3.14)), cette correction l'interprétera à tort
    comme une virgule décimale. Dans le contexte de ces formules (calcul
    géométrique de besoin en briques), ce cas ne devrait pas se présenter.
    """
    return re.sub(r"(?<=\d),(?=\d)", ".", formule)


def evaluer_formule(formule: str, variables: dict):
    """
    Évalue `formule` avec les valeurs de `variables`.
    Retourne (succes: bool, resultat_ou_message_erreur).
    Ne lève jamais d'exception — toute erreur est renvoyée sous forme de
    message, pour que l'appelant (vue) puisse l'afficher proprement.
    """
    if not formule or not formule.strip():
        return False, "La formule est vide."

    formule = _corriger_virgules_decimales(formule)

    inconnues = set()
    aeval = _make_interpreter()
    for key, value in variables.items():
        if key not in VARIABLES_DISPONIBLES:
            inconnues.add(key)
        aeval.symtable[key] = float(value)

    try:
        resultat = aeval(formule, show_errors=False)
    except Exception as exc:  # pragma: no cover - defensive, asteval rarely raises
        return False, f"Erreur d'évaluation : {exc}"

    if aeval.error:
        messages = "; ".join(err.get_error()[1] for err in aeval.error)
        return False, f"Formule invalide : {messages}"

    if resultat is None:
        return False, "La formule n'a produit aucun résultat numérique."

    try:
        resultat = float(resultat)
    except (TypeError, ValueError):
        return False, "La formule ne produit pas un nombre."

    if resultat < 0:
        return False, "La formule produit une quantité négative — vérifiez les paramètres."

    return True, resultat
