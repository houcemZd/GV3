import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class Four(models.Model):
    STATUT_CHOICES = [
        ("marche", "En marche"),
        ("arret", "À l'arrêt"),
        ("refection", "En réfection"),
    ]
    nom = models.CharField(max_length=100)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="marche")

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class TypeBrique(models.Model):
    """
    Famille de briques réfractaires (ex. "Brique isolante zone cuisson").
    Un type de brique regroupe généralement plusieurs sous-types (souvent 4)
    qui partagent le même fournisseur. Les formules ST-1..ST-4 sont définies
    ici et appliquées automatiquement aux sous-types correspondants.
    """
    nom = models.CharField(max_length=100)
    fournisseur_defaut = models.CharField(max_length=150, blank=True)
    formule_sous_type_1 = models.ForeignKey(
        "Formule", on_delete=models.PROTECT, null=True, blank=True, related_name="types_briques_st1"
    )
    formule_sous_type_2 = models.ForeignKey(
        "Formule", on_delete=models.PROTECT, null=True, blank=True, related_name="types_briques_st2"
    )
    formule_sous_type_3 = models.ForeignKey(
        "Formule", on_delete=models.PROTECT, null=True, blank=True, related_name="types_briques_st3"
    )
    formule_sous_type_4 = models.ForeignKey(
        "Formule", on_delete=models.PROTECT, null=True, blank=True, related_name="types_briques_st4"
    )

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def clean(self):
        super().clean()
        formules = [
            self.formule_sous_type_1,
            self.formule_sous_type_2,
            self.formule_sous_type_3,
            self.formule_sous_type_4,
        ]
        if any(formules) and not all(formules):
            raise ValidationError("Les 4 sous-types ST-1 à ST-4 doivent tous avoir une formule.")
        if all(formules):
            ids = [f.id for f in formules if f]
            if len(set(ids)) != 4:
                raise ValidationError("Chaque sous-type ST-1 à ST-4 doit avoir une formule différente.")

    def formule_pour_sous_type_nom(self, nom):
        match = re.match(r"^\s*ST[-\s]?([1-4])\s*$", nom or "", flags=re.IGNORECASE)
        if not match:
            return None
        return getattr(self, f"formule_sous_type_{match.group(1)}", None)

    def formule_mapping(self):
        return [
            ("ST-1", self.formule_sous_type_1),
            ("ST-2", self.formule_sous_type_2),
            ("ST-3", self.formule_sous_type_3),
            ("ST-4", self.formule_sous_type_4),
        ]


class Formule(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    expression = models.TextField(
        help_text=(
            "Variables disponibles : diametre, longueur_zone, epaisseur, longueur, "
            "largeur, hauteur, taux_chute, PI."
        )
    )

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class SousTypeBrique(models.Model):
    """
    Variante dimensionnelle d'un TypeBrique (généralement 4 par type).
    Chaque sous-type a ses propres dimensions, sa propre formule de calcul
    (section 6) et son propre taux de chute à la découpe (section 8) — c'est
    à ce niveau, et non au niveau du TypeBrique, que le calcul du besoin,
    le stock et la consommation réelle sont suivis.
    """
    FORMAT_CHOICES = [
        ("droite", "Droite"),
        ("cintree", "Cintrée"),
        ("speciale", "Spéciale"),
    ]

    type_brique = models.ForeignKey(TypeBrique, on_delete=models.CASCADE, related_name="sous_types")
    nom = models.CharField(max_length=100, help_text="Ex. : ST-1, Position clé, Petit format...")
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default="droite")
    longueur = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm")
    largeur = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm")
    hauteur = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm")
    poids_unitaire = models.DecimalField(max_digits=10, decimal_places=3, help_text="kg")

    formule_predefinie = models.ForeignKey(
        Formule, on_delete=models.PROTECT, null=True, blank=True, related_name="sous_types"
    )
    formule_calcul = models.TextField(
        blank=True,
        help_text=(
            "Expression libre. Variables disponibles : diametre, longueur_zone, "
            "epaisseur, longueur, largeur, hauteur, taux_chute, PI. "
            "Ex : (PI * diametre * longueur_zone) / (largeur * hauteur) * (1 + taux_chute)"
        )
    )
    taux_chute = models.DecimalField(
        max_digits=5, decimal_places=4, default=0,
        validators=[MinValueValidator(0)],
        help_text="Coefficient de perte à la découpe, ex. 0.08 pour 8%. 0 par défaut pour les sous-types droits.",
    )
    sous_types_lies = models.ManyToManyField(
        "self", blank=True,
        help_text=(
            "Sous-types toujours utilisés ensemble avec celui-ci (ex. deux formes "
            "trapézoïdales X/Y alternées dans le même anneau). Relation symétrique : "
            "lier X à Y suffit, Y sera automatiquement lié à X."
        ),
    )

    class Meta:
        ordering = ["type_brique", "nom"]
        unique_together = ("type_brique", "nom")

    def __str__(self):
        return f"{self.type_brique.nom} — {self.nom} ({self.get_format_display()})"

    def get_absolute_url(self):
        return reverse("core:sous_type_detail", args=[self.pk])

    def clean(self):
        super().clean()
        formule_type = None
        if self.type_brique_id and self.nom:
            formule_type = self.type_brique.formule_pour_sous_type_nom(self.nom)
        if formule_type and not self.formule_predefinie_id:
            self.formule_predefinie = formule_type
        if self.formule_predefinie_id:
            self.formule_calcul = self.formule_predefinie.expression
        if not self.formule_calcul or not self.formule_calcul.strip():
            raise ValidationError({"formule_calcul": "Veuillez saisir une formule ou sélectionner une formule prédéfinie."})

        # Si les dimensions ne sont pas encore renseignées, on laisse les
        # erreurs "champ requis" normales s'afficher sans tester la formule.
        if self.longueur is None or self.largeur is None or self.hauteur is None:
            return

        from .formula import VALEURS_EXEMPLE, evaluer_formule

        variables = {
            **VALEURS_EXEMPLE,
            "longueur": float(self.longueur),
            "largeur": float(self.largeur),
            "hauteur": float(self.hauteur),
            "taux_chute": float(self.taux_chute or 0),
        }
        ok, resultat = evaluer_formule(self.formule_calcul, variables)
        if not ok:
            raise ValidationError({"formule_calcul": f"Formule invalide (testée avec les valeurs d'exemple) : {resultat}"})


class Zone(models.Model):
    """
    Une zone du four. diametre_nominal est la valeur de conception d'origine,
    figée dans le temps : elle sert de référence "sans dérive" pour comparer
    au diamètre réellement mesuré à chaque campagne (cf. BesoinTheorique et
    section 8 - usure progressive / géométrie conique).
    """
    four = models.ForeignKey(Four, on_delete=models.CASCADE, related_name="zones")
    nom = models.CharField(max_length=100)
    diametre_nominal = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm (valeur de conception, ne change pas)")
    longueur = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm")
    position = models.PositiveIntegerField(help_text="Ordre / position dans le four")
    sous_type_brique_defaut = models.ForeignKey(
        SousTypeBrique, on_delete=models.SET_NULL, null=True, blank=True, related_name="zones_defaut"
    )
    sous_types_brique_autorises = models.ManyToManyField(
        SousTypeBrique, related_name="zones_autorisees", blank=True,
        help_text="Sous-types utilisables dans cette zone. Si vide, tous les sous-types sont proposés (à configurer).",
    )

    class Meta:
        ordering = ["four", "position"]

    def __str__(self):
        return f"{self.four.nom} — {self.nom}"

    def get_absolute_url(self):
        return reverse("core:zone_detail", args=[self.pk])

    def sous_types_disponibles(self):
        if self.sous_types_brique_autorises.exists():
            return self.sous_types_brique_autorises.all()
        return SousTypeBrique.objects.all()


class Campagne(models.Model):
    STATUT_CHOICES = [
        ("en_cours", "En cours"),
        ("cloturee", "Clôturée"),
    ]
    # PROTECT : un four ayant déjà des campagnes ne doit pas pouvoir être
    # supprimé, cela détruirait tout l'historique théorique/réel associé.
    four = models.ForeignKey(Four, on_delete=models.PROTECT, related_name="campagnes")
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="en_cours")
    zones = models.ManyToManyField(Zone, related_name="campagnes")

    class Meta:
        ordering = ["-date_debut"]

    def __str__(self):
        return f"Campagne {self.four.nom} — {self.date_debut}"

    def get_absolute_url(self):
        return reverse("core:campagne_detail", args=[self.pk])


class BesoinTheorique(models.Model):
    """
    diametre_utilise / epaisseur_garnissage_utilisee : valeurs mesurées,
    saisies au moment du calcul (pré-remplies depuis la Zone, modifiables).

    quantite_calculee : besoin calculé avec la géométrie réellement mesurée
    (avec dérive / usure prise en compte).
    quantite_calculee_nominale : le même calcul, mais avec le diamètre
    nominal de conception de la Zone à la place du diamètre mesuré — isole
    l'effet de l'usure du reste de l'écart théorique/réel (section 8).
    """
    campagne = models.ForeignKey(Campagne, on_delete=models.CASCADE, related_name="besoins")
    # PROTECT : empêche de supprimer une Zone qui a un historique de calcul.
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name="besoins")
    sous_type_brique = models.ForeignKey(SousTypeBrique, on_delete=models.PROTECT, related_name="besoins")
    diametre_utilise = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm (mesuré)")
    epaisseur_garnissage_utilisee = models.DecimalField(max_digits=10, decimal_places=2, help_text="mm")
    quantite_calculee = models.DecimalField(max_digits=10, decimal_places=2, help_text="pièces, avec dérive (mesure réelle)")
    quantite_calculee_nominale = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="pièces, sans dérive (diamètre nominal de la zone)"
    )

    class Meta:
        unique_together = ("campagne", "zone", "sous_type_brique")
        ordering = ["campagne", "zone"]

    def __str__(self):
        return f"{self.campagne} — {self.zone.nom} — {self.sous_type_brique}"

    @property
    def impact_derive(self):
        """Part de l'écart attribuable à la seule dérive géométrique."""
        return self.quantite_calculee - self.quantite_calculee_nominale


class ConsommationReelle(models.Model):
    """
    Ressaisie au poste depuis un relevé papier (section 2).
    """
    campagne = models.ForeignKey(Campagne, on_delete=models.CASCADE, related_name="consommations")
    # PROTECT : même raison que sur BesoinTheorique.
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name="consommations")
    sous_type_brique = models.ForeignKey(SousTypeBrique, on_delete=models.PROTECT, related_name="consommations")
    quantite_posee = models.DecimalField(max_digits=10, decimal_places=2, help_text="pièces")
    commentaire = models.TextField(blank=True, help_text="Anomalie éventuelle")
    date_saisie = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_saisie"]

    def __str__(self):
        return f"{self.campagne} — {self.zone.nom} — {self.sous_type_brique} : {self.quantite_posee}"


class Stock(models.Model):
    sous_type_brique = models.OneToOneField(SousTypeBrique, on_delete=models.CASCADE, related_name="stock")
    quantite_actuelle = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="pièces")
    seuil_mini = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="pièces")

    def __str__(self):
        return f"Stock {self.sous_type_brique} : {self.quantite_actuelle}"

    @property
    def sous_seuil(self):
        return self.quantite_actuelle < self.seuil_mini

    @property
    def negatif(self):
        return self.quantite_actuelle < 0


class MouvementStock(models.Model):
    TYPE_CHOICES = [
        ("entree", "Entrée"),
        ("sortie", "Sortie"),
        ("ajustement", "Ajustement (inventaire)"),
    ]
    sous_type_brique = models.ForeignKey(SousTypeBrique, on_delete=models.PROTECT, related_name="mouvements")
    type_mouvement = models.CharField(max_length=10, choices=TYPE_CHOICES)
    # Signée : positive pour entrée/ajustement à la hausse, négative pour
    # sortie/ajustement à la baisse. Permet un historique cohérent quel que
    # soit le type de mouvement.
    quantite = models.DecimalField(max_digits=10, decimal_places=2, help_text="pièces (signée)")
    date = models.DateTimeField(auto_now_add=True)
    reference = models.CharField(max_length=150, blank=True, help_text="Campagne ou bon de réception")
    fournisseur_lot = models.CharField(max_length=150, blank=True)
    motif = models.CharField(max_length=255, blank=True, help_text="Obligatoire pour un ajustement d'inventaire")

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_type_mouvement_display()} — {self.sous_type_brique} — {self.quantite}"
