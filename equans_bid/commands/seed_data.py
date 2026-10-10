"""Load all trades' master data (data/trades/*) and the project parameters. Idempotent.

bench --site equans.localhost execute equans_bid.commands.seed_data.run
bench --site equans.localhost execute equans_bid.commands.seed_data.run --kwargs "{'price_version': '2026-10'}"
"""

import json

import frappe

from equans_bid.extraction.pipeline import STARTER
from equans_bid.setup.master_data import sync_all


def seed_parameters():
	params = json.loads((STARTER / "project_parameters.json").read_text())
	doc = frappe.get_single("Project Parameter")
	doc.parameters = json.dumps(params, indent=2)
	doc.save(ignore_permissions=True)


def run(price_version: str | None = None):
	report = sync_all(price_version)
	seed_parameters()
	frappe.db.commit()
	for trade, parts in report.items():
		print(
			f"{trade}: families {parts['families']}, {parts['productivity']} productivity rules, "
			f"catalogue {parts['catalog']}"
		)
	return report
