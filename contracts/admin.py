from django.contrib import admin

from .models import (
    AdministrativeProcess,
    AuditLog,
    Commitment,
    Contract,
    ContractChange,
    ContractItem,
    Delivery,
    Document,
    ImportBatch,
    Organization,
    Person,
    Procurement,
    ProcurementItem,
    ProcurementItemDelivery,
    Supplier,
    SupplyOrder,
)

admin.site.site_header = "Administração — Gestão de Contratos SDAP"
admin.site.site_title = "Gestão de Contratos"
admin.site.index_title = "Cadastros, usuários e configurações"


class ContractItemInline(admin.TabularInline):
    model = ContractItem
    extra = 0


class ProcurementItemInline(admin.TabularInline):
    model = ProcurementItem
    extra = 0


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "supplier",
        "status",
        "start_date",
        "end_date",
        "current_value",
    )
    list_filter = ("status", "law", "managing_organization", "reference_organization")
    search_fields = (
        "number",
        "object",
        "supplier__name",
        "process_number",
        "procurement_number",
    )
    autocomplete_fields = (
        "supplier",
        "managing_organization",
        "reference_organization",
        "manager",
        "substitute_manager",
    )
    inlines = [ContractItemInline]


@admin.register(Procurement)
class ProcurementAdmin(admin.ModelAdmin):
    list_display = ("number", "requesting_organization", "status", "opening_date")
    list_filter = ("status", "law", "requesting_organization")
    search_fields = ("number", "object")
    inlines = [ProcurementItemInline]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "cnpj", "cadin_irregular", "impeded", "active")
    list_filter = ("cadin_irregular", "impeded", "active")
    search_fields = ("name", "trade_name", "cnpj")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("acronym", "name", "city", "state", "cep", "address", "active")
    list_filter = ("active", "state")
    search_fields = ("acronym", "name", "cnpj", "city", "state", "cep", "address")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "rank", "organization", "email", "active")
    list_filter = ("active", "organization")
    search_fields = ("name", "rank", "email")


@admin.register(Commitment)
class CommitmentAdmin(admin.ModelAdmin):
    list_display = ("number", "contract", "year", "issue_date", "value")
    search_fields = ("number", "contract__number", "contract__supplier__name")
    list_filter = ("year", "budget_action", "credit_origin")


@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = (
        "contract",
        "destination",
        "number",
        "deadline",
        "status",
        "quantity",
        "value",
    )
    search_fields = (
        "number",
        "official_reference",
        "contract__number",
        "destination__acronym",
    )
    list_filter = ("status", "destination")


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "supply_order",
        "delivery_date",
        "quantity",
        "acceptance",
        "invoice_number",
    )
    list_filter = ("acceptance", "delivery_date")


for model in [ContractChange, AdministrativeProcess, Document, ImportBatch]:
    admin.site.register(model)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "model_name", "representation")
    list_filter = ("action", "model_name", "created_at")
    search_fields = ("representation", "actor__username")
    readonly_fields = (
        "actor",
        "action",
        "model_name",
        "object_id",
        "representation",
        "changes",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProcurementItemDelivery)
class ProcurementItemDeliveryAdmin(admin.ModelAdmin):
    list_display = ("item", "destination", "quantity")
    search_fields = (
        "item__procurement__number",
        "item__item_number",
        "destination__acronym",
    )
