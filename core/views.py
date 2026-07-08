import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import ProtectedError, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import forms, models
from .formula import VALEURS_EXEMPLE, evaluer_formule


# ---------------------------------------------------------------------------
# Petit utilitaire pour éviter de dupliquer le même CRUD plusieurs fois
# ---------------------------------------------------------------------------

def _simple_crud_form(request, *, model, form_class, instance, template, list_url_name, success_message):
    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, success_message)
            return redirect(f"core:{list_url_name}")
    else:
        form = form_class(instance=instance)
    return render(request, template, {"form": form, "instance": instance})


def _simple_delete(request, *, obj, template, list_url_name):
    if request.method == "POST":
        try:
            obj.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Impossible de supprimer « {obj} » : des campagnes, calculs ou consommations "
                f"y font encore référence. Supprimez ou déplacez d'abord ces éléments.",
            )
            return redirect(f"core:{list_url_name}")
        messages.success(request, "Suppression effectuée.")
        return redirect(f"core:{list_url_name}")
    return render(request, template, {"objet": obj})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(request):
    stocks = list(models.Stock.objects.select_related("sous_type_brique", "sous_type_brique__type_brique"))
    stocks_sous_seuil = [s for s in stocks if s.sous_seuil]
    stocks_negatifs = [s for s in stocks if s.negatif]
    derniere_campagne = models.Campagne.objects.order_by("-date_debut").first()

    total_besoin = models.BesoinTheorique.objects.aggregate(t=Sum("quantite_calculee"))["t"] or Decimal("0")
    total_conso = models.ConsommationReelle.objects.aggregate(t=Sum("quantite_posee"))["t"] or Decimal("0")
    ecart_cumule = total_conso - total_besoin

    return render(request, "core/dashboard.html", {
        "stocks_sous_seuil": stocks_sous_seuil,
        "stocks_negatifs": stocks_negatifs,
        "derniere_campagne": derniere_campagne,
        "ecart_cumule": ecart_cumule,
        "nb_campagnes_en_cours": models.Campagne.objects.filter(statut="en_cours").count(),
    })


# ---------------------------------------------------------------------------
# Four
# ---------------------------------------------------------------------------

def four_list(request):
    return render(request, "core/four_list.html", {"fours": models.Four.objects.all()})


def four_form(request, pk=None):
    instance = get_object_or_404(models.Four, pk=pk) if pk else None
    return _simple_crud_form(
        request, model=models.Four, form_class=forms.FourForm, instance=instance,
        template="core/four_form.html", list_url_name="four_list", success_message="Four enregistré.",
    )


def four_delete(request, pk):
    four = get_object_or_404(models.Four, pk=pk)
    return _simple_delete(request, obj=four, template="core/confirm_delete.html", list_url_name="four_list")


# ---------------------------------------------------------------------------
# Zone (configuration four — section 7)
# ---------------------------------------------------------------------------

def _schema_zones_four(four):
    """
    Prépare les données du schéma simplifié du four (section 7 du cahier :
    "Configuration four : vue schématique des zones"). Largeur de chaque
    zone proportionnelle à sa longueur réelle, avec une largeur minimale
    pour que les zones courtes restent lisibles et cliquables.
    """
    LARGEUR_MIN = 70
    HAUTEUR_MAX = 90
    zones = list(four.zones.order_by("position"))
    if not zones:
        return {"zones": [], "largeur_totale": 0, "hauteur_max": HAUTEUR_MAX}

    longueur_totale = sum((z.longueur for z in zones), Decimal("0")) or Decimal("1")
    diametre_max = max((z.diametre_nominal for z in zones), default=Decimal("1")) or Decimal("1")
    largeur_dispo = 560

    AXE_Y = 65
    segments = []
    x = 0
    for z in zones:
        largeur = max(LARGEUR_MIN, round(float(z.longueur / longueur_totale) * largeur_dispo))
        hauteur = max(30, round(float(z.diametre_nominal / diametre_max) * HAUTEUR_MAX))
        segments.append({
            "zone": z, "x": x, "largeur": largeur, "hauteur": hauteur,
            "y": AXE_Y - hauteur // 2,
        })
        x += largeur

    return {"zones": segments, "largeur_totale": x, "hauteur_max": HAUTEUR_MAX}


def zone_list(request):
    zones = models.Zone.objects.select_related("four", "sous_type_brique_defaut").prefetch_related("sous_types_brique_autorises")
    fours = models.Four.objects.prefetch_related("zones")
    schemas = [(four, _schema_zones_four(four)) for four in fours if four.zones.exists()]
    return render(request, "core/zone_list.html", {"zones": zones, "schemas": schemas})


def zone_form(request, pk=None):
    instance = get_object_or_404(models.Zone, pk=pk) if pk else None
    return _simple_crud_form(
        request, model=models.Zone, form_class=forms.ZoneForm, instance=instance,
        template="core/zone_form.html", list_url_name="zone_list", success_message="Zone enregistrée.",
    )


def zone_delete(request, pk):
    zone = get_object_or_404(models.Zone, pk=pk)
    return _simple_delete(request, obj=zone, template="core/confirm_delete.html", list_url_name="zone_list")


# ---------------------------------------------------------------------------
# TypeBrique (famille — nom + fournisseur seulement)
# ---------------------------------------------------------------------------

def type_brique_list(request):
    types = models.TypeBrique.objects.prefetch_related("sous_types")
    return render(request, "core/type_brique_list.html", {"types": types})


def type_brique_form(request, pk=None):
    instance = get_object_or_404(models.TypeBrique, pk=pk) if pk else None
    return _simple_crud_form(
        request, model=models.TypeBrique, form_class=forms.TypeBriqueForm, instance=instance,
        template="core/type_brique_form.html", list_url_name="type_brique_list", success_message="Type de brique enregistré.",
    )


def type_brique_delete(request, pk):
    type_brique = get_object_or_404(models.TypeBrique, pk=pk)
    return _simple_delete(request, obj=type_brique, template="core/confirm_delete.html", list_url_name="type_brique_list")


# ---------------------------------------------------------------------------
# SousTypeBrique — dimensions + formule + taux de chute (section 6)
# ---------------------------------------------------------------------------

def sous_type_list(request):
    sous_types = models.SousTypeBrique.objects.select_related("type_brique").prefetch_related("sous_types_lies")
    return render(request, "core/sous_type_list.html", {"sous_types": sous_types})


def sous_type_form(request, pk=None):
    instance = get_object_or_404(models.SousTypeBrique, pk=pk) if pk else None
    resultat_test = None

    if request.method == "POST":
        form = forms.SousTypeBriqueForm(request.POST, instance=instance)
        action = request.POST.get("action")

        if action == "tester":
            # Aperçu immédiat, ne sauvegarde rien. La validation réelle,
            # appliquée automatiquement à l'enregistrement (y compris depuis
            # l'admin Django), vit dans SousTypeBrique.clean().
            formule = request.POST.get("formule_calcul", "")
            try:
                variables = {
                    **VALEURS_EXEMPLE,
                    "longueur": float(request.POST.get("longueur") or 0),
                    "largeur": float(request.POST.get("largeur") or 0),
                    "hauteur": float(request.POST.get("hauteur") or 0),
                    "taux_chute": float(request.POST.get("taux_chute") or 0),
                }
            except ValueError:
                resultat_test = (False, "Dimensions ou taux de chute invalides.")
            else:
                resultat_test = evaluer_formule(formule, variables)

        elif action == "enregistrer":
            # form.is_valid() déclenche instance.full_clean(), qui appelle
            # SousTypeBrique.clean() et valide donc la formule automatiquement.
            if form.is_valid():
                form.save()
                messages.success(request, "Sous-type de brique enregistré.")
                return redirect("core:sous_type_list")
    else:
        form = forms.SousTypeBriqueForm(instance=instance)

    return render(request, "core/sous_type_form.html", {
        "form": form,
        "instance": instance,
        "resultat_test": resultat_test,
        "valeurs_exemple": VALEURS_EXEMPLE,
    })


def sous_type_delete(request, pk):
    sous_type = get_object_or_404(models.SousTypeBrique, pk=pk)
    return _simple_delete(request, obj=sous_type, template="core/confirm_delete.html", list_url_name="sous_type_list")


# ---------------------------------------------------------------------------
# Campagne + Besoin théorique (calcul besoin théorique — section 7)
# ---------------------------------------------------------------------------

def campagne_list(request):
    return render(request, "core/campagne_list.html", {
        "campagnes": models.Campagne.objects.select_related("four").prefetch_related("zones"),
    })


def campagne_form(request):
    if request.method == "POST":
        form = forms.CampagneForm(request.POST)
        if form.is_valid():
            campagne = form.save()
            messages.success(request, "Campagne créée.")
            return redirect("core:campagne_detail", pk=campagne.pk)
    else:
        form = forms.CampagneForm()
    return render(request, "core/campagne_form.html", {"form": form})


def _classer_ecart(besoin, conso):
    if besoin == 0:
        return "inconnu"
    ratio = abs(conso - besoin) / besoin
    if ratio <= Decimal("0.05"):
        return "vert"
    if ratio <= Decimal("0.15"):
        return "orange"
    return "rouge"


def campagne_detail(request, pk):
    campagne = get_object_or_404(models.Campagne, pk=pk)
    besoins = campagne.besoins.select_related("zone", "sous_type_brique", "sous_type_brique__type_brique")
    consommations = campagne.consommations.select_related("zone", "sous_type_brique", "sous_type_brique__type_brique")

    conso_par_cle = {}
    for c in consommations:
        cle = (c.zone_id, c.sous_type_brique_id)
        conso_par_cle[cle] = conso_par_cle.get(cle, Decimal("0")) + c.quantite_posee

    lignes_ecart = []
    sous_types_avec_besoin = set(besoins.values_list("sous_type_brique_id", flat=True))
    paires_manquantes = set()
    for b in besoins:
        conso = conso_par_cle.get((b.zone_id, b.sous_type_brique_id), Decimal("0"))
        ecart = conso - b.quantite_calculee
        lignes_ecart.append({
            "zone": b.zone, "sous_type_brique": b.sous_type_brique,
            "besoin": b.quantite_calculee,
            "besoin_nominal": b.quantite_calculee_nominale,
            "impact_derive": b.impact_derive,
            "conso": conso, "ecart": ecart,
            "niveau": _classer_ecart(b.quantite_calculee, conso),
        })
        for lie in b.sous_type_brique.sous_types_lies.all():
            if lie.id not in sous_types_avec_besoin:
                paires_manquantes.add((b.zone.nom, str(b.sous_type_brique), str(lie)))

    zones_sans_besoin = campagne.zones.exclude(
        id__in=besoins.values_list("zone_id", flat=True)
    )

    return render(request, "core/campagne_detail.html", {
        "campagne": campagne,
        "lignes_ecart": lignes_ecart,
        "zones_sans_besoin": zones_sans_besoin,
        "consommations": consommations,
        "paires_manquantes": paires_manquantes,
    })


def _calculer_besoin_pour_sous_type(campagne, zone, sous_type, diametre, epaisseur):
    """
    Calcule et enregistre le BesoinTheorique pour un sous-type donné, avec
    et sans dérive géométrique. Retourne (ok, resultat_reel_ou_message_erreur).
    Factorisé pour être appelé à la fois pour le sous-type choisi et pour
    ses éventuels sous-types liés (ex. paire trapézoïdale X/Y — section 6bis).
    """
    base_variables = {
        "longueur_zone": float(zone.longueur),
        "epaisseur": float(epaisseur),
        "longueur": float(sous_type.longueur),
        "largeur": float(sous_type.largeur),
        "hauteur": float(sous_type.hauteur),
        "taux_chute": float(sous_type.taux_chute),
    }

    # Avec dérive : diamètre réellement mesuré pour cette campagne.
    ok_reel, resultat_reel = evaluer_formule(
        sous_type.formule_calcul, {**base_variables, "diametre": float(diametre)}
    )
    if not ok_reel:
        return False, f"« {sous_type} » — erreur dans la formule (diamètre mesuré) : {resultat_reel}"

    # Sans dérive : diamètre nominal de conception de la zone, figé, pour
    # isoler l'effet de l'usure du reste de l'écart (section 8).
    ok_nominal, resultat_nominal = evaluer_formule(
        sous_type.formule_calcul, {**base_variables, "diametre": float(zone.diametre_nominal)}
    )
    if not ok_nominal:
        return False, f"« {sous_type} » — erreur dans la formule (diamètre nominal) : {resultat_nominal}"

    models.BesoinTheorique.objects.update_or_create(
        campagne=campagne, zone=zone, sous_type_brique=sous_type,
        defaults={
            "diametre_utilise": diametre,
            "epaisseur_garnissage_utilisee": epaisseur,
            "quantite_calculee": Decimal(str(round(resultat_reel, 2))),
            "quantite_calculee_nominale": Decimal(str(round(resultat_nominal, 2))),
        },
    )
    return True, round(resultat_reel, 2)


def campagne_calculer_besoin(request, pk, zone_pk):
    campagne = get_object_or_404(models.Campagne, pk=pk)
    zone = get_object_or_404(models.Zone, pk=zone_pk, campagnes=campagne)

    if campagne.statut == "cloturee":
        messages.error(request, "Cette campagne est clôturée : impossible d'ajouter un nouveau calcul de besoin.")
        return redirect("core:campagne_detail", pk=campagne.pk)

    initial = {
        "diametre_utilise": zone.diametre_nominal,
        "epaisseur_garnissage_utilisee": 0,
        "sous_type_brique": zone.sous_type_brique_defaut,
    }

    if request.method == "POST":
        form = forms.CalculBesoinForm(request.POST, zone=zone)
        if form.is_valid():
            sous_type = form.cleaned_data["sous_type_brique"]
            diametre = form.cleaned_data["diametre_utilise"]
            epaisseur = form.cleaned_data["epaisseur_garnissage_utilisee"]

            ok, resultat = _calculer_besoin_pour_sous_type(campagne, zone, sous_type, diametre, epaisseur)
            if not ok:
                messages.error(request, resultat)
            else:
                messages_succes = [f"« {sous_type} » : {resultat} pièces"]

                # Sous-types liés (ex. X/Y toujours utilisés ensemble) :
                # calculés automatiquement avec la même géométrie, pour ne
                # jamais oublier la moitié d'une paire.
                for lie in sous_type.sous_types_lies.all():
                    ok_lie, resultat_lie = _calculer_besoin_pour_sous_type(campagne, zone, lie, diametre, epaisseur)
                    if ok_lie:
                        messages_succes.append(f"« {lie} » (lié) : {resultat_lie} pièces")
                    else:
                        messages.warning(request, f"Sous-type lié non calculé — {resultat_lie}")

                messages.success(request, "Besoin calculé — " + " ; ".join(messages_succes))
                return redirect("core:campagne_detail", pk=campagne.pk)
    else:
        form = forms.CalculBesoinForm(initial=initial, zone=zone)

    return render(request, "core/campagne_calculer_besoin.html", {
        "campagne": campagne, "zone": zone, "form": form,
    })


# ---------------------------------------------------------------------------
# Tableau de calcul — écran unique type "tableur" pour toutes les zones
# d'une campagne à la fois (remplace le calcul zone par zone ci-dessus).
# ---------------------------------------------------------------------------

def _sous_types_colonnes(campagne):
    """
    Liste ordonnée et dédupliquée de tous les sous-types pertinents pour au
    moins une zone de la campagne — devient les colonnes du tableau. Reste
    dynamique : ajouter un 3e ou 4e sous-type plus tard ajoute une colonne
    automatiquement, sans rien à changer ici.
    """
    ids_vus = []
    sous_types = []
    for zone in campagne.zones.all():
        for st in zone.sous_types_disponibles():
            if st.id not in ids_vus:
                ids_vus.append(st.id)
                sous_types.append(st)
    return sous_types


def campagne_tableau(request, pk):
    campagne = get_object_or_404(models.Campagne, pk=pk)
    zones = campagne.zones.select_related("sous_type_brique_defaut").order_by("position")
    colonnes = _sous_types_colonnes(campagne)

    besoins_existants = {
        (b.zone_id, b.sous_type_brique_id): b
        for b in campagne.besoins.all()
    }

    lignes = []
    for zone in zones:
        # Valeurs de départ : celles déjà enregistrées pour cette zone si
        # elles existent (n'importe quel sous-type de la zone donne la même
        # géométrie mesurée), sinon les valeurs nominales de la zone.
        premiere_ligne_zone = next(
            (b for (z_id, _), b in besoins_existants.items() if z_id == zone.id), None
        )
        diametre_depart = premiere_ligne_zone.diametre_utilise if premiere_ligne_zone else zone.diametre_nominal
        epaisseur_depart = premiere_ligne_zone.epaisseur_garnissage_utilisee if premiere_ligne_zone else Decimal("0")

        cellules = []
        for st in colonnes:
            disponible = st in zone.sous_types_disponibles()
            besoin = besoins_existants.get((zone.id, st.id))
            cellules.append({
                "sous_type": st,
                "disponible": disponible,
                "valeur": besoin.quantite_calculee if besoin else None,
            })

        lignes.append({
            "zone": zone,
            "diametre": diametre_depart,
            "epaisseur": epaisseur_depart,
            "cellules": cellules,
        })

    if request.method == "POST":
        if campagne.statut == "cloturee":
            messages.error(request, "Cette campagne est clôturée : impossible de modifier le calcul.")
            return redirect("core:campagne_detail", pk=campagne.pk)

        erreurs = []
        nb_calcules = 0
        for zone in zones:
            diametre_brut = request.POST.get(f"diametre_{zone.id}")
            epaisseur_brut = request.POST.get(f"epaisseur_{zone.id}")
            if not diametre_brut or not epaisseur_brut:
                continue
            try:
                diametre = Decimal(diametre_brut.replace(",", "."))
                epaisseur = Decimal(epaisseur_brut.replace(",", "."))
            except InvalidOperation:
                erreurs.append(f"{zone.nom} : diamètre ou épaisseur invalide.")
                continue

            for st in zone.sous_types_disponibles():
                ok, resultat = _calculer_besoin_pour_sous_type(campagne, zone, st, diametre, epaisseur)
                if ok:
                    nb_calcules += 1
                else:
                    erreurs.append(resultat)

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        if nb_calcules:
            messages.success(request, f"{nb_calcules} calcul(s) enregistré(s).")
        return redirect("core:campagne_tableau", pk=campagne.pk)

    return render(request, "core/campagne_tableau.html", {
        "campagne": campagne,
        "colonnes": colonnes,
        "lignes": lignes,
    })


@require_POST
def campagne_recalculer_zone_json(request, pk, zone_pk):
    """
    Recalcul en direct (appelé en JS à chaque frappe dans le tableau) : ne
    sauvegarde rien, renvoie juste les quantités pour affichage immédiat.
    Le calcul qui sera réellement enregistré passe toujours par la même
    fonction côté serveur au moment de la validation (campagne_tableau) —
    ceci n'est qu'un aperçu, jamais la source de vérité.
    """
    campagne = get_object_or_404(models.Campagne, pk=pk)
    zone = get_object_or_404(models.Zone, pk=zone_pk, campagnes=campagne)

    try:
        payload = json.loads(request.body)
        diametre = float(str(payload.get("diametre", "0")).replace(",", "."))
        epaisseur = float(str(payload.get("epaisseur", "0")).replace(",", "."))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"erreur": "Valeurs invalides."}, status=400)

    resultats = []
    for st in zone.sous_types_disponibles():
        base_variables = {
            "longueur_zone": float(zone.longueur),
            "epaisseur": epaisseur,
            "longueur": float(st.longueur),
            "largeur": float(st.largeur),
            "hauteur": float(st.hauteur),
            "taux_chute": float(st.taux_chute),
        }
        ok, resultat = evaluer_formule(st.formule_calcul, {**base_variables, "diametre": diametre})
        resultats.append({
            "sous_type_id": st.id,
            "ok": ok,
            "valeur": round(resultat, 2) if ok else None,
            "erreur": None if ok else str(resultat),
        })

    return JsonResponse({"resultats": resultats})


# ---------------------------------------------------------------------------
# Consommation réelle (ressaisie au poste — section 2 et 7)
# ---------------------------------------------------------------------------

def consommation_nouvelle(request, campagne_pk):
    campagne = get_object_or_404(models.Campagne, pk=campagne_pk)

    if campagne.statut == "cloturee":
        messages.error(request, "Cette campagne est clôturée : impossible d'ajouter une nouvelle consommation.")
        return redirect("core:campagne_detail", pk=campagne.pk)

    if request.method == "POST":
        form = forms.ConsommationReelleForm(request.POST, campagne=campagne)
        if form.is_valid():
            consommation = form.save(commit=False)
            consommation.campagne = campagne
            consommation.save()  # déclenche le signal : MouvementStock + Stock

            besoin = models.BesoinTheorique.objects.filter(
                campagne=campagne, zone=consommation.zone, sous_type_brique=consommation.sous_type_brique,
            ).first()
            if besoin:
                ecart = consommation.quantite_posee - besoin.quantite_calculee
                niveau = _classer_ecart(besoin.quantite_calculee, consommation.quantite_posee)
                messages.info(request, f"Écart immédiat pour cette saisie : {ecart:+.2f} pièces ({niveau}).")
            else:
                messages.warning(request, "Saisie enregistrée. Aucun besoin théorique calculé pour cette zone/sous-type à comparer.")

            stock = models.Stock.objects.filter(sous_type_brique=consommation.sous_type_brique).first()
            if stock and stock.negatif:
                messages.warning(
                    request,
                    f"Attention : le stock de « {consommation.sous_type_brique} » est maintenant négatif "
                    f"({stock.quantite_actuelle} pièces). Vérifiez l'ordre des saisies ou une éventuelle rupture réelle.",
                )

            messages.success(request, "Consommation réelle enregistrée et stock mis à jour.")
            return redirect("core:campagne_detail", pk=campagne.pk)
    else:
        form = forms.ConsommationReelleForm(campagne=campagne)

    return render(request, "core/consommation_form.html", {"form": form, "campagne": campagne})


# ---------------------------------------------------------------------------
# Stock magasin (section 7)
# ---------------------------------------------------------------------------

def stock_list(request):
    stocks = models.Stock.objects.select_related("sous_type_brique", "sous_type_brique__type_brique")
    return render(request, "core/stock_list.html", {"stocks": stocks})


def stock_entree(request):
    if request.method == "POST":
        form = forms.MouvementEntreeForm(request.POST)
        if form.is_valid():
            mouvement = form.save(commit=False)
            mouvement.type_mouvement = "entree"
            mouvement.save()

            stock, _ = models.Stock.objects.get_or_create(sous_type_brique=mouvement.sous_type_brique)
            stock.quantite_actuelle = stock.quantite_actuelle + mouvement.quantite
            stock.save(update_fields=["quantite_actuelle"])

            messages.success(request, "Entrée de stock enregistrée.")
            return redirect("core:stock_list")
    else:
        form = forms.MouvementEntreeForm()
    return render(request, "core/stock_entree_form.html", {"form": form})


def stock_ajustement(request):
    """
    Ajustement d'inventaire (casse, perte, écart de comptage physique) —
    distinct d'une entrée/sortie liée à une transaction réelle.
    """
    if request.method == "POST":
        form = forms.MouvementAjustementForm(request.POST)
        if form.is_valid():
            sous_type = form.cleaned_data["sous_type_brique"]
            quantite = form.cleaned_data["quantite"]
            motif = form.cleaned_data["motif"]

            models.MouvementStock.objects.create(
                sous_type_brique=sous_type, type_mouvement="ajustement",
                quantite=quantite, motif=motif,
            )
            stock, _ = models.Stock.objects.get_or_create(sous_type_brique=sous_type)
            stock.quantite_actuelle = stock.quantite_actuelle + quantite
            stock.save(update_fields=["quantite_actuelle"])

            messages.success(request, "Ajustement de stock enregistré.")
            return redirect("core:stock_list")
    else:
        form = forms.MouvementAjustementForm()
    return render(request, "core/stock_ajustement_form.html", {"form": form})


def mouvement_list(request):
    mouvements = models.MouvementStock.objects.select_related("sous_type_brique", "sous_type_brique__type_brique")
    return render(request, "core/mouvement_list.html", {"mouvements": mouvements})
