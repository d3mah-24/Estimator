"""Create (or refresh) the demo tender from the starter PDF and process it.

bench --site equans.localhost execute equans_bid.commands.seed_demo.run
"""

import frappe

from equans_bid.api import process_tender_pdf
from equans_bid.extraction.pipeline import STARTER

DEMO_NAME = "Primary School Oberglatt - Ventilation (BKP 244)"


def attach_starter_pdf(tender: str):
	"""Attach the starter tender PDF (private file) so the demo uses the same path as an upload."""
	if frappe.db.get_value("Tender", tender, "tender_file"):
		return
	pdf = STARTER / "BKP_244_LV_Lueftung_260804.pdf"
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": pdf.name,
			"attached_to_doctype": "Tender",
			"attached_to_name": tender,
			"attached_to_field": "tender_file",
			"is_private": 1,
			"content": pdf.read_bytes(),
		}
	).insert()
	frappe.db.set_value("Tender", tender, "tender_file", file.file_url)


def run():
	name = frappe.db.get_value("Tender", {"project_name": DEMO_NAME})
	if not name:
		name = frappe.get_doc({"doctype": "Tender", "project_name": DEMO_NAME}).insert().name
	attach_starter_pdf(name)
	summary = process_tender_pdf(name)
	frappe.db.commit()
	lv1 = frappe.db.get_value(
		"Tender Item",
		{"parent": name, "golden_lv_id": "LV0001"},
		["position_id", "source_page", "quantity", "unit", "matched_product", "direct_cost", "status"],
		as_dict=True,
	)
	print(f"Tender {name}: {len(frappe.get_doc('Tender', name).items)} positions")
	print(f"LV0001: {lv1}")
	print(f"Totals: {summary['totals']}")
	print(f"Baseline: {summary['build_up']['cost_baseline']}")
	return name
