from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.models.catalog import CatalogItem, LaborRole
from app.services.stock import IssueResult, TWO_PLACES


def _as_decimal(value: object, quant: Decimal = TWO_PLACES) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    else:
        result = Decimal(str(value))
    return result.quantize(quant, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class RateResolution:
    bill_rate: Decimal
    cost_rate: Decimal


def resolve_labor_rates(
    labor_role: LaborRole,
    *,
    bill_rate_override: Optional[object] = None,
    cost_rate_override: Optional[object] = None,
) -> RateResolution:
    bill_rate = _as_decimal(
        bill_rate_override if bill_rate_override is not None else labor_role.bill_rate or Decimal("0.00")
    )
    cost_rate = _as_decimal(
        cost_rate_override if cost_rate_override is not None else labor_role.cost_rate or Decimal("0.00")
    )
    return RateResolution(bill_rate=bill_rate, cost_rate=cost_rate)


def compute_part_usage_cost(issue_result: IssueResult) -> Decimal:
    return issue_result.average_cost.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_part_usage_total(
    qty: object,
    unit_price: object,
) -> Decimal:
    return (_as_decimal(qty, TWO_PLACES) * _as_decimal(unit_price, TWO_PLACES)).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


def compute_invoice_totals(subtotal: Decimal, tax: Decimal) -> Decimal:
    return (subtotal + tax).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

