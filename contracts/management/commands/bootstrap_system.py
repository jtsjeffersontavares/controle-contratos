from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand

from contracts.models import Organization


class Command(BaseCommand):
    help = "Cria grupos de acesso, permissões e cadastros básicos."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="")
        parser.add_argument("--password", default="")
        parser.add_argument("--email", default="")
        parser.add_argument("--no-admin", action="store_true")

    def handle(self, *args, **options):
        groups = {
            name: Group.objects.get_or_create(name=name)[0]
            for name in ["Administrador", "Gestor", "Fiscal", "Consulta"]
        }
        app_permissions = Permission.objects.filter(content_type__app_label="contracts")
        view_permissions = app_permissions.filter(codename__startswith="view_")
        groups["Administrador"].permissions.set(app_permissions)
        groups["Gestor"].permissions.set(app_permissions)

        fiscal_codenames = [
            "view_contract",
            "view_contractitem",
            "view_commitment",
            "view_supplyorder",
            "view_delivery",
            "view_contractchange",
            "view_administrativeprocess",
            "view_document",
            "view_supplier",
            "view_organization",
            "view_person",
            "add_delivery",
            "change_delivery",
            "delete_delivery",
            "add_document",
            "change_document",
            "delete_document",
            "change_supplyorder",
        ]
        groups["Fiscal"].permissions.set(
            app_permissions.filter(codename__in=fiscal_codenames)
        )
        groups["Consulta"].permissions.set(view_permissions)
        Organization.objects.get_or_create(
            acronym="SDAP", defaults={"name": "Subdiretoria de Apoio Administrativo"}
        )

        username = options["username"]
        password = options["password"]
        if not options["no_admin"] and username and password:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": options["email"],
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            user.is_staff = True
            user.is_superuser = True
            if options["email"]:
                user.email = options["email"]
            user.set_password(password)
            user.save()
            groups["Administrador"].user_set.add(user)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Administrador {username} {"criado" if created else "atualizado"}.'
                )
            )
        self.stdout.write(
            self.style.SUCCESS("Grupos, permissões e cadastro SDAP configurados.")
        )
