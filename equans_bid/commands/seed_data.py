"""Load all trades' master data (data/trades/*) and the project parameters. Idempotent.

bench --site equans.localhost execute equans_bid.commands.seed_data.run
bench --site equans.localhost execute equans_bid.commands.seed_data.run --kwargs "{'price_version': '2026-10'}"
"""

import json
from pathlib import Path

import frappe

from equans_bid.setup.master_data import sync_all

# Not imported from the pipeline: seeding must work without the PDF libraries loaded.
PARAMETERS = Path(__file__).resolve().parent.parent / "data" / "starter" / "project_parameters.json"


def seed_parameters(only_if_missing: bool = False):
	"""Project parameters from data/starter/project_parameters.json. With `only_if_missing`,
	parameters already on the site (possibly edited) are kept."""
	doc = frappe.get_single("Project Parameter")
	if only_if_missing and doc.parameters:
		return False
	doc.parameters = json.dumps(json.loads(PARAMETERS.read_text()), indent=2)
	doc.save(ignore_permissions=True)
	return True


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
