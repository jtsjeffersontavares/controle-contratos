from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from decimal import Decimal

from .models import TimeStampedModel


def update_contract_values_from_items(contract):
    """Atualiza os valores inicial e atualizado do contrato baseado na soma dos itens"""
    if not contract:
        return
    
    total = Decimal('0')
    for item in contract.items.all():
        item_total = (item.quantity or Decimal('0')) * (item.unit_value or Decimal('0'))
        total += item_total
    
    # Atualizar ambos os valores com o total dos itens
    contract.initial_value = total
    contract.current_value = total
    contract.save(update_fields=['initial_value', 'current_value'])


# Signals para atualizar valores do contrato quando itens são adicionados/removidos/editados
from .models import ContractItem

@receiver(post_save, sender=ContractItem)
def update_contract_values_on_item_save(sender, instance, **kwargs):
    """Atualiza os valores do contrato quando um item é salvo"""
    if instance.contract:
        update_contract_values_from_items(instance.contract)


@receiver(post_delete, sender=ContractItem)
def update_contract_values_on_item_delete(sender, instance, **kwargs):
    """Atualiza os valores do contrato quando um item é deletado"""
    if instance.contract:
        update_contract_values_from_items(instance.contract)
