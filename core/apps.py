import atexit
import sys

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from . import signals  # noqa: F401

        # Sauvegarde automatique à la fermeture de l'application (section 10
        # du cahier). Ne s'active que lorsqu'on lance réellement le serveur,
        # pas pendant les migrations, tests, ou commandes shell.
        if "runserver" in sys.argv:
            from .backup import effectuer_sauvegarde

            atexit.register(effectuer_sauvegarde)
