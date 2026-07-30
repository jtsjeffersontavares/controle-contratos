from __future__ import annotations

import csv
import io
import mimetypes
import re
from pathlib import Path
from datetime import timedelta
from collections import Counter
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms.utils import ErrorList
from django.db.models import Q, Sum
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    AdministrativeProcessForm,
    CommitmentForm,
    ContractChangeForm,
    ContractForm,
    ContractItemForm,
    DeliveryForm,
    DocumentForm,
    ImportWorkbookForm,
    OrganizationForm,
    PersonForm,
    ProcurementForm,
    ProcurementItemDeliveryFormSet,
    ProcurementItemForm,
    SupplierForm,
    SupplyOrderForm,
)
from .import_service import import_preview, preview_workbook
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
    Supplier,
    SupplyOrder,
)
from .permissions import EditorRequiredMixin, ManagerRequiredMixin
from .xlsx_utils import write_simple_xlsx


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'contracts/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        contracts = list(Contract.objects.select_related('supplier').all())
        orders = list(SupplyOrder.objects.select_related('contract', 'destination').all())
        status_counts = Counter(contract.calculated_status for contract in contracts)
        order_status_counts = Counter(order.effective_status for order in orders)
        total_value = sum((contract.current_value for contract in contracts), Decimal('0'))
        total_order_qty = sum((order.quantity for order in orders), Decimal('0'))
        delivered_qty = sum((order.delivered_quantity for order in orders), Decimal('0'))
        delivery_percent = (delivered_qty * Decimal('100') / total_order_qty) if total_order_qty else Decimal('0')
        top_destinations = list(
            SupplyOrder.objects.values('destination__acronym')
            .annotate(total=Sum('value'))
            .order_by('-total')[:10]
        )
        max_destination = max((row['total'] or 0 for row in top_destinations), default=1)
        for row in top_destinations:
            row['bar_percent'] = float((row['total'] or 0) * 100 / max_destination) if max_destination else 0
        upcoming = sorted(
            [contract for contract in contracts if contract.days_to_expiry is not None and 0 <= contract.days_to_expiry <= 90],
            key=lambda item: item.days_to_expiry,
        )[:10]
        overdue_orders = sorted(
            [order for order in orders if order.is_overdue],
            key=lambda item: item.deadline or today,
        )[:10]
        context.update({
            'total_contracts': len(contracts),
            'total_value': total_value,
            'active_contracts': status_counts[Contract.Status.ACTIVE],
            'expiring_contracts': status_counts[Contract.Status.EXPIRING],
            'expired_contracts': status_counts[Contract.Status.EXPIRED],
            'open_paai': AdministrativeProcess.objects.exclude(status=AdministrativeProcess.Status.ARCHIVED).count(),
            'overdue_orders_count': order_status_counts[SupplyOrder.Status.OVERDUE],
            'delivery_percent': min(Decimal('100'), delivery_percent),
            'top_destinations': top_destinations,
            'upcoming_contracts': upcoming,
            'overdue_orders': overdue_orders,
            'recent_audit': AuditLog.objects.select_related('actor')[:8],
            'status_cards': [
                {'label': 'Vigentes', 'value': status_counts[Contract.Status.ACTIVE], 'class': 'success'},
                {'label': 'Vencendo em 90 dias', 'value': status_counts[Contract.Status.EXPIRING], 'class': 'warning'},
                {'label': 'Vencidos', 'value': status_counts[Contract.Status.EXPIRED], 'class': 'danger'},
                {'label': 'Sem data/rascunho', 'value': status_counts[Contract.Status.DRAFT], 'class': 'neutral'},
            ],
        })
        return context


class SearchableListView(LoginRequiredMixin, ListView):
    paginate_by = 25
    search_fields = []

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q', '').strip()
        if query and self.search_fields:
            condition = Q()
            for field in self.search_fields:
                condition |= Q(**{f'{field}__icontains': query})
            queryset = queryset.filter(condition)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        return context


class ContractListView(SearchableListView):
    model = Contract
    template_name = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    search_fields = ['number', 'supplier__name', 'process_number']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('supplier', 'manager', 'reference_organization')
        status = self.request.GET.get('status', '')
        if status:
            ids = [contract.pk for contract in queryset if contract.calculated_status == status]
            queryset = queryset.filter(pk__in=ids)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', '')
        context['status_choices'] = Contract.Status.choices
        return context


class ContractDetailView(LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_detail.html'
    context_object_name = 'contract'

    def get_queryset(self):
        return Contract.objects.select_related(
            'supplier', 'managing_organization', 'reference_organization', 'manager', 'substitute_manager',
            'technical_inspector', 'substitute_inspector', 'procurement',
        ).prefetch_related(
            'items', 'commitments__item', 'supply_orders__destination', 'supply_orders__deliveries',
            'changes', 'administrative_processes', 'documents',
        )


class PrefillContractMixin:
    def get_initial(self):
        initial = super().get_initial()
        contract_id = self.request.GET.get('contract')
        if contract_id and 'contract' in self.form_class.base_fields:
            initial['contract'] = contract_id
        order_id = self.request.GET.get('order')
        if order_id and 'supply_order' in self.form_class.base_fields:
            initial['supply_order'] = order_id
        return initial


class FormMetaMixin:
    title = ''
    cancel_url_name = 'dashboard'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        context['cancel_url'] = self.get_cancel_url()
        return context

    def get_cancel_url(self):
        contract_id = self.request.GET.get('contract') or getattr(getattr(self, 'object', None), 'contract_id', None)
        if contract_id:
            return reverse('contract_detail', args=[contract_id])
        return reverse(self.cancel_url_name)

    def form_valid(self, form):
        messages.success(self.request, 'Registro salvo com sucesso.')
        return super().form_valid(form)


class ContractCreateView(LoginRequiredMixin, ManagerRequiredMixin, FormMetaMixin, CreateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/form.html'
    title = 'Novo contrato'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields.pop('procurement_number', None)
        form.fields.pop('managing_organization', None)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['contract_create_mode'] = True
        context['procurement_summary_url_template'] = reverse('procurement_summary', args=[0]).replace('/0/', '/__id__/')
        return context

    def form_valid(self, form):
        procurement = form.cleaned_data.get('procurement')
        if procurement:
            items = list(procurement.items.all())
            if items:
                form.instance.object = '; '.join(
                    (item.nomenclature or item.model or item.brand or f'Item {item.item_number}')
                    for item in items[:8]
                )
        return super().form_valid(form)


class ContractUpdateView(LoginRequiredMixin, ManagerRequiredMixin, FormMetaMixin, UpdateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/form.html'
    title = 'Editar contrato'


class ContractDeleteView(LoginRequiredMixin, ManagerRequiredMixin, DeleteView):
    model = Contract
    template_name = 'contracts/confirm_delete.html'
    success_url = reverse_lazy('contract_list')

    def form_valid(self, form):
        messages.success(self.request, 'Contrato excluído.')
        return super().form_valid(form)


class ProcurementListView(SearchableListView):
    model = Procurement
    template_name = 'contracts/procurement_list.html'
    context_object_name = 'procurements'
    search_fields = ['number', 'object', 'requesting_organization__acronym']

    def get_queryset(self):
        return super().get_queryset().select_related('requesting_organization')


class ProcurementDetailView(LoginRequiredMixin, DetailView):
    model = Procurement
    template_name = 'contracts/procurement_detail.html'
    context_object_name = 'procurement'

    def get_queryset(self):
        return Procurement.objects.select_related('requesting_organization').prefetch_related(
            'items__delivery_locations__destination', 'contracts__supplier', 'contracts__items__origin_procurement_item',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.object.items.all())

        def natural_key(value: str):
            return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', value or '')]

        context['procurement_items'] = sorted(items, key=lambda item: natural_key(item.item_number))

        linked_contracts = []
        for contract in self.object.contracts.all():
            linked_numbers = []
            seen = set()
            for contract_item in contract.items.all():
                origin = contract_item.origin_procurement_item
                if not origin or origin.procurement_id != self.object.pk:
                    continue
                number = origin.item_number or contract_item.procurement_item or 's/n'
                if number in seen:
                    continue
                seen.add(number)
                linked_numbers.append(number)
            linked_contracts.append({
                'contract': contract,
                'linked_item_numbers': sorted(linked_numbers, key=natural_key),
            })
        context['linked_contracts'] = linked_contracts
        return context


class ProcurementCreateView(LoginRequiredMixin, ManagerRequiredMixin, FormMetaMixin, CreateView):
    model = Procurement
    form_class = ProcurementForm
    template_name = 'contracts/form.html'
    title = 'Novo pregão'
    success_url = reverse_lazy('procurement_list')


class ProcurementUpdateView(LoginRequiredMixin, ManagerRequiredMixin, FormMetaMixin, UpdateView):
    model = Procurement
    form_class = ProcurementForm
    template_name = 'contracts/form.html'
    title = 'Editar pregão'

    def get_success_url(self):
        return self.object.get_absolute_url()


class ProcurementDeleteView(LoginRequiredMixin, ManagerRequiredMixin, DeleteView):
    model = Procurement
    template_name = 'contracts/confirm_delete.html'
    success_url = reverse_lazy('procurement_list')

    def form_valid(self, form):
        messages.success(self.request, 'Pregão excluído.')
        return super().form_valid(form)


class ProcurementSummaryView(LoginRequiredMixin, View):
    def get(self, request, pk):
        procurement = get_object_or_404(Procurement.objects.prefetch_related('items__delivery_locations__destination'), pk=pk)
        items = []
        for item in procurement.items.all():
            deliveries = [
                {
                    'destination': delivery.destination.acronym,
                    'quantity': str(delivery.quantity),
                }
                for delivery in item.delivery_locations.all()
            ]
            items.append({
                'id': item.pk,
                'item_number': item.item_number,
                'title': item.nomenclature or item.model or item.brand or f'Item {item.item_number}',
                'code': item.code,
                'quantity': str(item.quantity),
                'unit': item.unit,
                'deliveries': deliveries,
            })
        payload = {
            'id': procurement.pk,
            'number': procurement.number,
            'items': items,
        }
        return JsonResponse(payload)


class ContractOrderItemsView(LoginRequiredMixin, View):
    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)
        items = []
        queryset = contract.items.select_related('origin_procurement_item').all()
        for item in queryset:
            locations = []
            if item.origin_procurement_item_id:
                locations = list(
                    item.origin_procurement_item.delivery_locations.select_related('destination').values_list(
                        'destination__acronym', 'quantity'
                    )
                )
            refs = ', '.join(f'{acronym} ({quantity})' for acronym, quantity in locations)
            title = item.nomenclature or item.description[:40]
            label = f'Item {item.procurement_item or "s/n"} — {title}'
            items.append({
                'id': item.pk,
                'label': label,
                'procurementItem': item.procurement_item or '',
                'locationsText': refs,
            })
        return JsonResponse({'contractId': contract.pk, 'items': items})


class ProcurementItemFormMixin(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin):
    model = ProcurementItem
    form_class = ProcurementItemForm
    template_name = 'contracts/procurement_item_form.html'

    def get_initial(self):
        initial = super().get_initial()
        procurement_id = self.request.GET.get('procurement')
        if procurement_id:
            initial['procurement'] = procurement_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == 'POST':
            context['delivery_formset'] = ProcurementItemDeliveryFormSet(self.request.POST, instance=self.object)
        else:
            context['delivery_formset'] = ProcurementItemDeliveryFormSet(instance=self.object)
        context['item_quantity'] = getattr(self.object, 'quantity', None)
        context['planned_quantity'] = getattr(self.object, 'delivered_locations_quantity', Decimal('0'))
        return context

    def form_valid(self, form):
        self.object = form.save()
        context = self.get_context_data(form=form)
        formset = context['delivery_formset']
        formset.instance = self.object
        if formset.is_valid():
            quantity = form.cleaned_data.get('quantity') or Decimal('0')
            planned = sum(
                (
                    delivery_form.cleaned_data.get('quantity') or Decimal('0')
                    for delivery_form in formset.forms
                    if delivery_form.cleaned_data and not delivery_form.cleaned_data.get('DELETE')
                ),
                Decimal('0'),
            )
            if planned > quantity:
                formset._non_form_errors = ErrorList([
                    'A soma das quantidades por OM destino não pode ultrapassar a quantidade total do item.',
                ])
                context['planned_quantity'] = planned
                context['item_quantity'] = quantity
                return self.render_to_response(context)
            formset.save()
            messages.success(self.request, 'Item do pregão salvo com sucesso.')
            return redirect(self.get_success_url())
        return self.render_to_response(context)

    def get_success_url(self):
        return self.object.procurement.get_absolute_url()


class ProcurementItemCreateView(ProcurementItemFormMixin, CreateView):
    title = 'Novo item do pregão'


class ProcurementItemUpdateView(ProcurementItemFormMixin, UpdateView):
    title = 'Editar item do pregão'


class ProcurementItemDeleteView(LoginRequiredMixin, EditorRequiredMixin, DeleteView):
    model = ProcurementItem
    template_name = 'contracts/confirm_delete.html'

    def get_success_url(self):
        return self.object.procurement.get_absolute_url()

    def form_valid(self, form):
        messages.success(self.request, 'Item do pregão excluído.')
        return super().form_valid(form)


class SupplierListView(SearchableListView):
    model = Supplier
    template_name = 'contracts/supplier_list.html'
    context_object_name = 'suppliers'
    search_fields = ['name', 'trade_name', 'cnpj', 'contact_name']


class OrganizationListView(SearchableListView):
    model = Organization
    template_name = 'contracts/organization_list.html'
    context_object_name = 'organizations'
    search_fields = ['acronym', 'name', 'cnpj', 'city']


class PersonListView(SearchableListView):
    model = Person
    template_name = 'contracts/person_list.html'
    context_object_name = 'people'
    search_fields = ['name', 'rank', 'email', 'organization__acronym']


class CommitmentListView(SearchableListView):
    model = Commitment
    template_name = 'contracts/commitment_list.html'
    context_object_name = 'commitments'
    search_fields = ['number', 'contract__number', 'contract__supplier__name', 'ptres', 'pi']

    def get_queryset(self):
        return super().get_queryset().select_related('contract', 'item', 'organization')


class SupplyOrderListView(SearchableListView):
    model = SupplyOrder
    template_name = 'contracts/supplyorder_list.html'
    context_object_name = 'orders'
    search_fields = ['number', 'official_reference', 'contract__number', 'destination__acronym', 'contract__supplier__name']

    def get_queryset(self):
        return super().get_queryset().select_related('contract', 'destination', 'item', 'commitment').prefetch_related('deliveries')


class DeliveryListView(SearchableListView):
    model = Delivery
    template_name = 'contracts/delivery_list.html'
    context_object_name = 'deliveries'
    search_fields = ['supply_order__contract__number', 'supply_order__destination__acronym', 'invoice_number']

    def get_queryset(self):
        return super().get_queryset().select_related('supply_order__contract', 'supply_order__destination', 'accepted_by')


class ChangeListView(SearchableListView):
    model = ContractChange
    template_name = 'contracts/change_list.html'
    context_object_name = 'changes'
    search_fields = ['contract__number', 'number', 'status', 'justification']

    def get_queryset(self):
        return super().get_queryset().select_related('contract')


class ProcessListView(SearchableListView):
    model = AdministrativeProcess
    template_name = 'contracts/process_list.html'
    context_object_name = 'processes'
    search_fields = ['contract__number', 'number', 'reason', 'sanction']

    def get_queryset(self):
        return super().get_queryset().select_related('contract')


class DocumentListView(SearchableListView):
    model = Document
    template_name = 'contracts/document_list.html'
    context_object_name = 'documents'
    search_fields = ['contract__number', 'title', 'category', 'description']

    def get_queryset(self):
        return super().get_queryset().select_related('contract', 'uploaded_by')


class AuditListView(SearchableListView):
    model = AuditLog
    template_name = 'contracts/audit_list.html'
    context_object_name = 'logs'
    search_fields = ['actor__username', 'representation', 'model_name', 'action']

    def get_queryset(self):
        return super().get_queryset().select_related('actor')


# CRUDs auxiliares
class SupplierCreateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, CreateView):
    model = Supplier; form_class = SupplierForm; template_name = 'contracts/form.html'; title = 'Nova empresa'; success_url = reverse_lazy('supplier_list')
class SupplierUpdateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, UpdateView):
    model = Supplier; form_class = SupplierForm; template_name = 'contracts/form.html'; title = 'Editar empresa'; success_url = reverse_lazy('supplier_list')
class OrganizationCreateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, CreateView):
    model = Organization; form_class = OrganizationForm; template_name = 'contracts/form.html'; title = 'Nova Organização Militar'; success_url = reverse_lazy('organization_list')
class OrganizationUpdateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, UpdateView):
    model = Organization; form_class = OrganizationForm; template_name = 'contracts/form.html'; title = 'Editar Organização Militar'; success_url = reverse_lazy('organization_list')
class PersonCreateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, CreateView):
    model = Person; form_class = PersonForm; template_name = 'contracts/form.html'; title = 'Novo responsável'; success_url = reverse_lazy('person_list')
class PersonUpdateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, UpdateView):
    model = Person; form_class = PersonForm; template_name = 'contracts/form.html'; title = 'Editar responsável'; success_url = reverse_lazy('person_list')


class RelatedCreateView(LoginRequiredMixin, EditorRequiredMixin, PrefillContractMixin, FormMetaMixin, CreateView):
    template_name = 'contracts/form.html'

    def get_success_url(self):
        contract = getattr(self.object, 'contract', None)
        if contract:
            return contract.get_absolute_url()
        order = getattr(self.object, 'supply_order', None)
        if order:
            return order.contract.get_absolute_url()
        return reverse('dashboard')


class RelatedUpdateView(LoginRequiredMixin, EditorRequiredMixin, FormMetaMixin, UpdateView):
    template_name = 'contracts/form.html'

    def get_success_url(self):
        contract = getattr(self.object, 'contract', None)
        if contract:
            return contract.get_absolute_url()
        order = getattr(self.object, 'supply_order', None)
        if order:
            return order.contract.get_absolute_url()
        return reverse('dashboard')


class ItemCreateView(RelatedCreateView):
    model = ContractItem
    form_class = ContractItemForm
    title = 'Novo item contratual'


class ItemUpdateView(RelatedUpdateView):
    model = ContractItem
    form_class = ContractItemForm
    title = 'Editar item contratual'
class CommitmentCreateView(RelatedCreateView): model = Commitment; form_class = CommitmentForm; title = 'Nova nota de empenho'
class CommitmentUpdateView(RelatedUpdateView): model = Commitment; form_class = CommitmentForm; title = 'Editar nota de empenho'
class SupplyOrderCreateView(RelatedCreateView):
    model = SupplyOrder
    form_class = SupplyOrderForm
    title = 'Nova ordem de fornecimento'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form')
        context['item_locations_map'] = getattr(form, 'item_locations_map', {})
        context['order_items_url_template'] = reverse('contract_order_items', args=[0]).replace('/0/', '/__id__/')
        return context


class SupplyOrderUpdateView(RelatedUpdateView):
    model = SupplyOrder
    form_class = SupplyOrderForm
    title = 'Editar ordem de fornecimento'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form')
        context['item_locations_map'] = getattr(form, 'item_locations_map', {})
        context['order_items_url_template'] = reverse('contract_order_items', args=[0]).replace('/0/', '/__id__/')
        return context
class DeliveryCreateView(RelatedCreateView): model = Delivery; form_class = DeliveryForm; title = 'Registrar entrega'
class DeliveryUpdateView(RelatedUpdateView): model = Delivery; form_class = DeliveryForm; title = 'Editar entrega'
class ChangeCreateView(RelatedCreateView): model = ContractChange; form_class = ContractChangeForm; title = 'Nova alteração contratual'
class ChangeUpdateView(RelatedUpdateView): model = ContractChange; form_class = ContractChangeForm; title = 'Editar alteração contratual'
class ProcessCreateView(RelatedCreateView): model = AdministrativeProcess; form_class = AdministrativeProcessForm; title = 'Novo PAAI/processo administrativo'
class ProcessUpdateView(RelatedUpdateView): model = AdministrativeProcess; form_class = AdministrativeProcessForm; title = 'Editar PAAI/processo administrativo'


class DocumentCreateView(RelatedCreateView):
    model = Document
    form_class = DocumentForm
    title = 'Anexar documento'

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        return super().form_valid(form)


class DocumentUpdateView(RelatedUpdateView):
    model = Document
    form_class = DocumentForm
    title = 'Editar documento'


class RelatedDeleteView(LoginRequiredMixin, EditorRequiredMixin, DeleteView):
    template_name = 'contracts/confirm_delete.html'

    def get_success_url(self):
        contract = getattr(self.object, 'contract', None)
        order = getattr(self.object, 'supply_order', None)
        if contract:
            return contract.get_absolute_url()
        if order:
            return order.contract.get_absolute_url()
        return reverse('dashboard')

    def form_valid(self, form):
        messages.success(self.request, 'Registro excluído.')
        return super().form_valid(form)


class ItemDeleteView(RelatedDeleteView): model = ContractItem
class CommitmentDeleteView(RelatedDeleteView): model = Commitment
class SupplyOrderDeleteView(RelatedDeleteView): model = SupplyOrder
class DeliveryDeleteView(RelatedDeleteView): model = Delivery
class ChangeDeleteView(RelatedDeleteView): model = ContractChange
class ProcessDeleteView(RelatedDeleteView): model = AdministrativeProcess
class DocumentDeleteView(RelatedDeleteView): model = Document


class ImportUploadView(LoginRequiredMixin, ManagerRequiredMixin, View):
    template_name = 'contracts/import_upload.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ImportWorkbookForm()})

    def post(self, request):
        form = ImportWorkbookForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})
        file = form.cleaned_data['file']
        sheet_name = form.cleaned_data['sheet_name']
        try:
            preview = preview_workbook(file, sheet_name)
        except (ValueError, OSError) as exc:
            form.add_error('file', str(exc))
            return render(request, self.template_name, {'form': form})
        batch = ImportBatch.objects.create(
            filename=file.name,
            sheet_name=sheet_name,
            created_by=request.user,
            row_count=preview['summary']['rows'],
            error_count=preview['summary']['errors'],
            warning_count=preview['summary']['warnings'],
            preview_data=preview,
        )
        return redirect('import_preview', pk=batch.pk)


class ImportPreviewView(LoginRequiredMixin, ManagerRequiredMixin, View):
    template_name = 'contracts/import_preview.html'

    def get_batch(self, pk):
        batch = get_object_or_404(ImportBatch, pk=pk)
        if batch.status != ImportBatch.Status.PREVIEW:
            raise Http404('Este lote não está mais disponível para confirmação.')
        return batch

    def get(self, request, pk):
        batch = self.get_batch(pk)
        return render(request, self.template_name, {'batch': batch, 'preview': batch.preview_data})

    def post(self, request, pk):
        batch = self.get_batch(pk)
        if batch.error_count:
            messages.error(request, 'A importação não pode ser confirmada enquanto houver erros impeditivos.')
            return redirect('import_preview', pk=batch.pk)
        try:
            result = import_preview(batch.preview_data, actor=request.user, filename=batch.filename)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('import_preview', pk=batch.pk)
        batch.status = ImportBatch.Status.IMPORTED
        batch.result = result
        batch.preview_data = {}
        batch.save(update_fields=['status', 'result', 'preview_data', 'updated_at'])
        messages.success(request, 'Planilha importada com sucesso.')
        return render(request, 'contracts/import_result.html', {'batch': batch, 'result': result})


class ImportCancelView(LoginRequiredMixin, ManagerRequiredMixin, View):
    def post(self, request, pk):
        batch = get_object_or_404(ImportBatch, pk=pk, status=ImportBatch.Status.PREVIEW)
        batch.status = ImportBatch.Status.CANCELED
        batch.preview_data = {}
        batch.save(update_fields=['status', 'preview_data', 'updated_at'])
        messages.info(request, 'Importação cancelada sem gravar dados.')
        return redirect('dashboard')


def _contract_report_rows():
    rows = []
    for contract in Contract.objects.select_related('supplier', 'manager', 'reference_organization'):
        rows.append([
            contract.number,
            contract.supplier.name,
            contract.process_number,
            contract.procurement_number,
            contract.reference_organization.acronym if contract.reference_organization else '',
            contract.calculated_status_label,
            contract.signature_date,
            contract.end_date,
            contract.days_to_expiry if contract.days_to_expiry is not None else '',
            contract.current_value,
            contract.committed_value,
            contract.balance,
            f'{contract.delivery_percentage:.1f}%'.replace('.', ','),
        ])
    return rows


REPORT_HEADERS = [
    'Contrato', 'Empresa', 'PAG/Processo', 'Pregão', 'OM TR', 'Status', 'Assinatura', 'Fim da vigência',
    'Dias para vencer', 'Valor atualizado', 'Valor empenhado', 'Saldo', '% entregue',
]


def _procurement_report_rows():
    rows = []
    for procurement in Procurement.objects.select_related('requesting_organization').prefetch_related('items'):
        rows.append([
            procurement.number,
            '',
            procurement.requesting_organization.acronym if procurement.requesting_organization else '',
            procurement.get_status_display(),
            procurement.opening_date,
            procurement.items.count(),
            procurement.estimated_value,
        ])
    return rows


PROCUREMENT_REPORT_HEADERS = [
    'Pregão', 'OM requisitante', 'Situação', 'Abertura', 'Itens', 'Valor estimado',
]


class ExportContractsCsvView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="contratos_sdap.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow(REPORT_HEADERS)
        for row in _contract_report_rows():
            writer.writerow(row)
        AuditLog.objects.create(actor=request.user, action=AuditLog.Action.EXPORT, model_name='Contratos', representation='Relatório CSV')
        return response


class ExportContractsXlsxView(LoginRequiredMixin, View):
    def get(self, request):
        content = write_simple_xlsx(REPORT_HEADERS, _contract_report_rows(), 'Contratos')
        response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="contratos_sdap.xlsx"'
        AuditLog.objects.create(actor=request.user, action=AuditLog.Action.EXPORT, model_name='Contratos', representation='Relatório XLSX')
        return response


class DownloadImportTemplateView(LoginRequiredMixin, View):
    def get(self, request):
        headers = [
            'STATUS', 'CONTRATO', 'PAG', 'EMPRESA', 'PREGÃO', 'ITEM PREGÃO', 'CÓD. TDV', 'NOMENCLATURA',
            'TIPO', 'QTD EMPENHADO', 'ANO EMPENHO', 'EMPENHO', 'DATA NE', 'AÇÃO ORÇAMENTÁRIA', 'PTRES',
            'ORIGEM CRÉDITO', 'PI', 'VALOR UNITÁRIO', 'VALOR TOTAL', 'OM TERMO DE REFERÊNCIA', 'OM DESTINO',
            'GESTOR', 'SUPLENTE', 'ASSINATURA DO CONTRATO', 'VIGÊNCIA FINAL CONTRATO',
            'ASSINATURA DA ORD. FORNECIMENTO', 'PRAZO DE ENTREGA', 'OFÍCIO ORDEM FORNECIMENTO À OM',
            'ENTREGUES?', 'VIATURAS ENTREGUES EM:', 'STATUS VIGÊNCIA', 'DIAS P/ VENCER', 'STATUS ENTREGA',
        ]
        sample = [[
            'VIGENTE', '000/CAE-SDAP/2026', '67106.000000/2026-00', 'EMPRESA EXEMPLO LTDA', '90000/2026',
            1, 'P-1/01A-DTS', 'VEÍCULO DE SERVIÇO', 'MODELO EXEMPLO', 1, 2026, '2026NE000001',
            timezone.localdate(), '20XV', '000000', 'SDAP', 'PI000000', Decimal('100000.00'), Decimal('100000.00'),
            'SDAP', 'OM-DESTINO', '1T GESTOR', '2S SUPLENTE', timezone.localdate(),
            timezone.localdate() + timedelta(days=365), timezone.localdate(),
            timezone.localdate(), 'SIGAD: 00000000', 'NÃO', '', 'VIGENTE', '', 'PENDENTE',
        ]]
        content = write_simple_xlsx(headers, sample, 'Planilha1')
        response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="modelo_importacao_sdap.xlsx"'
        return response


class ExportContractsPdfView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise RuntimeError('A dependência reportlab não está instalada.') from exc
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer, pagesize=landscape(A4), rightMargin=10 * mm, leftMargin=10 * mm,
            topMargin=10 * mm, bottomMargin=10 * mm,
        )
        styles = getSampleStyleSheet()
        elements = [Paragraph('Relatório de Contratos — SDAP', styles['Title']), Spacer(1, 5 * mm)]
        data = [['Contrato', 'Empresa', 'Status', 'Fim vigência', 'Dias', 'Valor atualizado', 'Saldo']]
        for row in _contract_report_rows():
            data.append([
                row[0], row[1][:42], row[5], row[7].strftime('%d/%m/%Y') if row[7] else '', row[8],
                ('R$ ' + f'{row[9]:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')),
                ('R$ ' + f'{row[11]:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')),
            ])
        table = Table(data, repeatRows=1, colWidths=[34*mm, 78*mm, 27*mm, 27*mm, 16*mm, 37*mm, 37*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#123B5D')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        elements.append(table)
        document.build(elements)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="contratos_sdap.pdf"'
        AuditLog.objects.create(actor=request.user, action=AuditLog.Action.EXPORT, model_name='Contratos', representation='Relatório PDF')
        return response


class ExportProcurementsCsvView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="pregoes_sdap.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow(PROCUREMENT_REPORT_HEADERS)
        for row in _procurement_report_rows():
            writer.writerow(row)
        AuditLog.objects.create(actor=request.user, action=AuditLog.Action.EXPORT, model_name='Pregões', representation='Relatório CSV')
        return response


class ExportProcurementsXlsxView(LoginRequiredMixin, View):
    def get(self, request):
        content = write_simple_xlsx(PROCUREMENT_REPORT_HEADERS, _procurement_report_rows(), 'Pregoes')
        response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="pregoes_sdap.xlsx"'
        AuditLog.objects.create(actor=request.user, action=AuditLog.Action.EXPORT, model_name='Pregões', representation='Relatório XLSX')
        return response


class ExportProcurementsPdfView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise RuntimeError('A dependência reportlab não está instalada.') from exc

        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=10 * mm,
            leftMargin=10 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )
        styles = getSampleStyleSheet()
        elements = [Paragraph('Relatório de Pregões — SDAP', styles['Title']), Spacer(1, 5 * mm)]
        data = [['Pregão', 'OM requisitante', 'Situação', 'Abertura', 'Itens', 'Valor estimado']]
        for row in _procurement_report_rows():
            data.append([
                row[0],
                row[2] or '—',
                row[3],
                row[4].strftime('%d/%m/%Y') if row[4] else '',
                row[5],
                ('R$ ' + f'{row[6]:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')),
            ])
        table = Table(data, repeatRows=1, colWidths=[40 * mm, 42 * mm, 35 * mm, 28 * mm, 20 * mm, 40 * mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#123B5D')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        elements.append(table)
        document.build(elements)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="pregoes_sdap.pdf"'
        AuditLog.objects.create(actor=request.user, action=AuditLog.Action.EXPORT, model_name='Pregões', representation='Relatório PDF')
        return response


class HelpView(LoginRequiredMixin, TemplateView):
    template_name = 'contracts/help.html'


class ProtectedMediaView(LoginRequiredMixin, View):
    def get(self, request, path):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        requested = (media_root / path).resolve()
        try:
            requested.relative_to(media_root)
        except ValueError as exc:
            raise Http404('Arquivo inválido.') from exc
        if not requested.is_file():
            raise Http404('Arquivo não encontrado.')
        content_type, _ = mimetypes.guess_type(requested.name)
        return FileResponse(requested.open('rb'), content_type=content_type or 'application/octet-stream')
