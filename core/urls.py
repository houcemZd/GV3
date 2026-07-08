from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("fours/", views.four_list, name="four_list"),
    path("fours/nouveau/", views.four_form, name="four_create"),
    path("fours/<int:pk>/modifier/", views.four_form, name="four_update"),
    path("fours/<int:pk>/supprimer/", views.four_delete, name="four_delete"),

    path("zones/", views.zone_list, name="zone_list"),
    path("zones/nouveau/", views.zone_form, name="zone_create"),
    path("zones/<int:pk>/modifier/", views.zone_form, name="zone_update"),
    path("zones/<int:pk>/supprimer/", views.zone_delete, name="zone_delete"),

    path("types-briques/", views.type_brique_list, name="type_brique_list"),
    path("types-briques/nouveau/", views.type_brique_form, name="type_brique_create"),
    path("types-briques/<int:pk>/modifier/", views.type_brique_form, name="type_brique_update"),
    path("types-briques/<int:pk>/supprimer/", views.type_brique_delete, name="type_brique_delete"),

    path("formules/", views.formule_list, name="formule_list"),
    path("formules/nouvelle/", views.formule_form, name="formule_create"),
    path("formules/<int:pk>/modifier/", views.formule_form, name="formule_update"),
    path("formules/<int:pk>/supprimer/", views.formule_delete, name="formule_delete"),

    path("sous-types-briques/", views.sous_type_list, name="sous_type_list"),
    path("sous-types-briques/nouveau/", views.sous_type_form, name="sous_type_create"),
    path("sous-types-briques/<int:pk>/modifier/", views.sous_type_form, name="sous_type_update"),
    path("sous-types-briques/<int:pk>/supprimer/", views.sous_type_delete, name="sous_type_delete"),

    path("campagnes/", views.campagne_list, name="campagne_list"),
    path("campagnes/nouvelle/", views.campagne_form, name="campagne_create"),
    path("campagnes/<int:pk>/", views.campagne_detail, name="campagne_detail"),
    path("campagnes/<int:pk>/zones/<int:zone_pk>/calculer/", views.campagne_calculer_besoin, name="campagne_calculer_besoin"),
    path("campagnes/<int:pk>/tableau/", views.campagne_tableau, name="campagne_tableau"),
    path("campagnes/<int:pk>/zones/<int:zone_pk>/recalculer.json", views.campagne_recalculer_zone_json, name="campagne_recalculer_zone_json"),
    path("campagnes/<int:campagne_pk>/consommation/nouvelle/", views.consommation_nouvelle, name="consommation_create"),

    path("stock/", views.stock_list, name="stock_list"),
    path("stock/entree/", views.stock_entree, name="stock_entree"),
    path("stock/ajustement/", views.stock_ajustement, name="stock_ajustement"),
    path("stock/mouvements/", views.mouvement_list, name="mouvement_list"),
]
