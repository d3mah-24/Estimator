"""Deterministic position pricing. Pure Python: no Frappe, no LLM.

Formulas (starter package README):
	material cost  = quantity x net unit cost x (1 + material waste %)
	install hours  = quantity x base hours per unit x project factors
	labour cost    = install hours x hourly rate
	direct cost    = material cost + labour cost

`site_efficiency` is applied as 1 / site_efficiency; every other factor named in the
rule's `factor_keys` is multiplied directly.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
INVERSE_FACTORS = {"site_efficiency"}


def D(value) -> Decimal:
	"""Decimal from float/str/int without binary float noise."""
	if isinstance(value, Decimal):
		return value
	return Decimal(str(value))


def money(value: Decimal) -> Decimal:
	return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PositionCost:
	material_cost: Decimal
	labour_hours: Decimal
	labour_rate: Decimal
	labour_cost: Decimal
	direct_cost: Decimal

	def as_dict(self) -> dict:
		return {
			"material_cost": float(self.material_cost),
			"labour_hours": float(self.labour_hours),
			"labour_rate": float(self.labour_rate),
			"labour_cost": float(self.labour_cost),
			"direct_cost": float(self.direct_cost),
		}


def parse_factor_keys(factor_keys) -> list[str]:
	if not factor_keys:
		return []
	if isinstance(factor_keys, str):
		return [k.strip() for k in factor_keys.split("|") if k.strip()]
	return list(factor_keys)


def apply_factor_rules(factor_keys, context: dict, rules: list[dict]) -> list[str]:
	"""Swap productivity factors for positions that match a trade's factor rule (data, e.g. a
	sports-hall system uses the sports-hall mounting height). Rule:
	{"field": "system", "pattern": "<regex>", "flags": "i", "replace": {"<factor>": "<factor>"}}"""
	import re

	keys = parse_factor_keys(factor_keys)
	for rule in rules or []:
		value = str(context.get(rule.get("field", "system")) or "")
		flags = re.IGNORECASE if "i" in (rule.get("flags") or "") else 0
		if value and re.search(rule["pattern"], value, flags):
			keys = [rule["replace"].get(k, k) for k in keys]
	return keys


def labour_factor(factor_keys, productivity_factors: dict) -> Decimal:
	"""Product of the rule's project factors; unknown keys raise so a typo never prices silently."""
	factor = Decimal(1)
	for key in parse_factor_keys(factor_keys):
		if key not in productivity_factors:
			raise KeyError(f"Unknown productivity factor: {key}")
		value = D(productivity_factors[key])
		factor *= (Decimal(1) / value) if key in INVERSE_FACTORS else value
	return factor


def price_position(
	quantity,
	net_unit_cost,
	base_hours_per_unit,
	hourly_rate,
	factor_keys,
	params: dict,
	quote_override=None,
) -> PositionCost:
	"""Price one position.

	`params` is the parsed project_parameters.json. `quote_override` is a supplier's total
	supply price for the position; when given it replaces the catalogue material cost,
	and installation labour is still added.
	"""
	qty = D(quantity)
	waste = D(params["allowances"]["material_waste_pct"]) / 100

	if quote_override not in (None, ""):
		material = D(quote_override)
	else:
		material = qty * D(net_unit_cost) * (1 + waste)

	hours = qty * D(base_hours_per_unit) * labour_factor(factor_keys, params["productivity_factors"])
	rate = D(hourly_rate)
	labour = hours * rate

	material, labour = money(material), money(labour)
	return PositionCost(
		material_cost=material,
		labour_hours=hours.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
		labour_rate=rate,
		labour_cost=labour,
		direct_cost=material + labour,
	)
