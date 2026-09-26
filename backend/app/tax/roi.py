"""Public donation ROI calculator for recruiting restaurants. Shows every input and formula.
Never assumes a tax rate or a hauling cost."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from app.tax import calc

LBS_SOURCE = "https://www.feedingamerica.org/ways-to-give/faq/about-our-claims"


def estimate(avg_menu_price: float, food_cost_pct: float, meals_per_week: float, weeks_per_year: float,
             tax_rate_pct: Optional[float] = None, hauling_cost_per_lb: Optional[float] = None,
             lbs_per_meal: float = 1.2) -> Dict[str, Any]:
    meals = Decimal(str(meals_per_week)) * Decimal(str(weeks_per_year))
    fmv_meal = calc.money(avg_menu_price)
    basis_meal = calc.money(Decimal(str(avg_menu_price)) * Decimal(str(food_cost_pct)) / 100)
    line = calc.compute_line(float(meals), float(fmv_meal), float(basis_meal), False, True)
    saved = calc.tax_saved(line.extra_benefit_vs_discarding, tax_rate_pct)
    hauling = (calc.money(meals * Decimal(str(lbs_per_meal)) * Decimal(str(hauling_cost_per_lb)))
               if hauling_cost_per_lb is not None else None)
    return {
        "inputs": {"avg_menu_price": avg_menu_price, "food_cost_pct": food_cost_pct, "meals_per_week": meals_per_week,
                   "weeks_per_year": weeks_per_year, "tax_rate_pct": tax_rate_pct, "hauling_cost_per_lb": hauling_cost_per_lb,
                   "lbs_per_meal": lbs_per_meal, "lbs_per_meal_source": LBS_SOURCE},
        "yearly": {
            "meals_donated": float(meals), "fair_market_value": calc.dollars(line.fmv), "cost_basis": calc.dollars(line.basis),
            "enhanced_deduction": calc.dollars(line.enhanced_deduction),
            "extra_deduction_vs_discarding": calc.dollars(line.extra_benefit_vs_discarding),
            "extra_deduction_note": line.extra_benefit_note,
            "estimated_tax_saved": calc.dollars(saved),
            "estimated_tax_saved_note": "" if saved is not None else "enter your tax rate to see this",
            "avoided_hauling_cost": calc.dollars(hauling),
            "avoided_hauling_cost_note": "" if hauling is not None else "enter your hauling cost per lb to see this",
        },
        "formulas": [
            "meals per year = meals per week x weeks per year",
            "FMV = meals x average menu price; basis = FMV x food cost %",
            "enhanced deduction = FMV if FMV <= basis, else min(basis + 0.5 x (FMV - basis), 2 x basis)",
            "extra deduction vs discarding = enhanced deduction - basis (assumes your food cost is already deducted "
            "through cost of goods sold; not computed when FMV <= basis)",
            "estimated tax saved = extra deduction x your tax rate (only if you entered one)",
            "avoided hauling cost = meals x lbs per meal x your hauling cost per lb (only if you entered one)",
            "annual limit: 15% of taxable income (C corporations) or of aggregate net income from the donating "
            "businesses (others); excess carries forward up to 5 years",
        ],
        "disclaimer": "Illustrative estimate from your inputs. " + calc.DISCLAIMER,
    }
