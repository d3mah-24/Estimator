"""Check a processed Tender against the answer key of a tender package.

	bench --site equans.localhost execute equans_bid.commands.verify.run \\
		--kwargs "{'tender': '<Tender name>', 'package': '<folder with example_lv_positions.csv>'}"

The package (Equans starter package or one from equans_bid.tools.tender_package) holds the
verified rows (`example_lv_positions.csv`) and their expected costs (`expected_output_example.json`).
Each verified row is found among the Tender's positions by page, unit and quantity (the
benchmark rule), then product, status and direct cost are compared. Prints a table and returns
the result; read-only.
"""

import json
from pathlib import Path

import frappe

from equans_bid.api import _catalog_rows
from equans_bid.extraction.benchmark import validate_extraction_against_benchmark

COST_TOLERANCE = 0.01  # CHF


def _positions(doc) -> list[dict]:
	out = []
	for i in doc.items:
		attrs = json.loads(i.attributes) if isinstance(i.attributes, str) and i.attributes else {}
		out.append(
			{
				"position_id": i.position_id,
				"source_page": i.source_page,
				"unit": i.unit,
				"quantity": i.quantity,
				"family": i.family,
				"attributes": attrs,
				"matched_product": i.matched_product,
				"status": i.status,
				"description": i.description,
				"direct_cost": i.direct_cost,
				"quote_override": i.quote_override,
			}
		)
	return out


def check(tender: str, package) -> dict:
	package = Path(package)
	doc = frappe.get_doc("Tender", tender)
	positions = _positions(doc)
	by_id = {p["position_id"]: p for p in positions}
	expected = json.loads((package / "expected_output_example.json").read_text())
	want_cost = {r["lv_id"]: r for r in expected["position_results"]}

	report = validate_extraction_against_benchmark(
		positions, package / "example_lv_positions.csv", _catalog_rows(doc.trade), require_product=True
	)
	rows, ok = [], 0
	for r in report.rows:
		got = by_id.get(r.position_id) or {}
		exp = want_cost.get(r.lv_id, {})
		cost_ok = None
		if got and exp and not got.get("quote_override"):
			cost_ok = abs((got["direct_cost"] or 0) - exp["direct_position_cost_chf"]) <= COST_TOLERANCE
		passed = r.outcome == "OK" and cost_ok is not False
		ok += passed
		rows.append(
			{
				"lv_id": r.lv_id,
				"position_id": r.position_id,
				"result": "OK" if passed else (r.outcome if r.outcome != "OK" else "WRONG_COST"),
				"detail": r.detail,
				"product": got.get("matched_product"),
				"expected_product": exp.get("matched_product_id"),
				"direct_cost": got.get("direct_cost"),
				"expected_cost": exp.get("direct_position_cost_chf"),
				"quoted": bool(got.get("quote_override")),
			}
		)
	matched = {r["position_id"] for r in rows if r["position_id"]}
	subset_direct = sum(by_id[p]["direct_cost"] or 0 for p in matched)
	return {
		"tender": doc.name,
		"package": package.name,
		"verified": len(rows),
		"ok": ok,
		"rows": rows,
		"subset_direct_cost": round(subset_direct, 2),
		"expected_subset_direct_cost": expected["example_subset_summary"]["direct_cost_chf"],
		"other_positions": len(positions) - len(matched),
	}


def run(tender: str, package: str) -> dict:
	result = check(tender, package)
	print(f"Tender {result['tender']} vs {result['package']}\n")
	print(f"{'LV':<8}{'pos':<10}{'result':<15}{'product':<14}{'expected':<14}{'cost':>12}{'expected':>12}")
	for r in result["rows"]:
		cost = "" if r["direct_cost"] is None else f"{r['direct_cost']:,.2f}"
		exp = "" if r["expected_cost"] is None else f"{r['expected_cost']:,.2f}"
		note = "  (supplier quote entered)" if r["quoted"] else (f"  {r['detail']}" if r["detail"] else "")
		print(
			f"{r['lv_id']:<8}{r['position_id'] or '-':<10}{r['result']:<15}{r['product'] or '-':<14}"
			f"{r['expected_product'] or '-':<14}{cost:>12}{exp:>12}{note}"
		)
	print(
		f"\n{result['ok']}/{result['verified']} verified positions correct. Direct cost of these "
		f"positions: {result['subset_direct_cost']:,.2f} CHF (expected "
		f"{result['expected_subset_direct_cost']:,.2f}). {result['other_positions']} further "
		"positions are not in the answer key (e.g. items without a catalogue product)."
	)
	return {k: v for k, v in result.items() if k != "rows"}
