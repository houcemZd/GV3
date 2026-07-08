"""
Point d'entrée de l'application de bureau.

Contrairement à lancer_application.py (qui ouvre un onglet de navigateur),
ce script affiche l'application dans une vraie fenêtre native, comme
n'importe quel logiciel de bureau (Word, Excel...). C'est ce script qui est
empaqueté en .exe par construire_application.bat (voir ce fichier).

Fonctionnement : le serveur Django tourne en arrière-plan dans le même
processus (thread), et pywebview affiche une fenêtre pointant dessus.
À la fermeture de la fenêtre, la sauvegarde automatique est déclenchée
directement (plus fiable qu'un hook à la fermeture du processus).
"""
import os
import sys
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

HOTE = "127.0.0.1"
PORT = 8000


def _preparer_environnement():
    """Rend le projet importable, que ce script soit lancé en .py ou en .exe gelé."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # dossier temporaire d'extraction PyInstaller
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    if base not in sys.path:
        sys.path.insert(0, base)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


class ServeurWSGIThreade(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _demarrer_django_et_migrer():
    import django
    django.setup()

    # Applique les migrations automatiquement au démarrage : l'utilisateur
    # final ne doit jamais taper de commande manage.py lui-même.
    from django.core.management import call_command
    call_command("migrate", verbosity=0, interactive=False)

    from config.wsgi import application
    return application


def _lancer_serveur(application):
    httpd = make_server(HOTE, PORT, application, ServeurWSGIThreade)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    _preparer_environnement()
    application = _demarrer_django_et_migrer()
    _lancer_serveur(application)

    from core.backup import effectuer_sauvegarde

    import webview

    fenetre = webview.create_window(
        "Gestion Briques Réfractaires — Four Rotatif",
        f"http://{HOTE}:{PORT}/",
        width=1300, height=850, min_size=(1000, 700),
    )

    def a_la_fermeture():
        # Sauvegarde automatique (section 10 du cahier) déclenchée
        # directement à la fermeture de la fenêtre — plus fiable qu'un
        # hook process (atexit), qui peut ne pas s'exécuter si la fenêtre
        # est fermée brutalement.
        try:
            effectuer_sauvegarde()
        except Exception:
            pass  # ne bloque jamais la fermeture de l'application

    fenetre.events.closed += a_la_fermeture

    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Une application "--windowed" (sans console) n'affiche rien si elle
        # plante avant l'ouverture de la fenêtre : on écrit donc l'erreur
        # dans un fichier, à côté de l'exécutable, pour pouvoir la relire.
        import traceback

        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        try:
            with open(os.path.join(base, "erreur_demarrage.txt"), "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
