import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contracts.import_service import preview_workbook


class Command(BaseCommand):
    help = "Valida uma planilha XLSX sem gravar dados."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--sheet", default="Planilha1")
        parser.add_argument("--json-output", default="")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")
        try:
            preview = preview_workbook(path, options["sheet"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        summary = preview["summary"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Linhas: {summary['rows']} | Contratos: {summary['contracts']} | "
                f"Erros: {summary['errors']} | Alertas: {summary['warnings']}"
            )
        )
        for issue in preview["issues"][:30]:
            self.stdout.write(
                f"{issue['level']} linha {issue['row']}: {issue['message']}"
            )
        if options["json_output"]:
            Path(options["json_output"]).write_text(
                json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.stdout.write(f"Prévia salva em {options['json_output']}")
