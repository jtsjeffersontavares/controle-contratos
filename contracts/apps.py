from django.apps import AppConfig


class ContractsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contracts"
    verbose_name = "Gestão de Contratos"

    def ready(self):
        from . import signals  # noqa: F401
