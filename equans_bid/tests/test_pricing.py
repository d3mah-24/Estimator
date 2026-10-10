"""Golden tests: reproduce expected_output_example.json from the starter package.

Pure Python (no database), so they also run with `python -m unittest`.
"""

import csv
import json
import unittest
from decimal import Decimal
from pathlib import Path

from equans_bid.pricing.engine import apply_factor_rules, labour_factor, money, price_position
from equans_bid.pricing.project import (
	bid_range,
	effective_assumptions,
	indicative_price,
	project_baseline,
	selected_bid,
	subset_baseline,
	validate_selection,
)
from equans_bid.trades import load_trade

STARTER = Path(__file__).resolve().parent.parent / "data" / "starter"


def load():
	params = json.loads((STARTER / "project_parameters.json").read_text())
	expected = json.loads((STARTER / "expected_output_example.json").read_text())
	with open(STARTER / "catalog.csv") as fh:
		catalog = {r["product_id"]: r for r in csv.DictReader(fh)}
	with open(STARTER / "productivity.csv") as fh:
		rules = {r["install_code"]: r for r in csv.DictReader(fh)}
	return params, expected, catalog, rules


PARAMS, EXPECTED, CATALOG, RULES = load()


def price_golden(pos):
	product = CATALOG[pos["matched_product_id"]]
	rule = RULES[pos["install_code"]]
	return price_position(
		pos["quantity"],
		product["net_cost_chf"],
		rule["base_hours_per_unit"],
		rule["default_hourly_rate_chf"],
		rule["factor_keys"],
		PARAMS,
	)


class TestPositionPricing(unittest.TestCase):
	def test_lv0001_golden_example(self):
		lv1 = EXPECTED["position_results"][0]
		self.assertEqual(lv1["lv_id"], "LV0001")
		cost = price_golden(lv1)
		self.assertEqual(cost.material_cost, Decimal("388.96"))
		self.assertEqual(cost.labour_cost, Decimal("417.30"))
		self.assertEqual(cost.direct_cost, Decimal("806.26"))

	def test_all_22_golden_positions(self):
		positions = EXPECTED["position_results"]
		self.assertEqual(len(positions), 22)
		for pos in positions:
			with self.subTest(lv_id=pos["lv_id"]):
				cost = price_golden(pos)
				self.assertAlmostEqual(float(cost.material_cost), pos["material_cost_chf"], delta=0.01)
				# The golden file shows hours rounded half-up to 2 dp; money uses unrounded hours.
				self.assertEqual(float(money(cost.labour_hours)), pos["adjusted_install_hours"])
				self.assertAlmostEqual(float(cost.labour_cost), pos["labour_cost_chf"], delta=0.01)
				self.assertAlmostEqual(float(cost.direct_cost), pos["direct_position_cost_chf"], delta=0.01)

	def test_special_hourly_rate_and_timber_factor(self):
		rule = RULES["FIRE_DAMPER"]
		self.assertEqual(rule["default_hourly_rate_chf"], "118")
		self.assertIn("timber_interface", rule["factor_keys"])

	def test_site_efficiency_is_inverse(self):
		factor = labour_factor("site_efficiency", {"site_efficiency": 0.8})
		self.assertEqual(factor, Decimal("1.25"))

	def test_sports_hall_uses_its_mounting_height(self):
		"""The rule is HVAC trade data (trade.json factor_rules), not code."""
		rules = load_trade("HVAC").factor_rules
		keys = apply_factor_rules(
			RULES["DIFFUSER"]["factor_keys"], {"system": "244.05 LA05 Turnhalle"}, rules
		)
		self.assertIn("mounting_height_sports_hall", keys)
		self.assertNotIn("mounting_height_school", keys)
		self.assertEqual(
			apply_factor_rules("site_efficiency|mounting_height_school", {"system": "244.01 LA01"}, rules),
			["site_efficiency", "mounting_height_school"],
		)

	def test_unknown_factor_raises(self):
		with self.assertRaises(KeyError):
			labour_factor("site_efficency", PARAMS["productivity_factors"])

	def test_quote_override_replaces_material_keeps_labour(self):
		pos = next(p for p in EXPECTED["position_results"] if p["lv_id"] == "LV0006")
		rule = RULES[pos["install_code"]]
		base = price_golden(pos)
		quoted = price_position(
			pos["quantity"],
			0,
			rule["base_hours_per_unit"],
			rule["default_hourly_rate_chf"],
			rule["factor_keys"],
			PARAMS,
			quote_override="9000",
		)
		self.assertEqual(quoted.material_cost, Decimal("9000.00"))
		self.assertEqual(quoted.labour_cost, base.labour_cost)


BASELINE = Decimal("414489.12")  # golden subset baseline


class TestBidSelection(unittest.TestCase):
	def test_scenario_selection_equals_the_scenario(self):
		chosen = selected_bid(BASELINE, PARAMS, None, validate_selection({"scenario": "Target"}, PARAMS))
		target = next(s for s in bid_range(BASELINE, PARAMS) if s["scenario"] == "Target")
		self.assertEqual(chosen["bid_price_chf"], 432000)
		for key in ("bid_price_chf", "margin_pct", "estimated_win_probability", "expected_contribution_chf"):
			self.assertEqual(chosen[key], target[key], key)
		self.assertFalse(chosen["below_baseline"])

	def test_scenario_follows_edited_margin(self):
		sel = validate_selection({"scenario": "Target"}, PARAMS)
		chosen = selected_bid(BASELINE, PARAMS, {"scenario_margins_pct": {"Target": 8}}, sel)
		self.assertEqual(chosen["bid_price_chf"], 451000)  # ceil(414489.12 / 0.92 / 1000) * 1000

	def test_own_margin_is_priced_like_a_scenario(self):
		sel = validate_selection({"scenario": "custom", "margin_pct": 5}, PARAMS)
		self.assertEqual(selected_bid(BASELINE, PARAMS, None, sel)["bid_price_chf"], 437000)

	def test_fixed_price_derives_the_margin(self):
		sel = validate_selection({"scenario": "custom", "price_chf": 440000}, PARAMS)
		chosen = selected_bid(BASELINE, PARAMS, None, sel)
		self.assertEqual(chosen["bid_price_chf"], 440000)
		self.assertAlmostEqual(chosen["margin_pct"], 5.8, places=1)  # 1 - 414489.12 / 440000
		self.assertAlmostEqual(chosen["contribution_if_won_chf"], 25510.88, places=2)
		below = selected_bid(BASELINE, PARAMS, None, {"scenario": "custom", "price_chf": 400000})
		self.assertTrue(below["below_baseline"])
		self.assertLess(below["margin_pct"], 0)

	def test_invalid_selections_are_rejected(self):
		for bad in (
			{"scenario": "Greedy"},
			{"scenario": "custom"},
			{"scenario": "custom", "margin_pct": 5, "price_chf": 1},
			{"scenario": "custom", "margin_pct": 45},
			{"scenario": "custom", "price_chf": -5},
		):
			with self.subTest(bad=bad), self.assertRaises(ValueError):
				validate_selection(bad, PARAMS)
		self.assertIsNone(validate_selection(None, PARAMS))


class TestProjectPricing(unittest.TestCase):
	def setUp(self):
		self.costs = [price_golden(p) for p in EXPECTED["position_results"]]
		self.summary = EXPECTED["example_subset_summary"]

	def test_subset_totals(self):
		material = sum(c.material_cost for c in self.costs)
		labour = sum(c.labour_cost for c in self.costs)
		self.assertAlmostEqual(float(material), self.summary["material_cost_chf"], delta=0.01)
		self.assertAlmostEqual(float(labour), self.summary["labour_cost_chf"], delta=0.01)
		self.assertAlmostEqual(float(material + labour), self.summary["direct_cost_chf"], delta=0.01)

	def test_subset_baseline(self):
		direct = sum(c.direct_cost for c in self.costs)
		self.assertEqual(float(subset_baseline(direct, PARAMS)), self.summary["cost_baseline_chf"])

	def test_recommended_bid_range(self):
		baseline = subset_baseline(sum(c.direct_cost for c in self.costs), PARAMS)
		got = bid_range(baseline, PARAMS)
		want = EXPECTED["recommended_bid_range"]["scenarios"]
		for g, w in zip(got, want, strict=True):
			with self.subTest(scenario=w["scenario"]):
				self.assertEqual(g["scenario"], w["scenario"])
				self.assertEqual(g["bid_price_chf"], w["bid_price_chf"])
				self.assertEqual(g["margin_pct"], w["margin_pct"])
				self.assertEqual(g["estimated_win_probability"], w["estimated_win_probability"])
				self.assertAlmostEqual(
					g["expected_contribution_chf"], w["expected_contribution_chf"], delta=0.01
				)

	def test_recommendation_is_best_expected_contribution(self):
		baseline = subset_baseline(sum(c.direct_cost for c in self.costs), PARAMS)
		got = bid_range(baseline, PARAMS)
		self.assertEqual([s["scenario"] for s in got if s["recommended"]], ["Conservative"])
		self.assertEqual(got[0]["contribution_if_won_chf"], round(426000 - 414489.12, 2))

	def test_indicative_price_uses_target_margin(self):
		baseline = subset_baseline(sum(c.direct_cost for c in self.costs), PARAMS)
		self.assertEqual(indicative_price(baseline, PARAMS), {"bid_price_chf": 439000, "margin_pct": 5.5})

	def test_assumption_overrides_are_clamped_and_change_probability(self):
		a = effective_assumptions(
			PARAMS, {"competition_adjustment": -9, "scenario_margins_pct": {"Target": 99, "Nope": 1}}
		)
		self.assertEqual(a["competition_adjustment"], -0.5)
		self.assertEqual(a["scenario_margins_pct"]["Target"], 30.0)
		self.assertNotIn("Nope", a["scenario_margins_pct"])
		baseline = subset_baseline(sum(c.direct_cost for c in self.costs), PARAMS)
		tougher = bid_range(baseline, PARAMS, {"competition_adjustment": -0.15})
		default = bid_range(baseline, PARAMS)
		for t, d in zip(tougher, default, strict=True):
			self.assertEqual(t["bid_price_chf"], d["bid_price_chf"])
			self.assertLess(t["estimated_win_probability"], d["estimated_win_probability"])

	def test_project_baseline_adds_project_costs(self):
		result = project_baseline(0, 0, 0, PARAMS)
		self.assertEqual(result["project_costs"], Decimal("115700.00"))
		self.assertEqual(result["direct_cost"], Decimal("115700.00"))


if __name__ == "__main__":
	unittest.main()
