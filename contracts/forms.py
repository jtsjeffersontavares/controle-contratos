from django import forms

from .models import (
    AdministrativeProcess,
    Commitment,
    Contract,
    ContractChange,
    ContractItem,
    Delivery,
    Document,
    Organization,
    Person,
    Procurement,
    ProcurementItem,
    ProcurementItemDelivery,
    Supplier,
    SupplyOrder,
)

DATE_WIDGET = forms.DateInput(attrs={'type': 'date'})
TEXTAREA_WIDGET = forms.Textarea(attrs={'rows': 3})


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            current = field.widget.attrs.get('class', '')
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = f'{current} checkbox-input'.strip()
            else:
                field.widget.attrs['class'] = f'{current} form-control'.strip()


class ContractForm(StyledModelForm):
    class Meta:
        model = Contract
        fields = [
            'number', 'object', 'supplier', 'managing_organization', 'reference_organization',
            'manager', 'substitute_manager', 'technical_inspector', 'substitute_inspector',
            'procurement',
            'procurement_number', 'process_number', 'subprocess_number', 'law', 'status',
            'signature_date', 'start_date', 'end_date',
            'initial_value', 'current_value', 'notes',
        ]
        widgets = {
            'object': forms.Textarea(attrs={'rows': 4}),
            'notes': TEXTAREA_WIDGET,
            'signature_date': DATE_WIDGET,
            'start_date': DATE_WIDGET,
            'end_date': DATE_WIDGET,
            'guarantee_end': DATE_WIDGET,
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'O fim da vigência não pode ser anterior ao início.')
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('reference_organization', None)


class OrganizationForm(StyledModelForm):
    class Meta:
        model = Organization
        fields = '__all__'


class PersonForm(StyledModelForm):
    class Meta:
        model = Person
        fields = '__all__'


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = '__all__'
        widgets = {'address': TEXTAREA_WIDGET, 'notes': TEXTAREA_WIDGET}


class ContractItemForm(StyledModelForm):
    class Meta:
        model = ContractItem
        fields = [
            'contract', 'procurement_item', 'origin_procurement_item', 'code',
            'nomenclature', 'description', 'quantity', 'unit', 'unit_value',
        ]
        widgets = {'description': TEXTAREA_WIDGET}


class ProcurementForm(StyledModelForm):
    class Meta:
        model = Procurement
        fields = ['number', 'object', 'law', 'opening_date', 'status', 'notes']
        widgets = {
            'object': forms.Textarea(attrs={'rows': 4}),
            'notes': TEXTAREA_WIDGET,
            'opening_date': DATE_WIDGET,
        }


class ProcurementItemForm(StyledModelForm):
    class Meta:
        model = ProcurementItem
        fields = ['procurement', 'item_number', 'code', 'nomenclature', 'specification', 'quantity', 'unit', 'unit_value_estimate']
        widgets = {'specification': TEXTAREA_WIDGET}


ProcurementItemDeliveryFormSet = forms.inlineformset_factory(
    ProcurementItem,
    ProcurementItemDelivery,
    fields=['destination', 'quantity', 'notes'],
    extra=3,
    can_delete=True,
)


class CommitmentForm(StyledModelForm):
    class Meta:
        model = Commitment
        fields = [
            'contract', 'item', 'organization', 'number', 'year', 'issue_date', 'quantity', 'value',
            'budget_action', 'ptres', 'credit_origin', 'pi', 'notes',
        ]
        widgets = {'issue_date': DATE_WIDGET, 'notes': TEXTAREA_WIDGET}

    def clean(self):
        cleaned = super().clean()
        contract = cleaned.get('contract')
        item = cleaned.get('item')
        if contract and item and item.contract_id != contract.id:
            self.add_error('item', 'O item selecionado não pertence ao contrato informado.')
        return cleaned


class SupplyOrderForm(StyledModelForm):
    class Meta:
        model = SupplyOrder
        fields = [
            'contract', 'item', 'commitment', 'destination', 'number', 'official_reference',
            'issue_date', 'sent_date', 'deadline', 'quantity', 'value', 'status',
            'reported_delivery', 'reported_delivery_date_text', 'notes',
        ]
        widgets = {
            'issue_date': DATE_WIDGET,
            'sent_date': DATE_WIDGET,
            'deadline': DATE_WIDGET,
            'notes': TEXTAREA_WIDGET,
        }

    def clean(self):
        cleaned = super().clean()
        contract = cleaned.get('contract')
        item = cleaned.get('item')
        commitment = cleaned.get('commitment')
        issue_date = cleaned.get('issue_date')
        deadline = cleaned.get('deadline')
        if contract and item and item.contract_id != contract.id:
            self.add_error('item', 'O item selecionado não pertence ao contrato informado.')
        if contract and commitment and commitment.contract_id != contract.id:
            self.add_error('commitment', 'O empenho selecionado não pertence ao contrato informado.')
        if issue_date and deadline and deadline < issue_date:
            self.add_error('deadline', 'O prazo não pode ser anterior à emissão da ordem.')
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contract = self.initial.get('contract') or getattr(self.instance, 'contract', None)
        contract_id = getattr(contract, 'id', contract)
        if contract_id:
            queryset = ContractItem.objects.filter(contract_id=contract_id).select_related('origin_procurement_item')
            self.fields['item'].queryset = queryset

        posted_item_id = None
        if self.is_bound:
            posted_item_id = self.data.get(self.add_prefix('item'))
        selected_item = None
        if posted_item_id:
            selected_item = ContractItem.objects.filter(pk=posted_item_id).select_related('origin_procurement_item').first()
        elif self.instance.pk and self.instance.item_id:
            selected_item = ContractItem.objects.filter(pk=self.instance.item_id).select_related('origin_procurement_item').first()

        if selected_item and selected_item.origin_procurement_item_id:
            locations = list(
                selected_item.origin_procurement_item.delivery_locations.select_related('destination').values_list('destination__acronym', 'quantity')
            )
            if locations:
                refs = ', '.join(f'{acronym} ({quantity})' for acronym, quantity in locations)
                self.fields['destination'].help_text = f'OMs de referência do item do pregão: {refs}. Você pode selecionar outra OM destino.'


class DeliveryForm(StyledModelForm):
    class Meta:
        model = Delivery
        fields = ['supply_order', 'delivery_date', 'quantity', 'invoice_number', 'acceptance', 'accepted_by', 'notes']
        widgets = {'delivery_date': DATE_WIDGET, 'notes': TEXTAREA_WIDGET}

    def clean(self):
        cleaned = super().clean()
        order = cleaned.get('supply_order')
        quantity = cleaned.get('quantity')
        if order and quantity:
            existing = self.instance.quantity if self.instance.pk else 0
            available = order.pending_quantity + existing
            if quantity > available:
                self.add_error('quantity', f'A quantidade excede o saldo pendente da ordem ({available}).')
        return cleaned


class ContractChangeForm(StyledModelForm):
    class Meta:
        model = ContractChange
        fields = [
            'contract', 'change_type', 'number', 'request_date', 'signed_date',
            'old_end_date', 'new_end_date', 'value_change', 'status', 'justification',
        ]
        widgets = {
            'request_date': DATE_WIDGET,
            'signed_date': DATE_WIDGET,
            'old_end_date': DATE_WIDGET,
            'new_end_date': DATE_WIDGET,
            'justification': TEXTAREA_WIDGET,
        }


class AdministrativeProcessForm(StyledModelForm):
    class Meta:
        model = AdministrativeProcess
        fields = ['contract', 'number', 'reason', 'opened_date', 'deadline', 'status', 'sanction', 'notes']
        widgets = {
            'reason': TEXTAREA_WIDGET,
            'opened_date': DATE_WIDGET,
            'deadline': DATE_WIDGET,
            'sanction': TEXTAREA_WIDGET,
            'notes': TEXTAREA_WIDGET,
        }


class DocumentForm(StyledModelForm):
    class Meta:
        model = Document
        fields = ['contract', 'title', 'category', 'file', 'reference_date', 'description']
        widgets = {'reference_date': DATE_WIDGET, 'description': TEXTAREA_WIDGET}


class ImportWorkbookForm(forms.Form):
    file = forms.FileField(
        label='Planilha XLSX',
        help_text='Aceita a estrutura da planilha SDAP (aba Planilha1) ou o modelo fornecido pelo sistema.',
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx', 'class': 'form-control'}),
    )
    sheet_name = forms.CharField(
        label='Nome da aba',
        initial='Planilha1',
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def clean_file(self):
        file = self.cleaned_data['file']
        if not file.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Envie um arquivo no formato .xlsx.')
        if file.size > 12 * 1024 * 1024:
            raise forms.ValidationError('O arquivo excede 12 MB.')
        return file
