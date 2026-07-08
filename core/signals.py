from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ConsommationReelle, MouvementStock, Stock


@receiver(post_save, sender=ConsommationReelle)
def alimenter_mouvement_stock(sender, instance, created, **kwargs):
    """
    Une ConsommationRéelle alimente automatiquement un MouvementStock de
    type sortie, et met à jour le Stock correspondant (section 4 du cahier).
    Ne se déclenche qu'à la création, pour éviter de dupliquer le mouvement
    si la consommation est corrigée ensuite.
    """
    if not created:
        return

    MouvementStock.objects.create(
        sous_type_brique=instance.sous_type_brique,
        type_mouvement="sortie",
        quantite=-instance.quantite_posee,
        reference=f"Campagne #{instance.campagne_id} — {instance.zone.nom}",
    )

    stock, _ = Stock.objects.get_or_create(sous_type_brique=instance.sous_type_brique)
    stock.quantite_actuelle = stock.quantite_actuelle - instance.quantite_posee
    stock.save(update_fields=["quantite_actuelle"])
