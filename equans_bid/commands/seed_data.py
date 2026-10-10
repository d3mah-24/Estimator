"""Load the starter package into Frappe. Idempotent: re-running updates existing records.

bench --site equans.localhost execute equans_bid.commands.seed_data.run
"""

import csv
import json
from pathlib import Path

import frappe

STARTER = Path(__file__).resolve().parent.parent / "data" / "starter"


def _rows(name):
	with open(STARTER / name, newline="") as fh:
		return list(csv.DictReader(fh))


def _upsert(doctype, name, values):
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def seed_productivity_rules():
	rows = _rows("productivity.csv")
	for r in rows:
		_upsert(
			"Productivity Rule",
			r["install_code"],
			{
				"install_code": r["install_code"],
				"work_type": r["work_type"],
				"unit": r["unit"],
				"base_hours_per_unit": float(r["base_hours_per_unit"]),
				"labour_role": r["labour_role"],
				"default_hourly_rate_chf": float(r["default_hourly_rate_chf"]),
				"factor_keys": r["factor_keys"],
			},
		)
	return len(rows)


def seed_catalog():
	rows = _rows("catalog.csv")
	for r in rows:
		_upsert(
			"Catalog Item",
			r["product_id"],
			{
				"product_id": r["product_id"],
				"category": r["category"],
				"subcategory": r["subcategory"],
				"manufacturer": r["manufacturer"],
				"model": r["model"],
				"description": r["description"],
				"unit": r["unit"],
				"list_price_chf": float(r["list_price_chf"]),
				"discount_pct": float(r["discount_pct"]),
				"net_cost_chf": float(r["net_cost_chf"]),
				"install_code": r["install_code"],
				"source_type": r["source_type"],
				"supplier_quote_required": 1 if r["supplier_quote_required"].lower() == "true" else 0,
			},
		)
	return len(rows)


def seed_parameters():
	params = json.loads((STARTER / "project_parameters.json").read_text())
	doc = frappe.get_single("Project Parameter")
	doc.parameters = json.dumps(params, indent=2)
	doc.save(ignore_permissions=True)


def run():
	rules = seed_productivity_rules()
	items = seed_catalog()
	seed_parameters()
	frappe.db.commit()
	print(f"Seeded {rules} productivity rules, {items} catalog items, project parameters.")
