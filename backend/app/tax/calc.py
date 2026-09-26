"""Pure calculations for the enhanced deduction for donated food inventory (IRC 170(e)(3)).

No database, no I/O. Money is kept as Decimal cents internally and displayed as whole dollars.
Estimates for a tax preparer, never tax advice, never a final allowable deduction.

Per accepted item (only accepted quantities count):
  if the 25% basis election applies: basis = 0.25 x FMV
  if FMV <= basis: deduction = FMV (no appreciation, so no enhancement)
  else:            deduction = min(basis + 0.5 x (FMV - basis), 2 x basis)
  extra_benefit_vs_discarding = deduction - basis
      only when the business keeps inventory (its basis is already deducted through cost of
      goods sold whether the food is sold, discarded or donated, and donated basis comes out
      of COGS), not with the 25% election, and not when FMV <= basis.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Optional

CENT = Decimal("0.01")
HALF = Decimal("0.5")
ELECTION_FRACTION = Decimal("0.25")
CAP_FRACTION = Decimal("0.15")
CARRYFORWARD_YEARS = 5
ASK_PREPARER = "Ask your tax preparer how this interacts with your expensed costs."
NOT_VERIFIED = ("No estimate yet: your donations went to organizations not yet verified as 501(c)(3). "
                "It will appear once they are verified.")
NEEDS_VALUATION = "No estimate yet: add prices and food costs for your donated items to see this."
DISCLAIMER = "Estimates and records for your tax preparer. Not tax advice."


def money(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def dollars(x: Optional[Decimal]) -> Optional[int]:
    """Display rule: whole dollars, half up."""
    return None if x is None else int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def enhanced_deduction(fmv: Decimal, basis: Decimal) -> Decimal:
    fmv, basis = money(fmv), money(basis)
    if fmv <= basis:
        return fmv
    return money(min(basis + HALF * (fmv - basis), 2 * basis))


@dataclass
class LineResult:
    fmv: Decimal
    basis: Decimal
    enhanced_deduction: Decimal
    extra_benefit_vs_discarding: Optional[Decimal]
    extra_benefit_note: str
    basis_from_election: bool
    enhancement_applies: bool

    def as_json(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("fmv", "basis", "enhanced_deduction", "extra_benefit_vs_discarding"):
            d[k] = None if d[k] is None else float(d[k])
        return d


def compute_line(accepted_quantity: float, fmv_per_unit: float, basis_per_unit: Optional[float],
                 use_election: bool, keeps_inventory: bool) -> LineResult:
    qty = Decimal(str(accepted_quantity))
    fmv = money(Decimal(str(fmv_per_unit)) * qty)
    if use_election:
        basis = money(ELECTION_FRACTION * fmv)
    else:
        if basis_per_unit is None:
            raise ValueError("basis is required unless the 25% election applies")
        basis = money(Decimal(str(basis_per_unit)) * qty)
    deduction = enhanced_deduction(fmv, basis)
    enhancement = fmv > basis
    if keeps_inventory and not use_election and enhancement:
        extra, note = money(deduction - basis), ""
    else:
        extra, note = None, ASK_PREPARER
    return LineResult(fmv, basis, deduction, extra, note, use_election, enhancement)


def tax_saved(extra_benefit: Optional[Decimal], tax_rate_pct: Optional[float]) -> Optional[Decimal]:
    """Only with a rate the business entered. Never assumed."""
    if extra_benefit is None or tax_rate_pct is None:
        return None
    return money(extra_benefit * Decimal(str(tax_rate_pct)) / 100)


def cap_check(total_enhanced_deduction: Decimal, estimated_taxable_income: Optional[float], entity_type: str) -> Optional[Dict[str, Any]]:
    """15% limit warning. Returns None when the business did not enter an income figure."""
    if estimated_taxable_income is None:
        return None
    base_label = ("taxable income" if entity_type == "c_corp"
                  else "aggregate net income from the trades or businesses making the contributions")
    cap = money(CAP_FRACTION * Decimal(str(estimated_taxable_income)))
    over = money(max(Decimal(0), money(total_enhanced_deduction) - cap))
    return {
        "cap": float(cap), "cap_display": dollars(cap), "over_cap": float(over), "over_cap_display": dollars(over),
        "exceeds_cap": over > 0,
        "note": (f"Contributions under IRC 170(e)(3) are limited to 15% of {base_label}. "
                 + (f"About ${dollars(over):,} is over that limit; any excess can generally be carried forward up to "
                    f"{CARRYFORWARD_YEARS} years. " if over > 0 else "")
                 + "This is a warning, not a computed allowable deduction."),
    }
