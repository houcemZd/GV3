from django import forms

from . import models


class FourForm(forms.ModelForm):
    class Meta:
        model = models.Four
        fields = ["nom", "statut"]


class ZoneForm(forms.ModelForm):
    sous_types_brique_autorises = forms.ModelMultipleChoiceField(
        queryset=models.SousTypeBrique.objects.select_related("type_brique"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Sous-types de briques autorisés pour cette zone",
        help_text="Si aucun n'est coché, tous les sous-types seront proposés lors du calcul (à configurer dès que possible).",
    )

    class Meta:
        model = models.Zone
        fields = ["four", "nom", "diametre_nominal", "longueur", "position", "sous_type_brique_defaut", "sous_types_brique_autorises"]


class TypeBriqueForm(forms.ModelForm):
    """Le type de brique est juste la famille (nom + fournisseur) — les
    dimensions, la formule et le taux de chute vivent sur les sous-types."""
    class Meta:
        model = models.TypeBrique
        fields = ["nom", "fournisseur_defaut"]


class SousTypeBriqueForm(forms.ModelForm):
    class Meta:
        model = models.SousTypeBrique
        fields = [
            "type_brique", "nom", "format", "longueur", "largeur", "hauteur",
            "poids_unitaire", "formule_calcul", "taux_chute", "sous_types_lies",
        ]
        widgets = {
            "formule_calcul": forms.Textarea(attrs={"rows": 3}),
            "sous_types_lies": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = models.SousTypeBrique.objects.select_related("type_brique")
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields["sous_types_lies"].queryset = queryset


class CampagneForm(forms.ModelForm):
    zones = forms.ModelMultipleChoiceField(
        queryset=models.Zone.objects.select_related("four"),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = models.Campagne
        fields = ["four", "date_debut", "date_fin", "statut", "zones"]
        widgets = {
            "date_debut": forms.DateInput(attrs={"type": "date"}),
            "date_fin": forms.DateInput(attrs={"type": "date"}),
        }


class CalculBesoinForm(forms.Form):
    """
    Formulaire de calcul du besoin théorique pour une zone d'une campagne.
    diametre_utilise / epaisseur_garnissage_utilisee sont pré-remplis mais
    modifiables (section 4 - géométrie figée par campagne).
    """
    sous_type_brique = forms.ModelChoiceField(
        queryset=models.SousTypeBrique.objects.select_related("type_brique"),
        label="Sous-type de brique",
    )
    diametre_utilise = forms.DecimalField(max_digits=10, decimal_places=2, label="Diamètre mesuré (mm)")
    epaisseur_garnissage_utilisee = forms.DecimalField(
        max_digits=10, decimal_places=2, label="Épaisseur de garnissage utilisée (mm)"
    )

    def __init__(self, *args, zone=None, **kwargs):
        super().__init__(*args, **kwargs)
        if zone is not None:
            self.fields["sous_type_brique"].queryset = zone.sous_types_disponibles()


class ConsommationReelleForm(forms.ModelForm):
    class Meta:
        model = models.ConsommationReelle
        fields = ["zone", "sous_type_brique", "quantite_posee", "commentaire"]
        widgets = {
            "commentaire": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, campagne=None, **kwargs):
        super().__init__(*args, **kwargs)
        if campagne is not None:
            self.fields["zone"].queryset = campagne.zones.all()
            sous_type_ids = set()
            for zone in campagne.zones.all():
                sous_type_ids.update(zone.sous_types_disponibles().values_list("id", flat=True))
            if sous_type_ids:
                self.fields["sous_type_brique"].queryset = models.SousTypeBrique.objects.filter(id__in=sous_type_ids)


class MouvementEntreeForm(forms.ModelForm):
    class Meta:
        model = models.MouvementStock
        fields = ["sous_type_brique", "quantite", "reference", "fournisseur_lot"]


class MouvementAjustementForm(forms.Form):
    """
    Ajustement d'inventaire (perte, casse, écart de comptage physique) —
    distinct d'une entrée ou d'une sortie liée à une transaction réelle.
    """
    sous_type_brique = forms.ModelChoiceField(queryset=models.SousTypeBrique.objects.select_related("type_brique"))
    quantite = forms.DecimalField(
        max_digits=10, decimal_places=2,
        label="Ajustement (pièces)",
        help_text="Positif pour ajouter, négatif pour retirer. Ex : -12 pour signaler 12 pièces cassées.",
    )
    motif = forms.CharField(
        max_length=255, label="Motif (obligatoire)",
        help_text="Ex : casse constatée, écart d'inventaire physique, erreur de saisie précédente...",
    )
