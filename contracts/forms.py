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
            'number', 'supplier', 'reference_organization',
            'manager', 'substitute_manager', 'technical_inspector', 'substitute_inspector',
            'procurement',
            'process_number', 'subprocess_number', 'law', 'status',
            'signature_date', 'start_date', 'end_date',
            'initial_value', 'current_value', 'notes',
        ]
        widgets = {
            'notes': TEXTAREA_WIDGET,
            'signature_date': DATE_WIDGET,
            'start_date': DATE_WIDGET,
            'end_date': DATE_WIDGET,
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'O fim da vigência não pode ser anterior ao início.')

        if self.instance.pk:
            has_items = self.instance.items.exists()
            new_procurement = cleaned.get('procurement')
            if has_items and new_procurement != self.instance.procurement:
                self.add_error('procurement', 'Não é permitido alterar o pregão após inclusão de itens no contrato.')
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('reference_organization', None)
        if self.instance.pk and self.instance.items.exists():
            self.fields['procurement'].disabled = True
            self.fields['procurement'].help_text = 'Pregão bloqueado: já existem itens vinculados ao contrato.'
        else:
            self.fields['procurement'].help_text = 'Pode ser alterado enquanto o contrato não possuir itens.'


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        posted_contract = self.data.get(self.add_prefix('contract')) if self.is_bound else None
        contract = posted_contract or self.initial.get('contract') or getattr(self.instance, 'contract', None)
        contract_id = getattr(contract, 'id', contract)
        queryset = ProcurementItem.objects.none()
        if contract_id:
            contract_obj = Contract.objects.select_related('procurement').filter(pk=contract_id).first()
            if contract_obj and contract_obj.procurement_id:
                queryset = ProcurementItem.objects.filter(procurement_id=contract_obj.procurement_id)
                self.fields['origin_procurement_item'].required = True
                self.fields['origin_procurement_item'].help_text = 'Selecione um item do pregão vinculado ao contrato.'
            else:
                self.fields['origin_procurement_item'].help_text = 'O contrato não possui pregão vinculado.'
        self.fields['origin_procurement_item'].queryset = queryset
        self.fields['procurement_item'].widget.attrs['readonly'] = 'readonly'

    def clean(self):
        cleaned = super().clean()
        contract = cleaned.get('contract')
        origin_item = cleaned.get('origin_procurement_item')
        if contract and contract.procurement_id:
            if not origin_item:
                self.add_error('origin_procurement_item', 'Selecione um item do pregão vinculado ao contrato.')
            elif origin_item.procurement_id != contract.procurement_id:
                self.add_error('origin_procurement_item', 'O item selecionado não pertence ao pregão do contrato.')
            else:
                cleaned['procurement_item'] = origin_item.item_number
        return cleaned


class ProcurementForm(StyledModelForm):
    class Meta:
        model = Procurement
        fields = ['number', 'law', 'opening_date', 'status', 'notes']
        widgets = {
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
            'contract', 'item', 'commitment', 'procurement_destinations', 'destination', 'official_reference',
            'issue_date', 'sent_date', 'deadline', 'quantity', 'value', 'status',
            'reported_delivery', 'reported_delivery_date_text', 'notes',
        ]
        widgets = {
            'procurement_destinations': forms.Textarea(attrs={'rows': 2}),
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

        # Campo de referência do pregão é sempre derivado do item selecionado.
        refs = self._build_procurement_destinations_text(item)
        cleaned['procurement_destinations'] = refs
        return cleaned

    @staticmethod
    def _build_procurement_destinations_text(item):
        if not item or not item.origin_procurement_item_id:
            return ''
        locations = list(
            item.origin_procurement_item.delivery_locations.select_related('destination').values_list('destination__acronym', 'quantity')
        )
        return ', '.join(f'{acronym} ({quantity})' for acronym, quantity in locations) if locations else ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_locations_map = {}
        self.fields['procurement_destinations'].disabled = True
        self.fields['procurement_destinations'].help_text = 'Campo de referência fixo do item do pregão.'
        posted_contract = self.data.get(self.add_prefix('contract')) if self.is_bound else None
        contract = posted_contract or self.initial.get('contract') or getattr(self.instance, 'contract', None)
        contract_id = getattr(contract, 'id', contract)
        if contract_id:
            queryset = ContractItem.objects.filter(contract_id=contract_id).select_related('origin_procurement_item')
            self.fields['item'].queryset = queryset
            self.fields['item'].label_from_instance = lambda item: f'Item {item.procurement_item or "s/n"} — {item.nomenclature or item.description[:40]}'
            for item in queryset:
                self.item_locations_map[str(item.pk)] = self._build_procurement_destinations_text(item)

        posted_item_id = None
        if self.is_bound:
            posted_item_id = self.data.get(self.add_prefix('item'))
        selected_item = None
        if posted_item_id:
            selected_item = ContractItem.objects.filter(pk=posted_item_id).select_related('origin_procurement_item').first()
        elif self.instance.pk and self.instance.item_id:
            selected_item = ContractItem.objects.filter(pk=self.instance.item_id).select_related('origin_procurement_item').first()

        if selected_item and selected_item.origin_procurement_item_id:
            refs = self._build_procurement_destinations_text(selected_item)
            if refs:
                self.fields['destination'].help_text = f'OMs de referência do item do pregão: {refs}. Você pode selecionar outra OM destino.'
            self.initial['procurement_destinations'] = refs


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
