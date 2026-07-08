from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import Client, TestCase

from . import models
from .formula import evaluer_formule


class FormuleEvaluatorTests(TestCase):
    def test_formule_valide(self):
        ok, resultat = evaluer_formule(
            "(PI * diametre * longueur_zone) / (largeur * hauteur) * (1 + taux_chute)",
            {"diametre": 3000, "longueur_zone": 1000, "largeur": 150, "hauteur": 80, "taux_chute": 0.08},
        )
        self.assertTrue(ok)
        self.assertAlmostEqual(resultat, 848.23, places=1)

    def test_division_par_zero(self):
        ok, _ = evaluer_formule("diametre / 0", {"diametre": 10})
        self.assertFalse(ok)

    def test_variable_inconnue(self):
        ok, _ = evaluer_formule("diametre + inconnue", {"diametre": 10})
        self.assertFalse(ok)

    def test_resultat_negatif_rejete(self):
        ok, _ = evaluer_formule("-diametre", {"diametre": 10})
        self.assertFalse(ok)

    def test_virgule_decimale_francaise_acceptee(self):
        """
        "3,14" doit être compris comme 3.14, pas comme le tuple (3, 14) —
        bug remonté avec une vraie formule utilisateur (division par un
        tuple, TypeError cryptique côté Python).
        """
        ok, resultat = evaluer_formule(
            "(3,14*(diametre*(longueur-largeur)-2*hauteur*longueur))/((longueur*69)-(74*largeur))+0,6",
            {"diametre": 4500, "longueur": 200, "largeur": 66.5, "hauteur": 76.5},
        )
        self.assertTrue(ok)
        self.assertAlmostEqual(resultat, 202.23, places=1)


class TypeSousTypeStructureTests(TestCase):
    """
    Un TypeBrique est une famille ; chaque SousTypeBrique porte ses propres
    dimensions, formule et taux de chute (généralement 4 sous-types par type).
    """
    def test_un_type_peut_avoir_plusieurs_sous_types(self):
        type_brique = models.TypeBrique.objects.create(nom="Brique isolante A", fournisseur_defaut="ACME")
        for i in range(4):
            models.SousTypeBrique.objects.create(
                type_brique=type_brique, nom=f"ST-{i+1}", format="droite",
                longueur=300 + i * 10, largeur=150, hauteur=80, poids_unitaire=5,
                formule_calcul="diametre",
            )
        self.assertEqual(type_brique.sous_types.count(), 4)

    def test_sous_types_ont_formule_et_taux_chute_independants(self):
        type_brique = models.TypeBrique.objects.create(nom="Brique B")
        st1 = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="ST-1", format="droite",
            longueur=300, largeur=150, hauteur=80, poids_unitaire=5,
            formule_calcul="diametre", taux_chute=0,
        )
        st2 = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="ST-2", format="cintree",
            longueur=280, largeur=140, hauteur=75, poids_unitaire=4.5,
            formule_calcul="diametre * 2", taux_chute=Decimal("0.08"),
        )
        self.assertNotEqual(st1.formule_calcul, st2.formule_calcul)
        self.assertNotEqual(st1.taux_chute, st2.taux_chute)


class SousTypeBriqueValidationTests(TestCase):
    """La validation de la formule vit dans SousTypeBrique.clean(), donc
    s'applique quel que soit le point d'entrée (formulaire OU admin)."""

    def setUp(self):
        self.type_brique = models.TypeBrique.objects.create(nom="Brique test")

    def test_formule_invalide_rejetee_au_niveau_modele(self):
        sous_type = models.SousTypeBrique(
            type_brique=self.type_brique, nom="ST-1", format="droite",
            longueur=300, largeur=150, hauteur=80, poids_unitaire=5,
            formule_calcul="diametre / 0",
        )
        with self.assertRaises(ValidationError):
            sous_type.full_clean()

    def test_formule_valide_acceptee(self):
        sous_type = models.SousTypeBrique(
            type_brique=self.type_brique, nom="ST-1", format="droite",
            longueur=300, largeur=150, hauteur=80, poids_unitaire=5,
            formule_calcul="(PI * diametre * longueur_zone) / (largeur * hauteur)",
        )
        sous_type.full_clean()
        sous_type.save()
        self.assertTrue(models.SousTypeBrique.objects.filter(nom="ST-1").exists())


class ProtectedDeleteTests(TestCase):
    def setUp(self):
        self.four = models.Four.objects.create(nom="Four 1")
        self.zone = models.Zone.objects.create(
            four=self.four, nom="Zone A", diametre_nominal=3000, longueur=1000, position=1,
        )
        type_brique = models.TypeBrique.objects.create(nom="Brique A")
        self.sous_type = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="ST-1", longueur=300, largeur=150, hauteur=80,
            poids_unitaire=5, formule_calcul="diametre",
        )
        self.campagne = models.Campagne.objects.create(four=self.four, date_debut="2026-01-01")
        self.campagne.zones.add(self.zone)
        models.BesoinTheorique.objects.create(
            campagne=self.campagne, zone=self.zone, sous_type_brique=self.sous_type,
            diametre_utilise=2950, epaisseur_garnissage_utilisee=180,
            quantite_calculee=800, quantite_calculee_nominale=810,
        )

    def test_zone_avec_historique_ne_peut_pas_etre_supprimee(self):
        with self.assertRaises(ProtectedError):
            self.zone.delete()

    def test_four_avec_campagne_ne_peut_pas_etre_supprime(self):
        with self.assertRaises(ProtectedError):
            self.four.delete()

    def test_sous_type_avec_historique_ne_peut_pas_etre_supprime(self):
        with self.assertRaises(ProtectedError):
            self.sous_type.delete()


class GeometrieDeriveTests(TestCase):
    def test_besoin_stocke_les_deux_valeurs(self):
        four = models.Four.objects.create(nom="Four 1")
        zone = models.Zone.objects.create(
            four=four, nom="Zone A", diametre_nominal=3000, longueur=1000, position=1,
        )
        type_brique = models.TypeBrique.objects.create(nom="Brique A")
        sous_type = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="ST-1", longueur=300, largeur=150, hauteur=80,
            poids_unitaire=5, formule_calcul="diametre",
        )
        campagne = models.Campagne.objects.create(four=four, date_debut="2026-01-01")
        campagne.zones.add(zone)

        besoin = models.BesoinTheorique.objects.create(
            campagne=campagne, zone=zone, sous_type_brique=sous_type,
            diametre_utilise=2950, epaisseur_garnissage_utilisee=180,
            quantite_calculee=2950, quantite_calculee_nominale=3000,
        )
        self.assertEqual(besoin.impact_derive, Decimal("-50"))


class ConsommationSignalTests(TestCase):
    def setUp(self):
        self.four = models.Four.objects.create(nom="Four 1")
        self.zone = models.Zone.objects.create(
            four=self.four, nom="Zone A", diametre_nominal=3000, longueur=1000, position=1,
        )
        type_brique = models.TypeBrique.objects.create(nom="Brique A")
        self.sous_type = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="ST-1", longueur=300, largeur=150, hauteur=80,
            poids_unitaire=5, formule_calcul="diametre",
        )
        self.campagne = models.Campagne.objects.create(four=self.four, date_debut="2026-01-01")
        self.campagne.zones.add(self.zone)

    def test_consommation_alimente_mouvement_et_stock(self):
        models.ConsommationReelle.objects.create(
            campagne=self.campagne, zone=self.zone, sous_type_brique=self.sous_type, quantite_posee=100,
        )
        stock = models.Stock.objects.get(sous_type_brique=self.sous_type)
        self.assertEqual(stock.quantite_actuelle, Decimal("-100"))
        self.assertTrue(stock.negatif)
        mouvement = models.MouvementStock.objects.get()
        self.assertEqual(mouvement.type_mouvement, "sortie")
        self.assertEqual(mouvement.quantite, Decimal("-100"))

    def test_ajustement_positif_et_negatif(self):
        stock, _ = models.Stock.objects.get_or_create(sous_type_brique=self.sous_type)
        stock.quantite_actuelle = Decimal("100")
        stock.save()

        models.MouvementStock.objects.create(
            sous_type_brique=self.sous_type, type_mouvement="ajustement",
            quantite=Decimal("-15"), motif="casse constatée",
        )
        mouvement = models.MouvementStock.objects.get(type_mouvement="ajustement")
        self.assertEqual(mouvement.quantite, Decimal("-15"))
        self.assertEqual(mouvement.motif, "casse constatée")


class SousTypePaireTests(TestCase):
    """
    X et Y (ex. paire trapézoïdale toujours utilisée ensemble) : lier les
    deux doit suffire dans un sens (relation symétrique), et calculer le
    besoin pour l'un doit automatiquement calculer l'autre.
    """
    def setUp(self):
        self.client = Client()
        self.four = models.Four.objects.create(nom="Four 1")
        self.zone = models.Zone.objects.create(
            four=self.four, nom="Zone A", diametre_nominal=4500, longueur=2000, position=1,
        )
        type_brique = models.TypeBrique.objects.create(nom="Brique trapezoidale")
        self.brique_x = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="X", format="cintree",
            longueur=200, largeur=66.5, hauteur=76.5, poids_unitaire=8.35,
            formule_calcul="diametre / longueur",
        )
        self.brique_y = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="Y", format="cintree",
            longueur=200, largeur=69, hauteur=74, poids_unitaire=8.6,
            formule_calcul="diametre / longueur * 1.05",
        )
        self.brique_x1 = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="X1", format="cintree",
            longueur=198, largeur=67, hauteur=76, poids_unitaire=8.2,
            formule_calcul="diametre / longueur * 0.98",
        )
        self.brique_y1 = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="Y1", format="cintree",
            longueur=202, largeur=70, hauteur=75, poids_unitaire=8.4,
            formule_calcul="diametre / longueur * 1.02",
        )
        self.brique_x.sous_types_lies.add(self.brique_y)

        self.campagne = models.Campagne.objects.create(four=self.four, date_debut="2026-01-01")
        self.campagne.zones.add(self.zone)

    def test_relation_symetrique(self):
        # On n'a lié que X -> Y explicitement ; Y doit automatiquement voir X.
        self.assertIn(self.brique_x, self.brique_y.sous_types_lies.all())

    def test_calculer_besoin_pour_x_calcule_aussi_y(self):
        response = self.client.post(
            f"/campagnes/{self.campagne.id}/zones/{self.zone.id}/calculer/",
            {"sous_type_brique": self.brique_x.id, "diametre_utilise": "4500", "epaisseur_garnissage_utilisee": "200"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(models.BesoinTheorique.objects.filter(sous_type_brique=self.brique_x).exists())
        self.assertTrue(
            models.BesoinTheorique.objects.filter(sous_type_brique=self.brique_y).exists(),
            "Le sous-type lié Y aurait dû être calculé automatiquement avec X",
        )

    def test_calculer_besoin_pour_x_calcule_toute_la_famille(self):
        response = self.client.post(
            f"/campagnes/{self.campagne.id}/zones/{self.zone.id}/calculer/",
            {"sous_type_brique": self.brique_x.id, "diametre_utilise": "4500", "epaisseur_garnissage_utilisee": "200"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(models.BesoinTheorique.objects.filter(sous_type_brique=self.brique_x1).exists())
        self.assertTrue(models.BesoinTheorique.objects.filter(sous_type_brique=self.brique_y1).exists())

    def test_pas_de_paire_manquante_apres_calcul(self):
        self.client.post(
            f"/campagnes/{self.campagne.id}/zones/{self.zone.id}/calculer/",
            {"sous_type_brique": self.brique_x.id, "diametre_utilise": "4500", "epaisseur_garnissage_utilisee": "200"},
        )
        response = self.client.get(f"/campagnes/{self.campagne.id}/")
        self.assertNotContains(response, "Paire de sous-types incomplète")


class SchemaZonesTests(TestCase):
    """Écran 'Configuration four' — schéma visuel simple des zones (section 7 du cahier)."""

    def test_schema_proportionnel_et_sans_valeurs_negatives(self):
        client = Client()
        four = models.Four.objects.create(nom="Four 1")
        models.Zone.objects.create(four=four, nom="Préchauffage", diametre_nominal=3200, longueur=3000, position=1)
        models.Zone.objects.create(four=four, nom="Cuisson", diametre_nominal=4500, longueur=8000, position=2)

        response = client.get("/zones/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("<svg", body)
        self.assertIn("Préchauffage", body)
        self.assertIn("Cuisson", body)
        # La zone la plus longue (Cuisson) doit être visuellement plus large.
        self.assertGreater(body.index("Cuisson"), body.index("Préchauffage"))

    def test_pas_de_schema_si_aucune_zone(self):
        client = Client()
        models.Four.objects.create(nom="Four vide")
        response = client.get("/zones/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<svg", response.content.decode())


class CampagneTableauTests(TestCase):
    """Écran unique 'tableur' : toutes les zones, colonnes dynamiques par sous-type."""

    def setUp(self):
        self.client = Client()
        self.four = models.Four.objects.create(nom="Four 1")
        self.z1 = models.Zone.objects.create(four=self.four, nom="Zone A", diametre_nominal=4500, longueur=2000, position=1)
        self.z2 = models.Zone.objects.create(four=self.four, nom="Zone B", diametre_nominal=3800, longueur=1500, position=2)
        tb = models.TypeBrique.objects.create(nom="Brique")
        self.x = models.SousTypeBrique.objects.create(
            type_brique=tb, nom="X", longueur=200, largeur=66.5, hauteur=76.5, poids_unitaire=8.35,
            formule_calcul="(PI*diametre*longueur_zone)/(largeur*hauteur)",
        )
        self.y = models.SousTypeBrique.objects.create(
            type_brique=tb, nom="Y", longueur=200, largeur=69, hauteur=74, poids_unitaire=8.6,
            formule_calcul="(PI*diametre*longueur_zone)/(largeur*hauteur)*1.03",
        )
        self.x.sous_types_lies.add(self.y)
        self.campagne = models.Campagne.objects.create(four=self.four, date_debut="2026-07-01")
        self.campagne.zones.add(self.z1, self.z2)

    def test_tableau_affiche_toutes_les_zones_et_colonnes(self):
        response = self.client.get(f"/campagnes/{self.campagne.id}/tableau/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Zone A", body)
        self.assertIn("Zone B", body)

    def test_recalcul_json_ne_sauvegarde_rien(self):
        response = self.client.post(
            f"/campagnes/{self.campagne.id}/zones/{self.z1.id}/recalculer.json",
            data='{"diametre": "4500", "epaisseur": "200"}', content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["resultats"]), 2)
        self.assertTrue(all(r["ok"] for r in data["resultats"]))
        self.assertEqual(models.BesoinTheorique.objects.count(), 0)

    def test_enregistrer_tout_calcule_toutes_zones_et_sous_types(self):
        response = self.client.post(f"/campagnes/{self.campagne.id}/tableau/", {
            f"diametre_{self.z1.id}": "4500", f"epaisseur_{self.z1.id}": "200",
            f"diametre_{self.z2.id}": "3800", f"epaisseur_{self.z2.id}": "180",
        })
        self.assertEqual(response.status_code, 302)
        # 2 zones x 2 sous-types = 4 BesoinTheorique, X et Y inclus pour chacune.
        self.assertEqual(models.BesoinTheorique.objects.count(), 4)
        self.assertTrue(models.BesoinTheorique.objects.filter(zone=self.z1, sous_type_brique=self.y).exists())

    def test_tableau_bloque_si_campagne_cloturee(self):
        self.campagne.statut = "cloturee"
        self.campagne.save()
        self.client.post(f"/campagnes/{self.campagne.id}/tableau/", {
            f"diametre_{self.z1.id}": "9999", f"epaisseur_{self.z1.id}": "1",
        })
        self.assertEqual(models.BesoinTheorique.objects.count(), 0)


class CampagneClotureeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.four = models.Four.objects.create(nom="Four 1")
        self.zone = models.Zone.objects.create(
            four=self.four, nom="Zone A", diametre_nominal=3000, longueur=1000, position=1,
        )
        type_brique = models.TypeBrique.objects.create(nom="Brique A")
        self.sous_type = models.SousTypeBrique.objects.create(
            type_brique=type_brique, nom="ST-1", longueur=300, largeur=150, hauteur=80,
            poids_unitaire=5, formule_calcul="diametre",
        )
        self.campagne = models.Campagne.objects.create(
            four=self.four, date_debut="2026-01-01", statut="cloturee",
        )
        self.campagne.zones.add(self.zone)

    def test_calcul_besoin_refuse_si_cloturee(self):
        response = self.client.post(
            f"/campagnes/{self.campagne.id}/zones/{self.zone.id}/calculer/",
            {"sous_type_brique": self.sous_type.id, "diametre_utilise": "2950", "epaisseur_garnissage_utilisee": "180"},
        )
        self.assertEqual(models.BesoinTheorique.objects.count(), 0)
        self.assertRedirects(response, f"/campagnes/{self.campagne.id}/")

    def test_consommation_refusee_si_cloturee(self):
        response = self.client.post(
            f"/campagnes/{self.campagne.id}/consommation/nouvelle/",
            {"zone": self.zone.id, "sous_type_brique": self.sous_type.id, "quantite_posee": "100"},
        )
        self.assertEqual(models.ConsommationReelle.objects.count(), 0)
        self.assertRedirects(response, f"/campagnes/{self.campagne.id}/")


class FormulesTypeBriqueTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.f1 = models.Formule.objects.create(nom="F1", expression="diametre")
        self.f2 = models.Formule.objects.create(nom="F2", expression="diametre * 1.01")
        self.f3 = models.Formule.objects.create(nom="F3", expression="diametre * 1.02")
        self.f4 = models.Formule.objects.create(nom="F4", expression="diametre * 1.03")

    def test_creation_type_brique_avec_4_formules(self):
        response = self.client.post("/types-briques/nouveau/", {
            "nom": "Type Configuré",
            "fournisseur_defaut": "ACME",
            "formule_sous_type_1": self.f1.id,
            "formule_sous_type_2": self.f2.id,
            "formule_sous_type_3": self.f3.id,
            "formule_sous_type_4": self.f4.id,
        })
        self.assertEqual(response.status_code, 302)
        tb = models.TypeBrique.objects.get(nom="Type Configuré")
        self.assertEqual(tb.formule_sous_type_1, self.f1)
        self.assertEqual(tb.formule_sous_type_4, self.f4)

    def test_refus_si_formules_dupliquees_sur_les_4_slots(self):
        response = self.client.post("/types-briques/nouveau/", {
            "nom": "Type invalide",
            "fournisseur_defaut": "ACME",
            "formule_sous_type_1": self.f1.id,
            "formule_sous_type_2": self.f1.id,
            "formule_sous_type_3": self.f3.id,
            "formule_sous_type_4": self.f4.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chaque sous-type ST-1 à ST-4 doit avoir une formule différente")

    def test_sous_type_st_herite_automatiquement_de_la_formule_du_type(self):
        tb = models.TypeBrique.objects.create(
            nom="Type A",
            formule_sous_type_1=self.f1,
            formule_sous_type_2=self.f2,
            formule_sous_type_3=self.f3,
            formule_sous_type_4=self.f4,
        )
        sous_type = models.SousTypeBrique(
            type_brique=tb,
            nom="ST-1",
            format="droite",
            longueur=300,
            largeur=150,
            hauteur=80,
            poids_unitaire=5,
            formule_calcul="",
        )
        sous_type.full_clean()
        sous_type.save()
        self.assertEqual(sous_type.formule_predefinie, self.f1)
        self.assertEqual(sous_type.formule_calcul, self.f1.expression)

    def test_calcul_besoin_fonctionne_avec_formule_predefinie(self):
        four = models.Four.objects.create(nom="Four 1")
        zone = models.Zone.objects.create(
            four=four, nom="Zone A", diametre_nominal=3000, longueur=1000, position=1,
        )
        tb = models.TypeBrique.objects.create(
            nom="Type B",
            formule_sous_type_1=self.f1,
            formule_sous_type_2=self.f2,
            formule_sous_type_3=self.f3,
            formule_sous_type_4=self.f4,
        )
        st1 = models.SousTypeBrique(
            type_brique=tb, nom="ST-1", longueur=300, largeur=150, hauteur=80,
            poids_unitaire=5, formule_calcul="",
        )
        st1.full_clean()
        st1.save()
        campagne = models.Campagne.objects.create(four=four, date_debut="2026-01-01")
        campagne.zones.add(zone)

        response = self.client.post(
            f"/campagnes/{campagne.id}/zones/{zone.id}/calculer/",
            {"sous_type_brique": st1.id, "diametre_utilise": "2950", "epaisseur_garnissage_utilisee": "180"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(models.BesoinTheorique.objects.filter(campagne=campagne, zone=zone, sous_type_brique=st1).exists())

    def test_liste_types_affiche_mapping_formules(self):
        models.TypeBrique.objects.create(
            nom="Type C",
            formule_sous_type_1=self.f1,
            formule_sous_type_2=self.f2,
            formule_sous_type_3=self.f3,
            formule_sous_type_4=self.f4,
        )
        response = self.client.get("/types-briques/")
        self.assertContains(response, "ST-1: F1")
        self.assertContains(response, "ST-4: F4")
