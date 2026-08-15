from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import (
    Commitment,
    Contract,
    ContractItem,
    Delivery,
    Organization,
    Person,
    Procurement,
    ProcurementItem,
    ProcurementItemDelivery,
    Supplier,
    SupplyOrder,
)
from .xlsx_utils import read_xlsx_sheet

DATE_HEADERS = {
    'DATA_NE', 'ASSINATURA_CONTRATO', 'VIGENCIA_FINAL', 'ASSINATURA_OF', 'PRAZO_ENTREGA',
}

ALIASES = {
    'STATUS': 'STATUS',
    'CONTRATO': 'CONTRATO',
    'PAG': 'PAG',
    'EMPRESA': 'EMPRESA',
    'PREGAO': 'PREGAO',
    'ITEM_PREGAO': 'ITEM_PREGAO',
    'COD_TDV': 'COD_TDV',
    'CODIGO_TDV': 'COD_TDV',
    'NOMENCLATURA': 'NOMENCLATURA',
    'TIPO': 'TIPO',
    'QTD_EMPENHADO': 'QTD_EMPENHADO',
    'QUANTIDADE_EMPENHADA': 'QTD_EMPENHADO',
    'ANO_EMPENHO': 'ANO_EMPENHO',
    'EMPENHO': 'EMPENHO',
    'DATA_NE': 'DATA_NE',
    'ACAO_ORCAMENTARIA': 'ACAO_ORCAMENTARIA',
    'PTRES': 'PTRES',
    'ORIGEM_CREDITO': 'ORIGEM_CREDITO',
    'PI': 'PI',
    'VALOR_UNITARIO': 'VALOR_UNITARIO',
    'VALOR_TOTAL': 'VALOR_TOTAL',
    'OM_TERMO_DE_REFERENCIA': 'OM_TERMO_REFERENCIA',
    'OM_DESTINO': 'OM_DESTINO',
    'GESTOR': 'GESTOR',
    'SUPLENTE': 'SUPLENTE',
    'ASSINATURA_DO_CONTRATO': 'ASSINATURA_CONTRATO',
    'ASSINATURA_CONTRATO': 'ASSINATURA_CONTRATO',
    'VIGENCIA_FINAL_CONTRATO': 'VIGENCIA_FINAL',
    'VIGENCIA_FINAL': 'VIGENCIA_FINAL',
    'ASSINATURA_DA_ORD_FORNECIMENTO': 'ASSINATURA_OF',
    'ASSINATURA_DA_ORDEM_DE_FORNECIMENTO': 'ASSINATURA_OF',
    'ASSINATURA_OF': 'ASSINATURA_OF',
    'PRAZO_DE_ENTREGA': 'PRAZO_ENTREGA',
    'PRAZO_ENTREGA': 'PRAZO_ENTREGA',
    'OFICIO_ORDEM_FORNECIMENTO_A_OM': 'OFICIO_OF',
    'OFICIO_ORDEM_DE_FORNECIMENTO_A_OM': 'OFICIO_OF',
    'OFICIO_SIGAD': 'OFICIO_OF',
    'ENTREGUES': 'ENTREGUES',
    'VIATURAS_ENTREGUES_EM': 'ENTREGA_DATA_TEXTO',
    'DATA_ENTREGA': 'ENTREGA_DATA_TEXTO',
    'STATUS_VIGENCIA': 'STATUS_VIGENCIA',
    'DIAS_P_VENCER': 'DIAS_VENCER',
    'STATUS_ENTREGA': 'STATUS_ENTREGA',
}


def normalize_header(value) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r'[^A-Za-z0-9]+', '_', text.upper()).strip('_')
    return text


def clean_text(value) -> str:
    if value is None:
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def parse_decimal(value, default=Decimal('0')) -> Decimal:
    if value in (None, ''):
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = clean_text(value).replace('R$', '').replace(' ', '')
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return Decimal(text)
    except InvalidOperation:
        return default


def parse_int(value):
    number = parse_decimal(value, default=Decimal('0'))
    return int(number) if number else None


def parse_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        if 1 <= number <= 100000:
            try:
                return date(1899, 12, 30) + timedelta(days=int(number))
            except (ValueError, OverflowError):
                return None
    text = clean_text(value)
    if not text:
        return None
    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        number = float(text)
        if 1 <= number <= 100000:
            try:
                return date(1899, 12, 30) + timedelta(days=int(number))
            except (ValueError, OverflowError):
                return None
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%fZ', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', text)
    if match:
        day, month, year = map(int, match.groups())
        year += 2000 if year < 100 else 0
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def iso_date(value):
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def map_contract_status(value):
    normalized = normalize_header(value)
    mapping = {
        'VIGENTE': Contract.Status.ACTIVE,
        'VENCENDO': Contract.Status.EXPIRING,
        'VENCE_EM_90_DIAS': Contract.Status.EXPIRING,
        'VENCIDO': Contract.Status.EXPIRED,
        'ENCERRADO': Contract.Status.CLOSED,
        'RESCINDIDO': Contract.Status.TERMINATED,
        'SUSPENSO': Contract.Status.SUSPENDED,
        'RASCUNHO': Contract.Status.DRAFT,
    }
    return mapping.get(normalized, Contract.Status.DRAFT)


def map_supply_status(status_value, delivered_value, deadline_value):
    status = normalize_header(status_value)
    delivered = normalize_header(delivered_value)
    if delivered in {'SIM', 'ENTREGUE', 'S'} or status in {'ENTREGUE', 'CONCLUIDA', 'CONCLUIDO'}:
        return SupplyOrder.Status.COMPLETED
    if status in {'ATRASADO', 'ATRASADA'}:
        return SupplyOrder.Status.OVERDUE
    if status in {'PENDENTE', 'NAO'} or delivered in {'NAO', 'N'}:
        return SupplyOrder.Status.PENDING
    if status in {'PARCIAL', 'PARCIALMENTE_ENTREGUE'}:
        return SupplyOrder.Status.PARTIAL
    if status in {'EMITIDA'}:
        return SupplyOrder.Status.ISSUED
    if status in {'ENVIADA'}:
        return SupplyOrder.Status.SENT
    deadline = parse_date(deadline_value)
    if deadline and deadline < date.today():
        return SupplyOrder.Status.OVERDUE
    return SupplyOrder.Status.NOT_INFORMED


def _json_row(row: dict) -> dict:
    output = {}
    for key, value in row.items():
        if isinstance(value, (date, datetime)):
            output[key] = value.isoformat()
        elif isinstance(value, Decimal):
            output[key] = str(value)
        else:
            output[key] = value
    return output


def preview_workbook(source, sheet_name='Planilha1') -> dict:
    matrix = read_xlsx_sheet(source, sheet_name)
    if not matrix:
        raise ValueError('A aba selecionada não contém dados.')
    raw_headers = matrix[0]
    header_map = {}
    recognized = []
    for index, value in enumerate(raw_headers):
        normalized = normalize_header(value)
        canonical = ALIASES.get(normalized)
        if canonical:
            header_map[index] = canonical
            recognized.append(canonical)
    required = {'CONTRATO', 'EMPRESA'}
    missing = required - set(recognized)
    if missing:
        raise ValueError('Colunas obrigatórias ausentes: ' + ', '.join(sorted(missing)) + '.')

    rows = []
    issues = []
    seen_signatures = set()
    for excel_row, values in enumerate(matrix[1:], start=2):
        parsed = {canonical: values[index] if index < len(values) else None for index, canonical in header_map.items()}
        if not any(value not in (None, '') for value in parsed.values()):
            continue
        normalized_row = {
            'EXCEL_ROW': excel_row,
            'STATUS': clean_text(parsed.get('STATUS')),
            'CONTRATO': clean_text(parsed.get('CONTRATO')),
            'PAG': clean_text(parsed.get('PAG')),
            'EMPRESA': clean_text(parsed.get('EMPRESA')),
            'PREGAO': clean_text(parsed.get('PREGAO')),
            'ITEM_PREGAO': clean_text(parsed.get('ITEM_PREGAO')),
            'COD_TDV': clean_text(parsed.get('COD_TDV')),
            'NOMENCLATURA': clean_text(parsed.get('NOMENCLATURA')),
            'TIPO': clean_text(parsed.get('TIPO')),
            'QTD_EMPENHADO': str(parse_decimal(parsed.get('QTD_EMPENHADO'))),
            'ANO_EMPENHO': parse_int(parsed.get('ANO_EMPENHO')),
            'EMPENHO': clean_text(parsed.get('EMPENHO')),
            'DATA_NE': iso_date(parsed.get('DATA_NE')),
            'ACAO_ORCAMENTARIA': clean_text(parsed.get('ACAO_ORCAMENTARIA')),
            'PTRES': clean_text(parsed.get('PTRES')),
            'ORIGEM_CREDITO': clean_text(parsed.get('ORIGEM_CREDITO')),
            'PI': clean_text(parsed.get('PI')),
            'VALOR_UNITARIO': str(parse_decimal(parsed.get('VALOR_UNITARIO'))),
            'VALOR_TOTAL': str(parse_decimal(parsed.get('VALOR_TOTAL'))),
            'OM_TERMO_REFERENCIA': clean_text(parsed.get('OM_TERMO_REFERENCIA')),
            'OM_DESTINO': clean_text(parsed.get('OM_DESTINO')),
            'GESTOR': clean_text(parsed.get('GESTOR')),
            'SUPLENTE': clean_text(parsed.get('SUPLENTE')),
            'ASSINATURA_CONTRATO': iso_date(parsed.get('ASSINATURA_CONTRATO')),
            'VIGENCIA_FINAL': iso_date(parsed.get('VIGENCIA_FINAL')),
            'ASSINATURA_OF': iso_date(parsed.get('ASSINATURA_OF')),
            'PRAZO_ENTREGA': iso_date(parsed.get('PRAZO_ENTREGA')),
            'OFICIO_OF': clean_text(parsed.get('OFICIO_OF')),
            'ENTREGUES': clean_text(parsed.get('ENTREGUES')),
            'ENTREGA_DATA_TEXTO': clean_text(parsed.get('ENTREGA_DATA_TEXTO')),
            'STATUS_VIGENCIA': clean_text(parsed.get('STATUS_VIGENCIA')),
            'STATUS_ENTREGA': clean_text(parsed.get('STATUS_ENTREGA')),
        }
        row_errors = []
        row_warnings = []
        if not normalized_row['CONTRATO']:
            row_errors.append('Contrato não informado.')
        if not normalized_row['EMPRESA']:
            row_errors.append('Empresa não informada.')
        if not normalized_row['OM_DESTINO']:
            row_warnings.append('OM destino não informada; a linha não gerará ordem de fornecimento.')
        if not normalized_row['VIGENCIA_FINAL']:
            row_warnings.append('Vigência final ausente ou inválida.')
        if not normalized_row['EMPENHO']:
            row_warnings.append('Nota de empenho não informada.')
        if Decimal(normalized_row['QTD_EMPENHADO']) < 0:
            row_errors.append('Quantidade negativa.')
        if Decimal(normalized_row['VALOR_TOTAL']) < 0:
            row_errors.append('Valor total negativo.')
        signature = (
            normalized_row['CONTRATO'], normalized_row['ITEM_PREGAO'], normalized_row['COD_TDV'],
            normalized_row['EMPENHO'], normalized_row['OM_DESTINO'], normalized_row['OFICIO_OF'],
        )
        if signature in seen_signatures:
            row_warnings.append('Possível linha duplicada, com a mesma combinação de contrato, item, empenho e destino.')
        seen_signatures.add(signature)
        for message in row_errors:
            issues.append({'row': excel_row, 'level': 'ERRO', 'message': message})
        for message in row_warnings:
            issues.append({'row': excel_row, 'level': 'ALERTA', 'message': message})
        normalized_row['HAS_ERRORS'] = bool(row_errors)
        rows.append(_json_row(normalized_row))

    contracts = {row['CONTRATO'] for row in rows if row['CONTRATO']}
    suppliers = {row['EMPRESA'] for row in rows if row['EMPRESA']}
    destinations = {row['OM_DESTINO'] for row in rows if row['OM_DESTINO']}
    summary = {
        'rows': len(rows),
        'contracts': len(contracts),
        'suppliers': len(suppliers),
        'destinations': len(destinations),
        'errors': sum(issue['level'] == 'ERRO' for issue in issues),
        'warnings': sum(issue['level'] == 'ALERTA' for issue in issues),
        'total_value': str(sum((Decimal(row['VALOR_TOTAL']) for row in rows), Decimal('0'))),
    }
    return {
        'sheet_name': sheet_name,
        'recognized_columns': sorted(set(recognized)),
        'rows': rows,
        'issues': issues,
        'summary': summary,
    }


def _org(acronym: str):
    acronym = clean_text(acronym).upper()
    if not acronym:
        return None
    organization = Organization.objects.filter(acronym__iexact=acronym).first()
    if organization:
        return organization
    return Organization.objects.create(acronym=acronym, name=acronym)


def _supplier(name: str):
    name = clean_text(name)
    supplier = Supplier.objects.filter(name__iexact=name).first()
    if supplier:
        return supplier
    return Supplier.objects.create(name=name)


def _person(text: str):
    text = clean_text(text)
    if not text:
        return None
    match = re.match(r'^(CEL|TC|MAJ|CAP|1T|2T|ASP|SO|1S|2S|3S|CB|S1|S2)\s+(.+)$', text, flags=re.IGNORECASE)
    rank, name = (match.group(1).upper(), match.group(2).strip()) if match else ('', text)
    person = Person.objects.filter(name__iexact=name, organization__isnull=True).first()
    if person:
        if rank and not person.rank:
            person.rank = rank
            person.save(update_fields=['rank', 'updated_at'])
        return person
    return Person.objects.create(name=name, rank=rank)


def _procurement(number: str, reference_org=None):
    number = clean_text(number)
    if not number:
        return None
    procurement = Procurement.objects.filter(number__iexact=number).first()
    if procurement:
        if reference_org and not procurement.requesting_organization_id:
            procurement.requesting_organization = reference_org
            procurement.save(update_fields=['requesting_organization', 'updated_at'])
        return procurement
    return Procurement.objects.create(number=number, requesting_organization=reference_org)


def _item_key(row):
    return (row['ITEM_PREGAO'], row['COD_TDV'], row['TIPO'] or row['NOMENCLATURA'])


@transaction.atomic
def import_preview(preview: dict, actor=None, filename='planilha.xlsx') -> dict:
    if preview.get('summary', {}).get('errors'):
        raise ValueError('A prévia contém erros impeditivos. Corrija a planilha antes de confirmar.')
    rows = preview.get('rows', [])
    grouped_contracts = defaultdict(list)
    for row in rows:
        grouped_contracts[row['CONTRATO']].append(row)

    counters = defaultdict(int)
    for contract_number, contract_rows in grouped_contracts.items():
        first = contract_rows[0]
        supplier = _supplier(first['EMPRESA'])
        managing_org = _org('SDAP')
        reference_org = _org(first['OM_TERMO_REFERENCIA'])
        procurement = _procurement(first['PREGAO'], reference_org)
        manager = _person(first['GESTOR'])
        substitute = _person(first['SUPLENTE'])
        total_value = sum((Decimal(row['VALOR_TOTAL']) for row in contract_rows), Decimal('0'))
        nomenclatures = []
        for row in contract_rows:
            label = row['NOMENCLATURA'] or row['TIPO']
            if label and label not in nomenclatures:
                nomenclatures.append(label)
        object_text = '; '.join(nomenclatures[:8])
        contract, created = Contract.objects.update_or_create(
            number=contract_number,
            defaults={
                'object': object_text,
                'supplier': supplier,
                'managing_organization': managing_org,
                'reference_organization': reference_org,
                'manager': manager,
                'substitute_manager': substitute,
                'procurement': procurement,
                'procurement_number': first['PREGAO'],
                'process_number': first['PAG'],
                'status': map_contract_status(first['STATUS'] or first['STATUS_VIGENCIA']),
                'signature_date': parse_date(first['ASSINATURA_CONTRATO']),
                'start_date': parse_date(first['ASSINATURA_CONTRATO']),
                'end_date': parse_date(first['VIGENCIA_FINAL']),
                'initial_value': total_value,
                'current_value': total_value,
                'imported_from': filename,
            },
        )
        counters['contracts_created' if created else 'contracts_updated'] += 1

        item_groups = defaultdict(list)
        for row in contract_rows:
            item_groups[_item_key(row)].append(row)
        item_objects = {}
        procurement_item_objects = {}
        for key, item_rows in item_groups.items():
            sample = item_rows[0]
            quantity = sum((Decimal(row['QTD_EMPENHADO']) for row in item_rows), Decimal('0'))
            procurement_item = None
            if procurement:
                procurement_item, procurement_item_created = ProcurementItem.objects.update_or_create(
                    procurement=procurement,
                    item_number=sample['ITEM_PREGAO'],
                    code=sample['COD_TDV'],
                    defaults={
                        'nomenclature': sample['NOMENCLATURA'],
                        'model': sample['TIPO'] or sample['NOMENCLATURA'] or 'Item importado',
                        'brand': '',
                        'quantity': quantity,
                        'unit': 'UN',
                        'unit_value': Decimal(sample['VALOR_UNITARIO']),
                    },
                )
                counters['procurement_items_created' if procurement_item_created else 'procurement_items_updated'] += 1
            procurement_item_objects[key] = procurement_item
            item, created = ContractItem.objects.update_or_create(
                contract=contract,
                procurement_item=sample['ITEM_PREGAO'],
                code=sample['COD_TDV'],
                description=sample['TIPO'] or sample['NOMENCLATURA'] or 'Item importado',
                defaults={
                    'origin_procurement_item': procurement_item,
                    'nomenclature': sample['NOMENCLATURA'],
                    'quantity': quantity,
                    'unit': 'UN',
                    'unit_value': Decimal(sample['VALOR_UNITARIO']),
                },
            )
            item_objects[key] = item
            counters['items_created' if created else 'items_updated'] += 1

        delivery_totals = defaultdict(Decimal)
        for row in contract_rows:
            if row['OM_DESTINO']:
                delivery_totals[(_item_key(row), row['OM_DESTINO'])] += Decimal(row['QTD_EMPENHADO'])
        for (item_key, om_text), total_qty in delivery_totals.items():
            procurement_item = procurement_item_objects.get(item_key)
            if not procurement_item:
                continue
            ProcurementItemDelivery.objects.update_or_create(
                item=procurement_item,
                destination=_org(om_text),
                defaults={'quantity': total_qty},
            )

        commitment_groups = defaultdict(list)
        for row in contract_rows:
            if row['EMPENHO']:
                commitment_groups[(_item_key(row), row['EMPENHO'])].append(row)
        commitment_objects = {}
        for (item_key, commitment_number), commitment_rows in commitment_groups.items():
            sample = commitment_rows[0]
            item = item_objects[item_key]
            quantity = sum((Decimal(row['QTD_EMPENHADO']) for row in commitment_rows), Decimal('0'))
            value = sum((Decimal(row['VALOR_TOTAL']) for row in commitment_rows), Decimal('0'))
            commitment, created = Commitment.objects.update_or_create(
                contract=contract,
                number=commitment_number,
                item=item,
                defaults={
                    'year': sample['ANO_EMPENHO'],
                    'issue_date': parse_date(sample['DATA_NE']),
                    'quantity': quantity,
                    'value': value,
                    'budget_action': sample['ACAO_ORCAMENTARIA'],
                    'ptres': sample['PTRES'],
                    'credit_origin': sample['ORIGEM_CREDITO'],
                    'pi': sample['PI'],
                },
            )
            commitment_objects[(item_key, commitment_number)] = commitment
            counters['commitments_created' if created else 'commitments_updated'] += 1

        for row in contract_rows:
            if not row['OM_DESTINO']:
                counters['rows_without_destination'] += 1
                continue
            item_key = _item_key(row)
            item = item_objects[item_key]
            commitment = commitment_objects.get((item_key, row['EMPENHO']))
            destination = _org(row['OM_DESTINO'])
            official_reference = row['OFICIO_OF'] or f'IMPORTAÇÃO LINHA {row["EXCEL_ROW"]}'
            status = map_supply_status(row['STATUS_ENTREGA'], row['ENTREGUES'], row['PRAZO_ENTREGA'])
            order, created = SupplyOrder.objects.update_or_create(
                contract=contract,
                item=item,
                commitment=commitment,
                destination=destination,
                official_reference=official_reference,
                defaults={
                    'number': '',
                    'issue_date': parse_date(row['ASSINATURA_OF']),
                    'deadline': parse_date(row['PRAZO_ENTREGA']),
                    'quantity': Decimal(row['QTD_EMPENHADO']),
                    'value': Decimal(row['VALOR_TOTAL']),
                    'status': status,
                    'reported_delivery': row['ENTREGUES'],
                    'reported_delivery_date_text': row['ENTREGA_DATA_TEXTO'],
                },
            )
            counters['orders_created' if created else 'orders_updated'] += 1
            delivery_date = parse_date(row['ENTREGA_DATA_TEXTO'])
            if status == SupplyOrder.Status.COMPLETED and delivery_date:
                delivery, delivery_created = Delivery.objects.update_or_create(
                    supply_order=order,
                    delivery_date=delivery_date,
                    defaults={
                        'quantity': order.quantity,
                        'acceptance': Delivery.Acceptance.ACCEPTED,
                        'accepted_by': actor if getattr(actor, 'is_authenticated', False) else None,
                        'notes': 'Registro criado a partir da informação da planilha importada.',
                    },
                )
                counters['deliveries_created' if delivery_created else 'deliveries_updated'] += 1

    result = dict(counters)
    result['rows_processed'] = len(rows)
    return result
