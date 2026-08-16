from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from .validators import validate_cnpj, validate_document_extension, validate_file_size


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    acronym = models.CharField("sigla", max_length=40, unique=True)
    name = models.CharField("nome", max_length=200, blank=True)
    cnpj = models.CharField(
        "CNPJ",
        max_length=18,
        blank=True,
        null=True,
        unique=True,
        validators=[validate_cnpj],
    )
    city = models.CharField("cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    address = models.TextField("endereço", blank=True)
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["acronym"]
        verbose_name = "Organização Militar"
        verbose_name_plural = "Organizações Militares"

    def __str__(self):
        return f"{self.acronym} — {self.name}" if self.name else self.acronym


class Person(TimeStampedModel):
    name = models.CharField("nome", max_length=160)
    rank = models.CharField("posto/graduação", max_length=40, blank=True)
    organization = models.ForeignKey(
        Organization,
        verbose_name="OM",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="people",
    )
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"], name="unique_person_per_organization"
            ),
        ]
        verbose_name = "Responsável"
        verbose_name_plural = "Responsáveis"

    def __str__(self):
        prefix = f"{self.rank} " if self.rank else ""
        return f"{prefix}{self.name}".strip()


class Supplier(TimeStampedModel):
    name = models.CharField("razão social", max_length=240)
    trade_name = models.CharField("nome fantasia", max_length=180, blank=True)
    cnpj = models.CharField(
        "CNPJ",
        max_length=18,
        blank=True,
        null=True,
        unique=True,
        validators=[validate_cnpj],
    )
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    contact_name = models.CharField("contato", max_length=120, blank=True)
    address = models.TextField("endereço", blank=True)
    cadin_irregular = models.BooleanField("irregular no CADIN", default=False)
    impeded = models.BooleanField("impedida de licitar", default=False)
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("name"), name="unique_supplier_name_ci"
            ),
        ]
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self):
        return f"{self.name} ({self.cnpj})" if self.cnpj else self.name


class Procurement(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "RASCUNHO", "Rascunho"
        OPEN = "EM_ANDAMENTO", "Em andamento"
        HOMOLOGATED = "HOMOLOGADO", "Homologado"
        FAILED = "FRACASSADO", "Fracassado"
        CANCELED = "CANCELADO", "Cancelado"

    class Law(models.TextChoices):
        LAW_8666 = "8666", "Lei nº 8.666/1993"
        LAW_14133 = "14133", "Lei nº 14.133/2021"
        OTHER = "OUTRA", "Outra"

    number = models.CharField("número do pregão", max_length=100, unique=True)
    requesting_organization = models.ForeignKey(
        Organization,
        verbose_name="OM do termo de referência",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurements",
    )
    law = models.CharField(
        "legislação", max_length=10, choices=Law.choices, default=Law.LAW_14133
    )
    opening_date = models.DateField("data de abertura/sessão", null=True, blank=True)
    status = models.CharField(
        "situação", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    notes = models.TextField("observações", blank=True)
    imported_from = models.CharField("origem da importação", max_length=180, blank=True)

    class Meta:
        ordering = [models.F("opening_date").desc(nulls_last=True), "number"]
        verbose_name = "Pregão"
        verbose_name_plural = "Pregões"

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("procurement_detail", args=[self.pk])

    @property
    def estimated_value(self):
        return sum((item.total_value for item in self.items.all()), Decimal("0"))


class ProcurementItem(TimeStampedModel):
    procurement = models.ForeignKey(
        Procurement,
        verbose_name="pregão",
        on_delete=models.CASCADE,
        related_name="items",
    )
    supplier = models.ForeignKey(
        Supplier,
        verbose_name="empresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurement_items",
    )
    item_number = models.CharField("item do pregão", max_length=40)
    code = models.CharField("código/TDV", max_length=100, blank=True)
    nomenclature = models.CharField("nomenclatura", max_length=180, blank=True)
    model = models.CharField("modelo", max_length=180, blank=True)
    brand = models.CharField("marca", max_length=180, blank=True)
    quantity = models.DecimalField(
        "quantidade licitada",
        max_digits=14,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.CharField("unidade", max_length=30, default="UN")
    unit_value = models.DecimalField(
        "valor unitário",
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["procurement", "item_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["procurement", "item_number", "code"],
                name="unique_procurement_item_signature",
            ),
        ]
        verbose_name = "Item do pregão"
        verbose_name_plural = "Itens do pregão"

    def __str__(self):
        return f'{self.procurement.number} — Item {self.item_number} — {self.nomenclature or self.model or self.brand or "Item"}'

    def clean(self):
        super().clean()
        if not self.pk:
            return
        planned_total = self.delivery_locations.aggregate(total=Sum("quantity"))[
            "total"
        ] or Decimal("0")
        if planned_total > self.quantity:
            raise ValidationError(
                {
                    "quantity": "A quantidade do item não pode ser menor que a soma dos locais de entrega."
                }
            )

    @property
    def total_value(self):
        return self.quantity * self.unit_value

    @property
    def total_value_estimate(self):
        return self.total_value

    @property
    def delivered_locations_quantity(self):
        return self.delivery_locations.aggregate(total=Sum("quantity"))[
            "total"
        ] or Decimal("0")

    @property
    def contracted_quantity(self):
        return self.contract_items.aggregate(total=Sum("quantity"))["total"] or Decimal(
            "0"
        )


class ProcurementItemDelivery(TimeStampedModel):
    item = models.ForeignKey(
        ProcurementItem,
        verbose_name="item do pregão",
        on_delete=models.CASCADE,
        related_name="delivery_locations",
    )
    destination = models.ForeignKey(
        Organization,
        verbose_name="OM destino",
        on_delete=models.PROTECT,
        related_name="procurement_deliveries",
    )
    quantity = models.DecimalField(
        "quantidade",
        max_digits=14,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    notes = models.CharField("observações", max_length=200, blank=True)

    class Meta:
        ordering = ["item", "destination"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "destination"],
                name="unique_procurement_item_destination",
            ),
        ]
        verbose_name = "Local de entrega do item"
        verbose_name_plural = "Locais de entrega do item"

    def __str__(self):
        return f"{self.item} — {self.destination.acronym} ({self.quantity})"


class Contract(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "RASCUNHO", "Rascunho"
        ACTIVE = "VIGENTE", "Vigente"
        EXPIRING = "VENCENDO", "Vencendo"
        SUSPENDED = "SUSPENSO", "Suspenso"
        EXPIRED = "VENCIDO", "Vencido"
        CLOSED = "ENCERRADO", "Encerrado"
        TERMINATED = "RESCINDIDO", "Rescindido"

    class Law(models.TextChoices):
        LAW_8666 = "8666", "Lei nº 8.666/1993"
        LAW_14133 = "14133", "Lei nº 14.133/2021"
        OTHER = "OUTRA", "Outra"

    number = models.CharField("número do contrato", max_length=100, unique=True)
    object = models.TextField("objeto", blank=True)
    supplier = models.ForeignKey(
        Supplier,
        verbose_name="empresa",
        on_delete=models.PROTECT,
        related_name="contracts",
    )
    managing_organization = models.ForeignKey(
        Organization,
        verbose_name="OM gestora",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="managed_contracts",
    )
    reference_organization = models.ForeignKey(
        Organization,
        verbose_name="OM do termo de referência",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referenced_contracts",
    )
    manager = models.ForeignKey(
        Person,
        verbose_name="gestor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_contracts",
    )
    substitute_manager = models.ForeignKey(
        Person,
        verbose_name="suplente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_managed_contracts",
    )
    technical_inspector = models.ForeignKey(
        Person,
        verbose_name="fiscal técnico",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspected_contracts",
    )
    substitute_inspector = models.ForeignKey(
        Person,
        verbose_name="fiscal substituto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_inspected_contracts",
    )
    procurement_number = models.CharField(
        "pregão/contratação", max_length=120, blank=True
    )
    procurement = models.ForeignKey(
        Procurement,
        verbose_name="pregão",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
    )
    process_number = models.CharField("PAG/processo", max_length=120, blank=True)
    subprocess_number = models.CharField("subprocesso", max_length=100, blank=True)
    law = models.CharField(
        "legislação", max_length=10, choices=Law.choices, default=Law.LAW_14133
    )
    status = models.CharField(
        "situação informada",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    signature_date = models.DateField("data da assinatura", null=True, blank=True)
    start_date = models.DateField("início da vigência", null=True, blank=True)
    end_date = models.DateField("fim da vigência", null=True, blank=True)
    guarantee_end = models.DateField("fim da garantia", null=True, blank=True)
    initial_value = models.DecimalField(
        "valor inicial",
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    current_value = models.DecimalField(
        "valor atualizado",
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField("observações", blank=True)
    imported_from = models.CharField("origem da importação", max_length=180, blank=True)

    class Meta:
        ordering = [models.F("end_date").asc(nulls_last=True), "number"]
        verbose_name = "Contrato"
        verbose_name_plural = "Contratos"
        permissions = [
            ("view_management_dashboard", "Pode visualizar painel gerencial")
        ]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("contract_detail", args=[self.pk])

    @property
    def days_to_expiry(self):
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def calculated_status(self):
        if self.status in {
            self.Status.CLOSED,
            self.Status.TERMINATED,
            self.Status.SUSPENDED,
        }:
            return self.status
        days = self.days_to_expiry
        if days is None:
            return (
                self.Status.DRAFT if self.status == self.Status.DRAFT else self.status
            )
        if days < 0:
            return self.Status.EXPIRED
        if days <= 90:
            return self.Status.EXPIRING
        return self.Status.ACTIVE

    @property
    def calculated_status_label(self):
        return dict(self.Status.choices).get(
            self.calculated_status, self.calculated_status
        )

    @property
    def committed_value(self):
        total = Decimal("0")
        for commitment in self.commitments.all():
            total += commitment.total_value
        return total

    @property
    def ordered_value(self):
        return self.supply_orders.aggregate(total=Sum("value"))["total"] or Decimal("0")

    @property
    def balance(self):
        return self.current_value - self.committed_value

    @property
    def delivery_percentage(self):
        total = self.supply_orders.aggregate(total=Sum("quantity"))["total"] or Decimal(
            "0"
        )
        if not total:
            return Decimal("0")
        completed = sum(
            (order.delivered_quantity for order in self.supply_orders.all()),
            Decimal("0"),
        )
        return min(Decimal("100"), completed * Decimal("100") / total)

    def copy_items_from_procurement(self) -> int:
        if not self.procurement_id:
            return 0
        existing = set(
            self.items.exclude(origin_procurement_item__isnull=True).values_list(
                "origin_procurement_item_id", flat=True
            )
        )
        created_count = 0
        for procurement_item in self.procurement.items.all():
            if procurement_item.pk in existing:
                continue
            ContractItem.objects.create(
                contract=self,
                origin_procurement_item=procurement_item,
                procurement_item=procurement_item.item_number,
                code=procurement_item.code,
                nomenclature=procurement_item.nomenclature,
                description=procurement_item.model
                or procurement_item.brand
                or procurement_item.nomenclature,
                quantity=procurement_item.quantity,
                unit=procurement_item.unit,
                unit_value=procurement_item.unit_value,
            )
            created_count += 1
        return created_count


class ContractItem(TimeStampedModel):
    contract = models.ForeignKey(
        Contract,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="items",
    )
    procurement_item = models.CharField("item do pregão", max_length=40, blank=True)
    origin_procurement_item = models.ForeignKey(
        ProcurementItem,
        verbose_name="item do pregão de origem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_items",
    )
    code = models.CharField("código/TDV", max_length=100, blank=True)
    nomenclature = models.CharField("nomenclatura", max_length=180, blank=True)
    description = models.TextField("tipo/modelo/descrição")
    quantity = models.DecimalField(
        "quantidade contratada",
        max_digits=14,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.CharField("unidade", max_length=30, default="UN")
    unit_value = models.DecimalField(
        "valor unitário",
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["contract", "procurement_item", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "procurement_item", "code", "description"],
                name="unique_contract_item_signature",
            ),
        ]
        verbose_name = "Item do contrato"
        verbose_name_plural = "Itens do contrato"

    def __str__(self):
        item = self.procurement_item or "s/n"
        return f"{self.contract.number} — Item {item} — {self.nomenclature or self.description[:40]}"

    @property
    def total_value(self):
        return self.quantity * self.unit_value


class Commitment(TimeStampedModel):
    contract = models.ForeignKey(
        Contract,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="commitments",
    )
    item = models.ForeignKey(
        ContractItem,
        verbose_name="item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commitments",
    )
    organization = models.ForeignKey(
        Organization,
        verbose_name="OM do empenho",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commitments",
    )
    number = models.CharField("nota de empenho", max_length=100)
    year = models.PositiveIntegerField("ano do empenho", null=True, blank=True)
    issue_date = models.DateField("data de emissão", null=True, blank=True)
    quantity = models.DecimalField(
        "quantidade empenhada", max_digits=14, decimal_places=2, default=0
    )
    value = models.DecimalField(
        "valor",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    budget_action = models.CharField("ação orçamentária", max_length=60, blank=True)
    ptres = models.CharField("PTRES", max_length=60, blank=True)
    credit_origin = models.CharField("origem do crédito", max_length=120, blank=True)
    pi = models.CharField("PI", max_length=80, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = [models.F("issue_date").desc(nulls_last=True), "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "number", "item"],
                name="unique_commitment_contract_number_item",
            ),
        ]
        verbose_name = "Nota de empenho"
        verbose_name_plural = "Notas de empenho"

    def __str__(self):
        return f"{self.number} — {self.contract.number}"

    @property
    def total_value(self):
        resource_total = self.resources.aggregate(total=Sum("value"))["total"]
        if resource_total is not None:
            return resource_total
        return self.value or Decimal("0")

    @property
    def resource_count(self):
        return self.resources.count()


class CommitmentResource(TimeStampedModel):
    commitment = models.ForeignKey(
        Commitment,
        verbose_name="empenho",
        on_delete=models.CASCADE,
        related_name="resources",
    )
    number = models.CharField("nota de empenho", max_length=100, blank=True)
    budget_action = models.CharField("ação orçamentária", max_length=60, blank=True)
    ptres = models.CharField("PTRES", max_length=60, blank=True)
    credit_origin = models.CharField("origem do crédito", max_length=120, blank=True)
    pi = models.CharField("PI", max_length=80, blank=True)
    value = models.DecimalField(
        "valor do recurso",
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "Recurso do empenho"
        verbose_name_plural = "Recursos do empenho"

    def __str__(self):
        return f"{self.commitment.number} — {self.number or self.ptres or self.pi or self.budget_action or 'recurso'}"


class SupplyOrder(TimeStampedModel):
    class Status(models.TextChoices):
        NOT_INFORMED = "NAO_INFORMADO", "Não informado"
        ISSUED = "EMITIDA", "Emitida"
        SENT = "ENVIADA", "Enviada à empresa/OM"
        PENDING = "PENDENTE", "Pendente"
        PARTIAL = "PARCIAL", "Parcialmente atendida"
        COMPLETED = "CONCLUIDA", "Concluída"
        OVERDUE = "ATRASADA", "Atrasada"
        CANCELED = "CANCELADA", "Cancelada"

    contract = models.ForeignKey(
        Contract,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="supply_orders",
    )
    item = models.ForeignKey(
        ContractItem,
        verbose_name="item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_orders",
    )
    commitment = models.ForeignKey(
        Commitment,
        verbose_name="empenho",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_orders",
    )
    destination = models.ForeignKey(
        Organization,
        verbose_name="OM destino",
        on_delete=models.PROTECT,
        related_name="supply_orders",
    )
    procurement_destinations = models.TextField("OMs destino do pregão", blank=True)
    number = models.CharField("ordem de fornecimento", max_length=120, blank=True)
    official_reference = models.CharField(
        "ofício/SIGAD de encaminhamento", max_length=160, blank=True
    )
    issue_date = models.DateField("assinatura/emissão da OF", null=True, blank=True)
    sent_date = models.DateField("data de envio", null=True, blank=True)
    deadline = models.DateField("prazo de entrega", null=True, blank=True)
    quantity = models.DecimalField(
        "quantidade",
        max_digits=14,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0"))],
    )
    value = models.DecimalField(
        "valor",
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        "situação", max_length=20, choices=Status.choices, default=Status.NOT_INFORMED
    )
    reported_delivery = models.CharField(
        "entregue? (informado)", max_length=30, blank=True
    )
    reported_delivery_date_text = models.CharField(
        "data de entrega informada", max_length=200, blank=True
    )
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = [
            models.F("deadline").asc(nulls_last=True),
            "contract",
            "destination",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "contract",
                    "item",
                    "commitment",
                    "destination",
                    "official_reference",
                ],
                name="unique_supply_order_import_signature",
            ),
        ]
        verbose_name = "Ordem de fornecimento"
        verbose_name_plural = "Ordens de fornecimento"

    def __str__(self):
        ref = self.number or self.official_reference or "OF sem referência"
        return f"{ref} — {self.destination.acronym}"

    @property
    def delivered_quantity(self):
        delivered = self.deliveries.aggregate(total=Sum("quantity"))[
            "total"
        ] or Decimal("0")
        if delivered == 0 and self.status == self.Status.COMPLETED:
            return self.quantity
        return min(delivered, self.quantity)

    @property
    def pending_quantity(self):
        return max(Decimal("0"), self.quantity - self.delivered_quantity)

    @property
    def is_overdue(self):
        return bool(
            self.deadline
            and self.deadline < timezone.localdate()
            and self.status not in {self.Status.COMPLETED, self.Status.CANCELED}
        )

    @property
    def effective_status(self):
        if self.status in {self.Status.COMPLETED, self.Status.CANCELED}:
            return self.status
        if self.is_overdue:
            return self.Status.OVERDUE
        if self.delivered_quantity and self.pending_quantity:
            return self.Status.PARTIAL
        return self.status

    @property
    def effective_status_label(self):
        return dict(self.Status.choices).get(
            self.effective_status, self.effective_status
        )


class Delivery(TimeStampedModel):
    class Acceptance(models.TextChoices):
        PENDING = "PENDENTE", "Pendente de aceite"
        ACCEPTED = "ACEITA", "Aceita"
        REJECTED = "RECUSADA", "Recusada"
        WITH_RESTRICTION = "RESSALVA", "Aceita com ressalva"

    supply_order = models.ForeignKey(
        SupplyOrder,
        verbose_name="ordem de fornecimento",
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    delivery_date = models.DateField("data da entrega")
    quantity = models.DecimalField(
        "quantidade entregue",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    invoice_number = models.CharField("nota fiscal", max_length=100, blank=True)
    acceptance = models.CharField(
        "aceite", max_length=20, choices=Acceptance.choices, default=Acceptance.PENDING
    )
    accepted_by = models.ForeignKey(
        User,
        verbose_name="recebido/atestado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_deliveries",
    )
    notes = models.TextField("observações/ocorrências", blank=True)

    class Meta:
        ordering = ["-delivery_date"]
        verbose_name = "Entrega"
        verbose_name_plural = "Entregas"

    def __str__(self):
        return f"{self.supply_order} — {self.delivery_date:%d/%m/%Y}"


class ContractChange(TimeStampedModel):
    class ChangeType(models.TextChoices):
        QUANTITY = "QUANTIDADE", "Alteração de Quantidade"
        DEADLINE = "PRAZO", "Alteração de Prazo"
        VALUE = "VALOR", "Alteração de Valor"

    contract = models.ForeignKey(
        Contract,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="changes",
    )
    change_type = models.CharField(
        "tipo de alteração", max_length=20, choices=ChangeType.choices
    )
    number = models.CharField("número da alteração", max_length=100)
    request_date = models.DateField(
        "data da solicitação", auto_now_add=True, null=True, blank=True
    )
    item = models.ForeignKey(
        ContractItem,
        verbose_name="item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="changes",
    )
    old_quantity = models.DecimalField(
        "quantidade anterior", max_digits=14, decimal_places=2, null=True, blank=True
    )
    new_quantity = models.DecimalField(
        "nova quantidade", max_digits=14, decimal_places=2, null=True, blank=True
    )
    deadline_scope = models.CharField(
        "escopo da alteração de prazo", max_length=120, blank=True
    )
    old_end_date = models.DateField("prazo anterior", null=True, blank=True)
    new_end_date = models.DateField("novo prazo", null=True, blank=True)
    value_change = models.DecimalField(
        "alteração do valor", max_digits=18, decimal_places=2, null=True, blank=True
    )
    commitment = models.ForeignKey(
        Commitment,
        verbose_name="empenho para alteração de valor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="changes",
    )
    commitment_mode = models.CharField(
        "modalidade do empenho", max_length=60, blank=True
    )
    new_commitment_number = models.CharField(
        "número do novo empenho", max_length=100, blank=True
    )
    justification = models.TextField("justificativa", blank=True)

    class Meta:
        ordering = ["-request_date", "number"]
        verbose_name = "Alteração contratual"
        verbose_name_plural = "Alterações contratuais"

    def __str__(self):
        return f"{self.contract.number} — {self.number}"


class AdministrativeProcess(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "ABERTO", "Aberto"
        IN_PROGRESS = "EM_ANDAMENTO", "Em andamento"
        SUSPENDED = "SUSPENSO", "Suspenso"
        CLOSED = "ENCERRADO", "Encerrado"

    contract = models.ForeignKey(
        Contract,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="administrative_processes",
    )
    number = models.CharField("número do processo", max_length=100)
    reason = models.TextField("motivo")
    opened_date = models.DateField("data de abertura")
    deadline = models.DateField("prazo", null=True, blank=True)
    status = models.CharField(
        "situação", max_length=20, choices=Status.choices, default=Status.OPEN
    )
    sanction = models.TextField("sanção aplicada", blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["-opened_date"]
        verbose_name = "Processo administrativo"
        verbose_name_plural = "Processos administrativos"

    def __str__(self):
        return f"{self.contract.number} — {self.number}"


class ImportBatch(TimeStampedModel):
    class Status(models.TextChoices):
        PREVIEW = "PREVIA", "Prévia gerada"
        IMPORTED = "IMPORTADO", "Importado"
        CANCELED = "CANCELADO", "Cancelado"
        FAILED = "FALHOU", "Falhou"

    filename = models.CharField("arquivo", max_length=255)
    sheet_name = models.CharField("aba", max_length=100, default="Planilha1")
    status = models.CharField(
        "situação", max_length=20, choices=Status.choices, default=Status.PREVIEW
    )
    created_by = models.ForeignKey(
        User, verbose_name="usuário", on_delete=models.SET_NULL, null=True, blank=True
    )
    row_count = models.PositiveIntegerField("linhas lidas", default=0)
    error_count = models.PositiveIntegerField("erros", default=0)
    warning_count = models.PositiveIntegerField("alertas", default=0)
    preview_data = models.JSONField("dados da prévia", default=dict, blank=True)
    result = models.JSONField("resultado", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lote de importação"
        verbose_name_plural = "Lotes de importação"

    def __str__(self):
        return f"{self.filename} — {self.get_status_display()}"


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CRIAR", "Criação"
        UPDATE = "ALTERAR", "Alteração"
        DELETE = "EXCLUIR", "Exclusão"
        IMPORT = "IMPORTAR", "Importação"
        EXPORT = "EXPORTAR", "Exportação"
        LOGIN = "LOGIN", "Acesso"

    actor = models.ForeignKey(
        User, verbose_name="usuário", on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField("ação", max_length=15, choices=Action.choices)
    model_name = models.CharField("módulo", max_length=100)
    object_id = models.CharField("ID do registro", max_length=80, blank=True)
    representation = models.CharField("registro", max_length=255)
    changes = models.JSONField("alterações", default=dict, blank=True)
    created_at = models.DateTimeField("data/hora", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at", "action"])]
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"

    def __str__(self):
        return f"{self.get_action_display()} — {self.representation}"


class Document(TimeStampedModel):
    class Category(models.TextChoices):
        LEGAL = "LEGAL", "Legal/Contratual"
        FINANCIAL = "FINANCIAL", "Financeiro"
        TECHNICAL = "TECHNICAL", "Técnico"
        CORRESPONDENCE = "CORRESPONDENCE", "Correspondência"
        DELIVERY = "DELIVERY", "Entrega/Recebimento"
        OTHER = "OTHER", "Outro"

    contract = models.ForeignKey(
        Contract,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField("título", max_length=240)
    category = models.CharField(
        "categoria", max_length=30, choices=Category.choices, default=Category.OTHER
    )
    file = models.FileField(
        "arquivo",
        upload_to="contracts/documents/",
        validators=[validate_document_extension, validate_file_size],
    )
    reference_date = models.DateField("data de referência", null=True, blank=True)
    description = models.TextField("descrição", blank=True)

    class Meta:
        ordering = ["-reference_date", "-created_at"]
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"

    def __str__(self):
        return f"{self.contract.number} — {self.title}"
