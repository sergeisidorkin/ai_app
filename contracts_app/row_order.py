"""Bulk row-order specs for contract reference tables (see core.row_order).

The contracts project registry keeps its dedicated endpoint
(``contracts_project_registration_row_order``).
"""
from core.row_order import RowOrderSpec, register_row_orders, staff_only

from .models import ContractSubject, ContractTemplate, ContractVariable

CT_HX_EVENT = "contract-templates-updated"
FP_HX_EVENT = "field-params-updated"

register_row_orders([
    RowOrderSpec(key="contract-template", model=ContractTemplate, permission=staff_only, events={CT_HX_EVENT: True}),
    RowOrderSpec(key="contract-variable", model=ContractVariable, permission=staff_only, events={CT_HX_EVENT: True}),
    RowOrderSpec(key="contract-subject", model=ContractSubject, permission=staff_only, events={FP_HX_EVENT: True}),
])
