"""Integration: trade master data, central catalogue with price snapshots, a second trade."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from equans_bid.api import (
	STARTER_PDF,
	apply_price_refresh,
	export_tender,
	preview_price_refresh,
	process_tender_pdf,
	trade_config,
	update_item,
)
from equans_bid.commands.seed_data import run as seed
from equans_bid.extraction.pipeline import detect_trade
from equans_bid.trades import TRADES_DIR, load_trade

ELECTRICAL_PDF = TRADES_DIR / "electrical" / "sample" / "BKP_231_LV_Elektro_SAMPLE.pdf"


def _attach(tender: str, path, field="tender_file"):
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": path.name,
			"attached_to_doctype": "Tender",
			"attached_to_name": tender,
			"attached_to_field": field,
			"is_private": 1,
			"content": path.read_bytes(),
		}
	).insert()
	return file.file_url


class TestTradeMasterData(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		seed()

	def test_database_config_equals_files(self):
		for folder in ("hvac", "electrical"):
			files, db = load_trade(folder), trade_config(load_trade(folder).code)
			self.assertEqual([f.code for f in files.families], [f.code for f in db.families])
			for a, b in zip(files.families, db.families, strict=True):
				self.assertEqual(
					(a.patterns, a.key_attributes, a.soft_attributes, a.size_strategy, a.labels),
					(b.patterns, b.key_attributes, b.soft_attributes, b.size_strategy, b.labels),
				)
			self.assertEqual(files.factor_rules, db.factor_rules)
			self.assertEqual(files.system_header_pattern, db.system_header_pattern)

	def test_catalogue_is_one_global_master(self):
		self.assertEqual(frappe.db.count("Catalog Item", {"trade": "HVAC"}), 56)
		self.assertEqual(frappe.db.count("Catalog Item", {"trade": "Electrical"}), 8)
		self.assertEqual(frappe.db.count("Catalog Item", {"family": ["is", "not set"]}), 0)
		seed()  # re-running never duplicates
		self.assertEqual(frappe.db.count("Catalog Item"), 64)

	def test_invalid_family_pattern_is_rejected(self):
		doc = frappe.get_doc("Product Family", "supply_valve")
		doc.append("patterns", {"pattern": "unclosed(group"})
		with self.assertRaises(frappe.ValidationError):
			doc.save()


class TestPriceSnapshot(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		seed()
		cls.tender = frappe.get_doc(
			{"doctype": "Tender", "project_name": "Snapshot test", "trade": "HVAC"}
		).insert()
		process_tender_pdf(cls.tender.name, pages=[78, 79, 80])

	def lv1(self):
		doc = frappe.get_doc("Tender", self.tender.name)
		return doc, next(i for i in doc.items if i.matched_product == "P-AIR-001" and i.quantity == 5)

	def test_catalogue_price_change_waits_for_refresh(self):
		original = frappe.db.get_value("Catalog Item", "P-AIR-001", "net_cost_chf")
		try:
			doc, lv1 = self.lv1()
			self.assertAlmostEqual(lv1.direct_cost, 806.26, places=2)
			self.assertEqual(lv1.net_unit_cost, 74.8)
			frappe.db.set_value("Catalog Item", "P-AIR-001", "net_cost_chf", 80.0)

			# An unrelated edit reprices from the snapshot: LV0001 does not move.
			other = next(i for i in doc.items if i.status == "supplier_quote_required")
			update_item(doc.name, other.name, quote_override=9000)
			_, lv1 = self.lv1()
			self.assertAlmostEqual(lv1.direct_cost, 806.26, places=2)

			diff = preview_price_refresh(doc.name)
			change = next(c for c in diff["changes"] if c["item"] == lv1.name)
			self.assertAlmostEqual(change["before"], 806.26, places=2)
			self.assertAlmostEqual(change["after"], 5 * 80.0 * 1.04 + 417.30, places=2)
			_, lv1 = self.lv1()
			self.assertAlmostEqual(lv1.direct_cost, 806.26, places=2)  # preview changed nothing

			applied = apply_price_refresh(doc.name)
			_, lv1 = self.lv1()
			self.assertAlmostEqual(lv1.direct_cost, change["after"], places=2)
			self.assertAlmostEqual(
				applied["total_after"] - applied["total_before"], change["after"] - 806.26, places=2
			)
		finally:
			frappe.db.set_value("Catalog Item", "P-AIR-001", "net_cost_chf", original)
			apply_price_refresh(self.tender.name)

	def test_product_change_takes_a_new_snapshot(self):
		doc, lv1 = self.lv1()
		update_item(doc.name, lv1.name, matched_product="P-AIR-002")
		row = frappe.get_doc("Tender Item", lv1.name)
		self.assertEqual(row.net_unit_cost, 86.24)
		self.assertEqual(row.status, "calculated")
		update_item(doc.name, lv1.name, matched_product="P-AIR-001")
		self.assertAlmostEqual(frappe.get_doc("Tender Item", lv1.name).direct_cost, 806.26, places=2)


class TestElectricalTrade(IntegrationTestCase):
	"""Gate 4: a second trade is processed and priced with data only."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		seed()
		# No trade given: it is recognised from the PDF's LV page headers.
		cls.tender = frappe.get_doc({"doctype": "Tender", "project_name": "Electrical sample"}).insert()
		cls.tender.db_set("tender_file", _attach(cls.tender.name, ELECTRICAL_PDF))
		process_tender_pdf(cls.tender.name)

	def items(self):
		return frappe.get_doc("Tender", self.tender.name).items

	def test_trade_recognised_from_the_pdf(self):
		self.assertEqual(frappe.db.get_value("Tender", self.tender.name, "trade"), "Electrical")
		trades = [trade_config(code) for code in ("HVAC", "Electrical")]
		self.assertEqual(detect_trade(STARTER_PDF, trades)[0], "HVAC")
		self.assertEqual(detect_trade(ELECTRICAL_PDF, trades)[0], "Electrical")

	def test_cables_matched_by_cores_and_cross_section(self):
		by_qty = {i.quantity: i for i in self.items() if i.family == "el_cable"}
		self.assertEqual(by_qty[240].matched_product, "E-CAB-315")
		self.assertEqual(by_qty[95].matched_product, "E-CAB-525")
		self.assertEqual(by_qty[20].status, "review_required")  # 5x10 mm² is not in the catalogue
		self.assertGreater(by_qty[95].direct_cost, 0)

	def test_custom_attributes_stored_as_printed(self):
		cable = next(i for i in self.items() if i.quantity == 95)
		self.assertEqual(json.loads(cable.custom_attributes)["Querschnitt"], "5x2.5 mm²")

	def test_supplier_package_and_unknown_family(self):
		items = self.items()
		self.assertEqual(
			next(i for i in items if i.matched_product == "E-DB-24").status, "supplier_quote_required"
		)
		emergency = next(i for i in items if i.family == "el_emergency_light")
		self.assertEqual(emergency.reason_code, "no_catalog_item")
		self.assertEqual(emergency.direct_cost, 0)

	def test_export_uses_family_labels_from_master_data(self):
		export_tender(self.tender.name, lang="de-CH", format="csv")
		self.assertIn("Notleuchte", frappe.local.response.filecontent)
		header = frappe.local.response.filecontent.splitlines()[2].split(";")
		self.assertIn("Querschnitt", header)  # project column, label as printed
		self.assertIn("Schutzart", header)


class TestUploadValidation(IntegrationTestCase):
	def test_non_pdf_is_rejected(self):
		"""Frappe already refuses a broken *.pdf; our check also catches any other file type."""
		tender = frappe.get_doc(
			{"doctype": "Tender", "project_name": "Upload test", "trade": "HVAC"}
		).insert()
		file = frappe.get_doc(
			{"doctype": "File", "file_name": "renamed-text.txt", "is_private": 1, "content": b"not a pdf"}
		).insert()
		tender.tender_file = file.file_url
		with self.assertRaises(frappe.ValidationError):
			tender.save()
