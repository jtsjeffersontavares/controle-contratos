from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def brl(value):
    try:
        number = Decimal(value or 0)
    except Exception:
        return value
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


@register.filter
def decimal_pt(value):
    try:
        number = Decimal(value or 0)
    except Exception:
        return value
    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def percent_pt(value):
    try:
        return f"{Decimal(value or 0):.1f}%".replace(".", ",")
    except Exception:
        return value


@register.filter
def status_class(value):
    text = str(value or "").upper()
    if text in {"VIGENTE", "CONCLUIDA", "ACEITA", "ENTREGUE"}:
        return "success"
    if text in {
        "VENCENDO",
        "PENDENTE",
        "EMITIDA",
        "ENVIADA",
        "PARCIAL",
        "APURACAO",
        "DEFESA",
        "ANALISE",
    }:
        return "warning"
    if text in {"VENCIDO", "ATRASADA", "RECUSADA", "RESCINDIDO", "SUSPENSO"}:
        return "danger"
    return "neutral"


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key) if dictionary else None
