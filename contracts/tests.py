from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .import_service import import_preview, preview_workbook
from .models import Contract, Delivery, Document, Organization, Procurement, ProcurementItem, ProcurementItemDelivery, Supplier, SupplyOrder
from .xlsx_utils import read_xlsx_sheet, write_simple_xlsx


class XlsxUtilityTests(TestCase):
    def test_write_and_read_xlsx(self):
        content = write_simple_xlsx(['CONTRATO', 'EMPRESA'], [['001/2026', 'EMPRESA TESTE']], 'Planilha1')
        rows = read_xlsx_sheet(SimpleUploadedFile('teste.xlsx', content), 'Planilha1')
        self.assertEqual(rows[0][:2], ['CONTRATO', 'EMPRESA'])
        self.assertEqual(rows[1][:2], ['001/2026', 'EMPRESA TESTE'])


class ImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('gestor', password='SenhaForte123!')

    def workbook(self):
        headers = [
            'STATUS', 'CONTRATO', 'PAG', 'EMPRESA', 'PREGÃO', 'ITEM PREGÃO', 'CÓD. TDV',
            'NOMENCLATURA', 'TIPO', 'QTD EMPENHADO', 'ANO EMPENHO', 'EMPENHO', 'DATA NE',
            'AÇÃO ORÇAMENTÁRIA', 'PTRES', 'ORIGEM CRÉDITO', 'PI', 'VALOR UNITÁRIO',
            'VALOR TOTAL', 'OM TERMO DE REFERÊNCIA', 'OM DESTINO', 'GESTOR', 'SUPLENTE',
            'ASSINATURA DO CONTRATO', 'VIGÊNCIA FINAL CONTRATO', 'ASSINATURA DA ORD. FORNECIMENTO',
            'PRAZO DE ENTREGA', 'OFÍCIO ORDEM FORNECIMENTO À OM', 'ENTREGUES?',
            'VIATURAS ENTREGUES EM:', 'STATUS VIGÊNCIA', 'DIAS P/ VENCER', 'STATUS ENTREGA',
        ]
        today = timezone.localdate()
        row = [
            'VIGENTE', '001/TESTE/2026', '00000.000001/2026-00', 'EMPRESA TESTE LTDA', '90000/2026',
            1, 'P-1/01A-DTS', 'VEÍCULO', 'MODELO TESTE', 2, 2026, '2026NE000001', today,
            '20XV', '123456', 'SDAP', 'PI0001', Decimal('100000'), Decimal('200000'), 'SDAP',
            'OM-TESTE', '1T GESTOR', '2S SUPLENTE', today, today + timedelta(days=365), today,
            today + timedelta(days=90), 'SIGAD: 123456', 'SIM', today + timedelta(days=30),
            'VIGENTE', '', 'ENTREGUE',
        ]
        return SimpleUploadedFile('planilha.xlsx', write_simple_xlsx(headers, [row], 'Planilha1'))

    def test_preview_and_import(self):
        preview = preview_workbook(self.workbook(), 'Planilha1')
        self.assertEqual(preview['summary']['errors'], 0)
        self.assertEqual(preview['summary']['contracts'], 1)
        result = import_preview(preview, actor=self.user, filename='planilha.xlsx')
        self.assertEqual(result['contracts_created'], 1)
        self.assertEqual(Contract.objects.count(), 1)
        self.assertEqual(SupplyOrder.objects.count(), 1)
        self.assertEqual(Delivery.objects.count(), 1)
        self.assertEqual(Contract.objects.get().current_value, Decimal('200000'))
        self.assertEqual(Procurement.objects.count(), 1)
        self.assertEqual(ProcurementItem.objects.count(), 1)
        self.assertEqual(ProcurementItemDelivery.objects.count(), 1)
        contract = Contract.objects.get()
        self.assertIsNotNone(contract.procurement)

    def test_preview_rejects_missing_required_columns(self):
        file = SimpleUploadedFile('invalida.xlsx', write_simple_xlsx(['PAG'], [['x']], 'Planilha1'))
        with self.assertRaises(ValueError):
            preview_workbook(file, 'Planilha1')


class ContractModelTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(name='EMPRESA MODELO')
        self.org = Organization.objects.create(acronym='SDAP', name='SDAP')

    def test_calculated_status(self):
        contract = Contract.objects.create(
            number='001/MODELO/2026', supplier=self.supplier, managing_organization=self.org,
            end_date=timezone.localdate() + timedelta(days=30), current_value=100, initial_value=100,
            status=Contract.Status.ACTIVE,
        )
        self.assertEqual(contract.calculated_status, Contract.Status.EXPIRING)
        self.assertEqual(contract.days_to_expiry, 30)

    def test_copy_items_from_procurement(self):
        procurement = Procurement.objects.create(number='90000/2026')
        procurement_item = ProcurementItem.objects.create(
            procurement=procurement,
            item_number='1',
            code='P-1/01A-DTS',
            nomenclature='VEICULO',
            specification='MODELO TESTE',
            quantity=Decimal('2'),
            unit='UN',
            unit_value_estimate=Decimal('100000'),
        )
        contract = Contract.objects.create(
            number='010/COPIA/2026',
            supplier=self.supplier,
            managing_organization=self.org,
            procurement=procurement,
            initial_value=Decimal('200000'),
            current_value=Decimal('200000'),
        )

        copied = contract.copy_items_from_procurement()
        self.assertEqual(copied, 1)
        item = contract.items.get()
        self.assertEqual(item.origin_procurement_item, procurement_item)
        self.assertEqual(item.quantity, Decimal('2'))

        copied_again = contract.copy_items_from_procurement()
        self.assertEqual(copied_again, 0)


class ViewAndPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('consulta', password='SenhaForte123!')
        self.gestor = User.objects.create_user('gestor', password='SenhaForte123!')
        group = Group.objects.create(name='Gestor')
        self.gestor.groups.add(group)
        Group.objects.get_or_create(name='Fiscal')

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_dashboard_authenticated(self):
        self.client.login(username='consulta', password='SenhaForte123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Painel gerencial')

    def test_read_only_user_cannot_create_contract(self):
        self.client.login(username='consulta', password='SenhaForte123!')
        response = self.client.get(reverse('contract_create'))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_open_import(self):
        self.client.login(username='gestor', password='SenhaForte123!')
        response = self.client.get(reverse('import_upload'))
        self.assertEqual(response.status_code, 200)



    def test_uploaded_document_requires_login_and_is_served_to_authenticated_user(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as media_dir:
            with override_settings(MEDIA_ROOT=Path(media_dir)):
                supplier = Supplier.objects.create(name='EMPRESA DOCUMENTO')
                org = Organization.objects.create(acronym='OM-DOC', name='OM Documento')
                contract = Contract.objects.create(number='004/DOC/2026', supplier=supplier, managing_organization=org, initial_value=0, current_value=0)
                document = Document.objects.create(contract=contract, title='Teste', file=SimpleUploadedFile('teste.txt', b'conteudo protegido'))
                anonymous = self.client.get(document.file.url)
                self.assertEqual(anonymous.status_code, 302)
                self.client.login(username='gestor', password='SenhaForte123!')
                response = self.client.get(document.file.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), b'conteudo protegido')

    def test_report_exports(self):
        self.client.login(username='gestor', password='SenhaForte123!')
        supplier = Supplier.objects.create(name='EMPRESA RELATÓRIO')
        org = Organization.objects.create(acronym='OM-REL', name='OM Relatório')
        procurement = Procurement.objects.create(number='91000/2026', requesting_organization=org)
        ProcurementItem.objects.create(
            procurement=procurement,
            item_number='1',
            specification='Item relatório',
            quantity=Decimal('2'),
            unit='UN',
            unit_value_estimate=Decimal('5000'),
        )
        Contract.objects.create(
            number='003/RELATORIO/2026', supplier=supplier, managing_organization=org,
            current_value=Decimal('12345.67'), initial_value=Decimal('12345.67'),
            end_date=timezone.localdate() + timedelta(days=180), status=Contract.Status.ACTIVE,
        )
        xlsx_response = self.client.get(reverse('export_contracts_xlsx'))
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertTrue(xlsx_response.content.startswith(b'PK'))
        parsed = read_xlsx_sheet(SimpleUploadedFile('relatorio.xlsx', xlsx_response.content), 'Contratos')
        self.assertEqual(parsed[0][0], 'Contrato')
        pdf_response = self.client.get(reverse('export_contracts_pdf'))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertTrue(pdf_response.content.startswith(b'%PDF'))
        csv_response = self.client.get(reverse('export_contracts_csv'))
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn('003/RELATORIO/2026', csv_response.content.decode('utf-8-sig'))

        procurement_xlsx_response = self.client.get(reverse('export_procurements_xlsx'))
        self.assertEqual(procurement_xlsx_response.status_code, 200)
        self.assertTrue(procurement_xlsx_response.content.startswith(b'PK'))
        procurement_parsed = read_xlsx_sheet(SimpleUploadedFile('pregoes.xlsx', procurement_xlsx_response.content), 'Pregoes')
        self.assertEqual(procurement_parsed[0][0], 'Pregão')

        procurement_pdf_response = self.client.get(reverse('export_procurements_pdf'))
        self.assertEqual(procurement_pdf_response.status_code, 200)
        self.assertTrue(procurement_pdf_response.content.startswith(b'%PDF'))

        procurement_csv_response = self.client.get(reverse('export_procurements_csv'))
        self.assertEqual(procurement_csv_response.status_code, 200)
        self.assertIn('91000/2026', procurement_csv_response.content.decode('utf-8-sig'))

        template_response = self.client.get(reverse('import_template'))
        self.assertEqual(template_response.status_code, 200)
        template_rows = read_xlsx_sheet(SimpleUploadedFile('modelo.xlsx', template_response.content), 'Planilha1')
        self.assertEqual(template_rows[0][0], 'STATUS')

    def test_main_pages_render(self):
        self.client.login(username='gestor', password='SenhaForte123!')
        supplier = Supplier.objects.create(name='EMPRESA PÁGINAS')
        org = Organization.objects.create(acronym='OM-PAG', name='OM Páginas')
        contract = Contract.objects.create(
            number='002/PAGINAS/2026', supplier=supplier, managing_organization=org,
            status=Contract.Status.ACTIVE, current_value=1000, initial_value=1000,
            end_date=timezone.localdate() + timedelta(days=200),
        )
        procurement = Procurement.objects.create(number='90001/2026')
        procurement_item = ProcurementItem.objects.create(
            procurement=procurement,
            item_number='1',
            specification='Item de teste',
            quantity=Decimal('1'),
            unit='UN',
            unit_value_estimate=Decimal('1'),
        )
        urls = [
            reverse('contract_list'), reverse('contract_detail', args=[contract.pk]),
            reverse('procurement_list'), reverse('procurement_detail', args=[procurement.pk]),
            reverse('supplier_list'), reverse('organization_list'), reverse('person_list'),
            reverse('commitment_list'), reverse('supplyorder_list'), reverse('delivery_list'),
            reverse('change_list'), reverse('process_list'), reverse('document_list'),
            reverse('audit_list'), reverse('help'), reverse('contract_create'),
            reverse('procurement_create'), reverse('procurement_item_create') + f'?procurement={procurement.pk}',
            reverse('procurement_item_update', args=[procurement_item.pk]),
            reverse('item_create') + f'?contract={contract.pk}',
            reverse('commitment_create') + f'?contract={contract.pk}',
            reverse('supplyorder_create') + f'?contract={contract.pk}',
            reverse('change_create') + f'?contract={contract.pk}',
            reverse('process_create') + f'?contract={contract.pk}',
            reverse('document_create') + f'?contract={contract.pk}',
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_contract_and_procurement_edit_forms_hide_removed_fields(self):
        self.client.login(username='gestor', password='SenhaForte123!')
        supplier = Supplier.objects.create(name='EMPRESA FORM')
        org = Organization.objects.create(acronym='OM-FRM', name='OM Form')
        procurement = Procurement.objects.create(number='90002/2026', requesting_organization=org)
        contract = Contract.objects.create(
            number='100/FORM/2026',
            supplier=supplier,
            managing_organization=org,
            procurement=procurement,
            initial_value=Decimal('30'),
            current_value=Decimal('30'),
        )

        contract_response = self.client.get(reverse('contract_update', args=[contract.pk]))
        self.assertEqual(contract_response.status_code, 200)
        self.assertNotContains(contract_response, 'Fim da garantia')
        self.assertNotContains(contract_response, 'OM do termo de referência')

        procurement_response = self.client.get(reverse('procurement_update', args=[procurement.pk]))
        self.assertEqual(procurement_response.status_code, 200)
        self.assertNotContains(procurement_response, 'OM do termo de referência')

    def test_supply_order_edit_filters_items_by_contract_and_shows_procurement_locations(self):
        self.client.login(username='gestor', password='SenhaForte123!')
        supplier = Supplier.objects.create(name='EMPRESA ORD')
        org = Organization.objects.create(acronym='OM-ORD', name='OM Ordens')
        destination = Organization.objects.create(acronym='OM-DST', name='OM Destino')
        procurement = Procurement.objects.create(number='90003/2026')
        procurement_item = ProcurementItem.objects.create(
            procurement=procurement,
            item_number='1',
            specification='Item de pregão para OF',
            quantity=Decimal('5'),
            unit='UN',
            unit_value_estimate=Decimal('100'),
        )
        ProcurementItemDelivery.objects.create(item=procurement_item, destination=destination, quantity=Decimal('2'))

        contract = Contract.objects.create(
            number='101/ORD/2026',
            supplier=supplier,
            managing_organization=org,
            procurement=procurement,
            initial_value=Decimal('500'),
            current_value=Decimal('500'),
        )
        valid_item = contract.items.create(
            procurement_item='1',
            origin_procurement_item=procurement_item,
            description='Item válido',
            quantity=Decimal('5'),
            unit='UN',
            unit_value=Decimal('100'),
        )
        other_contract = Contract.objects.create(
            number='102/ORD/2026',
            supplier=supplier,
            managing_organization=org,
            initial_value=Decimal('100'),
            current_value=Decimal('100'),
        )
        invalid_item = other_contract.items.create(
            procurement_item='99',
            description='Item de outro contrato',
            quantity=Decimal('1'),
            unit='UN',
            unit_value=Decimal('100'),
        )

        order = SupplyOrder.objects.create(
            contract=contract,
            item=valid_item,
            destination=destination,
            quantity=Decimal('2'),
            value=Decimal('200'),
        )

        response = self.client.get(reverse('supplyorder_update', args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(valid_item.pk))
        self.assertNotContains(response, 'Item de outro contrato')
        self.assertContains(response, 'OMs de referência do item do pregão')

    def test_procurement_item_form_rejects_planned_quantity_above_item_quantity(self):
        self.client.login(username='gestor', password='SenhaForte123!')
        org = Organization.objects.create(acronym='OM-VLD', name='OM Validação')
        procurement = Procurement.objects.create(number='92000/2026')

        response = self.client.post(reverse('procurement_item_create'), {
            'procurement': procurement.pk,
            'item_number': '1',
            'code': 'COD-1',
            'nomenclature': 'Teste',
            'specification': 'Especificação teste',
            'quantity': '1',
            'unit': 'UN',
            'unit_value_estimate': '10',
            'delivery_locations-TOTAL_FORMS': '1',
            'delivery_locations-INITIAL_FORMS': '0',
            'delivery_locations-MIN_NUM_FORMS': '0',
            'delivery_locations-MAX_NUM_FORMS': '1000',
            'delivery_locations-0-destination': org.pk,
            'delivery_locations-0-quantity': '2',
            'delivery_locations-0-notes': 'Acima do limite',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A soma das quantidades por OM destino não pode ultrapassar a quantidade total do item.')
