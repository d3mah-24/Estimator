"""Project-level build-up: baseline, indicative price and the Recommended Bid Range.

Verified against expected_output_example.json (golden subset of 22 positions):
	baseline     = direct cost x (1 + transport_equipment_pct) x (1 + overhead_pct)
	price        = ceil(baseline / (1 - margin) / round_to) x round_to
	win prob.    = reference_win_probability
	               - points_per_1pct x (price / reference_price - 1) x 100
	               + strategic_appetite_adjustment + competition_adjustment
	               where reference_price = baseline / (1 - target_margin), clamped to [min, max]
	contribution = (price - baseline) x win probability

`project_baseline` additionally adds project costs and the small-material and supplier-package
allowances. The golden file does not cover those, so that part is our own assumption.
"""

import math
from decimal import Decimal

from equans_bid.pricing.engine import D, money


def _pct(value) -> Decimal:
	return D(value) / 100


def subset_baseline(direct_cost, params: dict) -> Decimal:
	transport = _pct(params["allowances"]["transport_equipment_pct"])
	overhead = _pct(params["commercial"]["overhead_pct"])
	return money(D(direct_cost) * (1 + transport) * (1 + overhead))


def project_costs_total(params: dict) -> Decimal:
	pc = params["project_costs"]
	return (
		D(pc["engineering_hours"]) * D(pc["engineering_rate_chf_per_h"])
		+ D(pc["commissioning_hours"]) * D(pc["commissioning_rate_chf_per_h"])
		+ D(pc["hygiene_inspection_chf"])
		+ D(pc["documentation_chf"])
	)


def project_baseline(catalog_material, supplier_material, labour, params: dict) -> dict:
	"""Full-tender build-up (assumption: see module docstring). Returns every step for traceability."""
	al = params["allowances"]
	catalog_material, supplier_material, labour = D(catalog_material), D(supplier_material), D(labour)
	small_material = catalog_material * _pct(al["small_material_pct"])
	contingency = supplier_material * _pct(al["supplier_package_contingency_pct"])
	project_costs = project_costs_total(params)
	direct = catalog_material + supplier_material + labour + small_material + contingency + project_costs
	transport = direct * _pct(al["transport_equipment_pct"])
	overhead = (direct + transport) * _pct(params["commercial"]["overhead_pct"])
	return {
		"catalog_material": money(catalog_material),
		"supplier_material": money(supplier_material),
		"labour": money(labour),
		"small_material": money(small_material),
		"supplier_contingency": money(contingency),
		"project_costs": money(project_costs),
		"direct_cost": money(direct),
		"transport_equipment": money(transport),
		"overhead": money(overhead),
		"cost_baseline": money(direct + transport + overhead),
	}


def selling_price(baseline, margin_pct, round_to=1000) -> int:
	unrounded = D(baseline) / (1 - _pct(margin_pct))
	return math.ceil(unrounded / D(round_to)) * int(round_to)


def win_probability(price, baseline, params: dict) -> Decimal:
	cfg = params["stretch_bid_optimization"]
	reference_price = D(baseline) / (1 - _pct(params["commercial"]["target_margin_pct"]))
	deviation_pct = (D(price) / reference_price - 1) * 100
	p = (
		D(cfg["reference_win_probability"])
		- D(cfg["price_sensitivity_probability_points_per_1pct_price"]) * deviation_pct
		+ D(cfg["strategic_appetite_adjustment"])
		+ D(cfg["competition_adjustment"])
	)
	return max(D(cfg["minimum_probability"]), min(D(cfg["maximum_probability"]), p))


def bid_range(baseline, params: dict, margins: dict | None = None) -> list[dict]:
	"""Aggressive / Target / Conservative scenarios. `margins` overrides the parameter file."""
	cfg = params["stretch_bid_optimization"]
	margins = margins or cfg["scenario_margins_pct"]
	round_to = params["commercial"].get("round_to_chf", 1000)
	scenarios = []
	for name in cfg["scenario_names"]:
		margin = margins[name]
		price = selling_price(baseline, margin, round_to)
		p = win_probability(price, baseline, params)
		scenarios.append(
			{
				"scenario": name,
				"bid_price_chf": price,
				"margin_pct": float(margin),
				"estimated_win_probability": float(round(p, 2)),
				"expected_contribution_chf": float(money((D(price) - D(baseline)) * p)),
			}
		)
	return scenarios
