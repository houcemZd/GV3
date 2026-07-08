from django.core.management.base import BaseCommand

from core.backup import effectuer_sauvegarde


class Command(BaseCommand):
    help = "Effectue une sauvegarde horodatée de la base (identique à celle déclenchée à la fermeture de l'app)."

    def handle(self, *args, **options):
        effectuer_sauvegarde()
        self.stdout.write(self.style.SUCCESS("Sauvegarde effectuée dans backups/."))
