"""End to end in Frappe: PDF -> Tender Items -> price -> estimator edit -> reprice."""

import frappe
from frappe.tests import IntegrationTestCase

from equans_bid.api import process_tender_pdf, update_item
from equans_bid.commands.seed_data import run as seed


class TestTenderEndToEnd(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		seed()
		cls.tender = frappe.get_doc({"doctype": "Tender", "project_name": "E2E test tender"}).insert()
		process_tender_pdf(cls.tender.name, pages=[78, 79, 80])

	def item(self, lv_id):
		doc = frappe.get_doc("Tender", self.tender.name)
		return doc, next(i for i in doc.items if i.golden_lv_id == lv_id)

	def test_lv0001_extracted_and_priced(self):
		_, lv1 = self.item("LV0001")
		self.assertEqual(lv1.source_page, 78)
		self.assertEqual(lv1.quantity, 5)
		self.assertEqual(lv1.unit, "pc")
		self.assertEqual(lv1.matched_product, "P-AIR-001")
		self.assertEqual(lv1.status, "calculated")
		self.assertAlmostEqual(lv1.direct_cost, 806.26, places=2)

	def test_supplier_quote_override_reprices(self):
		doc, lv6 = self.item("LV0006")
		self.assertEqual(lv6.status, "supplier_quote_required")
		labour_before = lv6.labour_cost
		update_item(doc.name, lv6.name, quote_override=9000)
		_, lv6 = self.item("LV0006")
		self.assertEqual(lv6.material_cost, 9000)
		self.assertEqual(lv6.labour_cost, labour_before)
		self.assertEqual(lv6.price_source, "supplier_quote")

	def test_unrecognised_positions_stay_unpriced(self):
		doc = frappe.get_doc("Tender", self.tender.name)
		for i in doc.items:
			if i.status in ("review_required", "insufficient_information"):
				self.assertEqual(i.direct_cost, 0, i.position_id)
		self.assertGreater(doc.unresolved_count, 0)
