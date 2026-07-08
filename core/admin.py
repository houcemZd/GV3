from django.contrib import admin
from . import models


@admin.register(models.Four)
class FourAdmin(admin.ModelAdmin):
    list_display = ("nom", "statut")


class SousTypeBriqueInline(admin.TabularInline):
    model = models.SousTypeBrique
    extra = 0


@admin.register(models.TypeBrique)
class TypeBriqueAdmin(admin.ModelAdmin):
    list_display = ("nom", "fournisseur_defaut", "nb_sous_types")
    inlines = [SousTypeBriqueInline]

    def nb_sous_types(self, obj):
        return obj.sous_types.count()
    nb_sous_types.short_description = "Sous-types"


@admin.register(models.SousTypeBrique)
class SousTypeBriqueAdmin(admin.ModelAdmin):
    list_display = ("type_brique", "nom", "format", "taux_chute", "poids_unitaire")
    list_filter = ("format", "type_brique")


@admin.register(models.Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("four", "nom", "position", "diametre_nominal", "sous_type_brique_defaut")
    list_filter = ("four",)


@admin.register(models.Campagne)
class CampagneAdmin(admin.ModelAdmin):
    list_display = ("four", "date_debut", "date_fin", "statut")
    filter_horizontal = ("zones",)


@admin.register(models.BesoinTheorique)
class BesoinTheoriqueAdmin(admin.ModelAdmin):
    list_display = ("campagne", "zone", "sous_type_brique", "diametre_utilise", "quantite_calculee")


@admin.register(models.ConsommationReelle)
class ConsommationReelleAdmin(admin.ModelAdmin):
    list_display = ("campagne", "zone", "sous_type_brique", "quantite_posee", "date_saisie")


@admin.register(models.Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("sous_type_brique", "quantite_actuelle", "seuil_mini", "sous_seuil", "negatif")


@admin.register(models.MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ("sous_type_brique", "type_mouvement", "quantite", "date", "reference")
    list_filter = ("type_mouvement",)
