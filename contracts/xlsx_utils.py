"""Leitura e escrita XLSX com a biblioteca padrão.

O projeto evita depender de Excel instalado no servidor. O leitor cobre valores,
strings compartilhadas e fórmulas com valor em cache; o escritor produz relatórios
simples compatíveis com Excel/LibreOffice.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _open_bytes(source) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if hasattr(source, "seek"):
        source.seek(0)
    data = source.read()
    if hasattr(source, "seek"):
        source.seek(0)
    return data


def _column_index(reference: str) -> int:
    letters = "".join(ch for ch in reference if ch.isalpha()).upper()
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter) - 64)
    return max(0, value - 1)


def _column_name(index: int) -> str:
    index += 1
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def list_xlsx_sheets(source) -> list[str]:
    data = _open_bytes(source)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
        return [
            node.attrib.get("name", "")
            for node in root.findall(f".//{{{MAIN_NS}}}sheet")
        ]


def read_xlsx_sheet(source, sheet_name: str | None = None) -> list[list[object]]:
    data = _open_bytes(source)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{MAIN_NS}}}si"):
                text = "".join(
                    (node.text or "") for node in item.iter(f"{{{MAIN_NS}}}t")
                )
                shared_strings.append(text)

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall(f".//{{{MAIN_NS}}}sheet")
        if not sheets:
            return []
        selected = None
        if sheet_name:
            for sheet in sheets:
                if (
                    sheet.attrib.get("name", "").strip().casefold()
                    == sheet_name.strip().casefold()
                ):
                    selected = sheet
                    break
            if selected is None:
                available = ", ".join(sheet.attrib.get("name", "") for sheet in sheets)
                raise ValueError(
                    f"A aba “{sheet_name}” não foi encontrada. Abas disponíveis: {available}."
                )
        else:
            selected = sheets[0]

        rel_id = selected.attrib.get(f"{{{REL_NS}}}id")
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for relation in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            if relation.attrib.get("Id") == rel_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise ValueError("Não foi possível localizar a estrutura interna da aba.")
        target = target.lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        sheet_path = re.sub(r"/+", "/", sheet_path)
        root = ET.fromstring(archive.read(sheet_path))

        result: list[list[object]] = []
        for row in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
            values: list[object] = []
            for cell in row.findall(f"{{{MAIN_NS}}}c"):
                ref = cell.attrib.get("r", "")
                column = _column_index(ref)
                while len(values) <= column:
                    values.append(None)
                cell_type = cell.attrib.get("t")
                value_node = cell.find(f"{{{MAIN_NS}}}v")
                value: object = None
                if cell_type == "inlineStr":
                    inline = cell.find(f"{{{MAIN_NS}}}is")
                    value = (
                        "".join(
                            (node.text or "") for node in inline.iter(f"{{{MAIN_NS}}}t")
                        )
                        if inline is not None
                        else ""
                    )
                elif value_node is not None:
                    raw = value_node.text or ""
                    if cell_type == "s":
                        try:
                            value = shared_strings[int(raw)]
                        except (ValueError, IndexError):
                            value = raw
                    elif cell_type == "b":
                        value = raw == "1"
                    elif cell_type in {"str", "e"}:
                        value = raw
                    else:
                        try:
                            number = float(raw)
                            value = int(number) if number.is_integer() else number
                        except ValueError:
                            value = raw
                values[column] = value
            result.append(values)
        max_columns = max((len(row) for row in result), default=0)
        for row in result:
            row.extend([None] * (max_columns - len(row)))
        return result


def excel_serial(value: date | datetime) -> float:
    if isinstance(value, datetime):
        value = value.date()
    epoch = date(1899, 12, 30)
    return float((value - epoch).days)


def _safe_xml_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)
    return escape(text)


def _cell_xml(row_index: int, col_index: int, value: object, style: int = 0) -> str:
    ref = f"{_column_name(col_index)}{row_index}"
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (date, datetime)):
        return f'<c r="{ref}" s="3"><v>{excel_serial(value)}</v></c>'
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            selected_style = style or (2 if isinstance(value, Decimal) else 0)
            style_attr = f' s="{selected_style}"' if selected_style else ""
            return f'<c r="{ref}"{style_attr}><v>{number}</v></c>'
    text = _safe_xml_text(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return (
        f'<c r="{ref}" t="inlineStr"{style_attr}><is><t{preserve}>{text}</t></is></c>'
    )


def write_simple_xlsx(
    headers: list[str], rows: list[list[object]], sheet_name: str = "Relatório"
) -> bytes:
    sheet_name = re.sub(r"[\\/*?:\[\]]", "-", sheet_name)[:31] or "Relatório"
    all_rows = [headers] + rows
    widths = []
    for col in range(len(headers)):
        max_length = max(
            (
                len(str(row[col])) if col < len(row) and row[col] is not None else 0
                for row in all_rows
            ),
            default=10,
        )
        widths.append(min(42, max(10, max_length + 2)))

    row_xml = []
    for row_idx, row in enumerate(all_rows, start=1):
        cells = []
        for col_idx, value in enumerate(row):
            style = 1 if row_idx == 1 else 0
            cells.append(_cell_xml(row_idx, col_idx, value, style))
        row_xml.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    last_col = _column_name(max(0, len(headers) - 1))
    dimension = f"A1:{last_col}{max(1, len(all_rows))}"
    cols_xml = "".join(
        f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
        for i, width in enumerate(widths, start=1)
    )

    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{MAIN_NS}">
  <dimension ref="{dimension}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>{cols_xml}</cols>
  <sheetData>{''.join(row_xml)}</sheetData>
  <autoFilter ref="{dimension}"/>
</worksheet>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}"><sheets><sheet name="{_safe_xml_text(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
    styles_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{MAIN_NS}">
  <numFmts count="2"><numFmt numFmtId="164" formatCode="R$ #,##0.00"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy"/></numFmts>
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF123B5D"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="2"><border/><border><left style="thin"><color rgb="FFD9E2EC"/></left><right style="thin"><color rgb="FFD9E2EC"/></right><top style="thin"><color rgb="FFD9E2EC"/></top><bottom style="thin"><color rgb="FFD9E2EC"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="4">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Gestão de Contratos SDAP</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Gestão de Contratos SDAP</Application></Properties>"""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
    return output.getvalue()
