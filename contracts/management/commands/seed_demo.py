from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.models import Commitment, Contract, ContractItem, Organization, Person, Supplier, SupplyOrder


class Command(BaseCommand):
    help = "Cria dados fictícios opcionais para demonstração."

    def handle(self, *args, **options):
        sdap, _ = Organization.objects.get_or_create(
            acronym="SDAP", defaults={"name": "Subdiretoria de Apoio Administrativo"}
        )
        destination, _ = Organization.objects.get_or_create(
            acronym="OM-DEMO", defaults={"name": "Organização de demonstração"}
        )
        supplier, _ = Supplier.objects.get_or_create(name="EMPRESA DEMONSTRAÇÃO LTDA")
        person, _ = Person.objects.get_or_create(
            name="GESTOR DEMONSTRAÇÃO", defaults={"rank": "1T", "organization": sdap}
        )
        today = timezone.localdate()
        contract, _ = Contract.objects.update_or_create(
            number="000/DEMO/2026",
            defaults={
                "object": "Veículo de demonstração — dados fictícios",
                "supplier": supplier,
                "managing_organization": sdap,
                "reference_organization": sdap,
                "manager": person,
                "procurement_number": "90000/2026",
                "process_number": "00000.000000/2026-00",
                "status": Contract.Status.ACTIVE,
                "signature_date": today,
                "start_date": today,
                "end_date": today + timedelta(days=250),
                "initial_value": Decimal("150000"),
                "current_value": Decimal("150000"),
            },
        )
        item, _ = ContractItem.objects.update_or_create(
            contract=contract,
            procurement_item="1",
            code="P-1/01A-DTS",
            description="VEÍCULO DEMONSTRAÇÃO",
            defaults={
                "nomenclature": "Veículo de serviço",
                "quantity": 1,
                "unit_value": Decimal("150000"),
            },
        )
        commitment, _ = Commitment.objects.update_or_create(
            contract=contract,
            number="2026NE000000",
            item=item,
            defaults={
                "year": 2026,
                "issue_date": today,
                "quantity": 1,
                "value": Decimal("150000"),
                "budget_action": "20XV",
                "ptres": "000000",
                "credit_origin": "DEMO",
                "pi": "PI000000",
            },
        )
        SupplyOrder.objects.update_or_create(
            contract=contract,
            item=item,
            commitment=commitment,
            destination=destination,
            official_reference="SIGAD: DEMO",
            defaults={
                "issue_date": today,
                "deadline": today + timedelta(days=90),
                "quantity": 1,
                "value": Decimal("150000"),
                "status": SupplyOrder.Status.PENDING,
            },
        )
        self.stdout.write(
            self.style.SUCCESS("Dados fictícios de demonstração criados.")
        )
