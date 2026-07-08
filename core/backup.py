"""
Sauvegarde locale automatique (section 10 du cahier).

- Déclenchement : à chaque fermeture de l'application (voir core/apps.py).
- Emplacement : dossier local backups/, distinct du fichier de travail.
- Rétention : conservation des N dernières sauvegardes (30 par défaut).

Limite assumée (documentée dans le cahier) : une sauvegarde sur le même
disque ne protège pas d'une panne matérielle du disque lui-même — il est
recommandé de copier périodiquement backups/ sur un support externe.
"""
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings

RETENTION = 30


def effectuer_sauvegarde():
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        return  # pas encore de base créée (ex. avant la première migration)

    backups_dir = Path(settings.DATA_DIR) / "backups"
    backups_dir.mkdir(exist_ok=True)

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backups_dir / f"{db_path.stem}_{horodatage}{db_path.suffix}"
    shutil.copy2(db_path, destination)

    _purger_anciennes_sauvegardes(backups_dir, db_path.stem)


def _purger_anciennes_sauvegardes(backups_dir: Path, prefix: str):
    sauvegardes = sorted(
        backups_dir.glob(f"{prefix}_*"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for ancienne in sauvegardes[RETENTION:]:
        ancienne.unlink(missing_ok=True)
