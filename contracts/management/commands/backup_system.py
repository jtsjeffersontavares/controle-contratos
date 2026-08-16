import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Gera backup do SQLite e dos documentos. Para PostgreSQL, use pg_dump conforme o manual."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=str(settings.BASE_DIR / "backups"))

    def handle(self, *args, **options):
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError(
                "Este comando automático cobre SQLite. Para PostgreSQL, consulte o manual de backup."
            )
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = output_dir / f"backup_gestao_contratos_{timestamp}.zip"
        db_path = Path(settings.DATABASES["default"]["NAME"])
        if not db_path.exists():
            raise CommandError(f"Banco SQLite não encontrado: {db_path}")
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "db.sqlite3"
            with sqlite3.connect(db_path) as source, sqlite3.connect(
                snapshot
            ) as destination:
                source.backup(destination)
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "db.sqlite3")
                media_root = Path(settings.MEDIA_ROOT)
                if media_root.exists():
                    for file in media_root.rglob("*"):
                        if file.is_file():
                            archive.write(
                                file, Path("media") / file.relative_to(media_root)
                            )
        self.stdout.write(self.style.SUCCESS(f"Backup criado: {archive_path}"))
