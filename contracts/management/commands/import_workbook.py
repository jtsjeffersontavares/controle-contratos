from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from contracts.import_service import import_preview, preview_workbook


class Command(BaseCommand):
    help = "Importa uma planilha XLSX após validar. Uso administrativo/implantação."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--sheet", default="Planilha1")
        parser.add_argument("--username", default="")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError(
                "Use --confirm para autorizar a gravação após revisar a prévia."
            )
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")
        actor = None
        if options["username"]:
            actor = (
                get_user_model().objects.filter(username=options["username"]).first()
            )
        preview = preview_workbook(path, options["sheet"])
        if preview["summary"]["errors"]:
            raise CommandError(
                f"A prévia contém {preview['summary']['errors']} erros impeditivos."
            )
        result = import_preview(preview, actor=actor, filename=path.name)
        for key, value in sorted(result.items()):
            self.stdout.write(f"{key}: {value}")
        self.stdout.write(self.style.SUCCESS("Importação concluída."))
