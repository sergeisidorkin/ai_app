"""Bulk row-order specs for classifier tables (see core.row_order)."""
from core.row_order import RowOrderSpec, register_row_orders

from .models import (
    BusinessEntityAttributeRecord,
    BusinessEntityIdentifierRecord,
    BusinessEntityRecord,
    BusinessEntityRelationRecord,
    LegalEntityIdentifier,
    LegalEntityRecord,
    LivingWage,
    NumcapRecord,
    OKSMCountry,
    OKVCurrency,
    PhysicalEntityIdentifier,
    RussianFederationSubjectCode,
    TerritorialDivision,
)

register_row_orders([
    RowOrderSpec(key="oksm", model=OKSMCountry),
    RowOrderSpec(key="okv", model=OKVCurrency),
    RowOrderSpec(key="lei", model=LegalEntityIdentifier),
    RowOrderSpec(key="pei", model=PhysicalEntityIdentifier),
    RowOrderSpec(key="numcap", model=NumcapRecord),
    RowOrderSpec(key="katd", model=TerritorialDivision),
    RowOrderSpec(key="rfs", model=RussianFederationSubjectCode),
    RowOrderSpec(key="ber", model=BusinessEntityRecord),
    RowOrderSpec(key="bei", model=BusinessEntityIdentifierRecord),
    RowOrderSpec(key="bat", model=BusinessEntityAttributeRecord),
    RowOrderSpec(
        key="bea",
        model=LegalEntityRecord,
        base_filter={"attribute": LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS},
    ),
    RowOrderSpec(key="brl", model=BusinessEntityRelationRecord),
    RowOrderSpec(key="lw", model=LivingWage),
    RowOrderSpec(key="ler", model=LegalEntityRecord),
])
