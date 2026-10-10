"""Extraction tests. Pure Python; the GPT-4o adapter is tested with a fake client (no network)."""

import json
import tempfile
import unittest
from types import SimpleNamespace
from typing import ClassVar

from equans_bid.extraction import matcher
from equans_bid.extraction.benchmark import GOLDEN_PAGES, catalog_rows
from equans_bid.extraction.componentlist import parse_component_page
from equans_bid.extraction.llm import GPT4oClassifier
from equans_bid.extraction.pipeline import STARTER, extract_positions, load_golden
from equans_bid.extraction.segmenter import page_system

PDF = STARTER / "BKP_244_LV_Lueftung_260804.pdf"
CATALOG = matcher.index_catalog(catalog_rows())


class TestGoldenExtraction(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.positions = extract_positions(PDF, catalog_rows(), GOLDEN_PAGES)

	def test_all_22_verified_positions_found(self):
		found = {p["golden_lv_id"]: p for p in self.positions if p["golden_lv_id"]}
		golden = load_golden()
		self.assertEqual(len(found), len(golden))
		for (page, product, qty), lv_id in golden.items():
			with self.subTest(lv_id=lv_id):
				p = found[lv_id]
				self.assertEqual(
					(p["source_page"], p["matched_product"], p["quantity"]), (page, product, qty)
				)

	def test_every_position_has_a_status_and_page(self):
		for p in self.positions:
			self.assertTrue(p["status"], p["position_id"])
			self.assertTrue(p["source_page"], p["position_id"])

	def test_empty_quantity_is_insufficient_information(self):
		p = next(p for p in self.positions if p["description"].startswith("Thermische Aussendämmung 100/15"))
		self.assertIsNone(p["quantity"])
		self.assertEqual(p["status"], "insufficient_information")


class TestMatcher(unittest.TestCase):
	def test_wrong_dn_is_never_auto_accepted(self):
		m = matcher.match("exhaust_valve", {"dn_mm": [125]}, "Abluft Tellerventil", CATALOG, "pc")
		self.assertLess(m.confidence, matcher.CONFIDENT)

	def test_bend_other_angle_is_an_assumption_at_nearest_angle(self):
		m = matcher.match("bend", {"dn_mm": [125], "angle": 45}, "Bogen", CATALOG, "pc")
		self.assertEqual(m.product_id, "P-FTG-B-125-30")
		self.assertEqual(m.confidence, matcher.ASSUMED)

	def test_rect_duct_priced_at_size_class(self):
		m = matcher.match("duct_rect", {"dims_mm": [300, 200]}, "Luftleitung", CATALOG, "m2")
		self.assertEqual(m.product_id, "P-DCT-X-400x200")  # tie 200x200 / 400x200 -> larger
		self.assertEqual(m.confidence, matcher.ASSUMED)

	def test_family_without_catalogue_item_is_named(self):
		m = matcher.match("thermometer", {}, "Zeigerthermometer", CATALOG, "pc")
		self.assertIsNone(m.product_id)
		self.assertIn("dial thermometer", m.reason)


class TestPageSystem(unittest.TestCase):
	def test_footer_wins_when_header_has_wrong_section(self):
		text = (
			"SH Erlenstrasse Oberglatt 244.03 LA03 Küche/Abwaschen Seite 9 / 20\nPos. Gegenstand\n"
			"H:\\Projekt\\08 Baukosten\\02 L\\244.05 LA05 Turnhalle.docx 31.07.2026"
		)
		system, conflict = page_system(text)
		self.assertEqual(system, "244.05 LA05 Turnhalle")
		self.assertIn("244.03", conflict)

	def test_header_kept_when_consistent(self):
		text = "SH Erlenstrasse Oberglatt 244.04 Schulzimmer OG Seite 1 / 24\nx\nH:\\a\\244.04 LA04 Schulzimmer OG.docx 28.07.2026"
		self.assertEqual(page_system(text), ("244.04 Schulzimmer OG", ""))


class TestComponentList(unittest.TestCase):
	PAGE = "\n".join(
		[
			"Bauteilliste Lüftung",
			"Auflistung der Rohre",
			"33860R-R Wickelfalzrohr 100",
			"12540R-R Wickelfalzrohr 100Einlage",
			"Auflistung der Kanäle",
			"3938L Luftleitung 150 500",
			"224LT Luftleitungsteil 150 500",
			"Auflistung der Formstücke rund",
			"8BGE Bogen 100 90",
			"3ATE Abzweigstück 90° 100 100 100 90",
		]
	)

	def test_parse(self):
		rows = {p["label"]: p for p in parse_component_page(76, self.PAGE, "244.01 LA01 Nebenräume")}
		self.assertAlmostEqual(rows["Wickelfalzrohr DN100"]["quantity"], 33.86)
		self.assertAlmostEqual(rows["Wickelfalzrohr DN100 (Einlage)"]["quantity"], 12.54)
		# Lengths of the same size are summed; area = perimeter x length.
		self.assertAlmostEqual(rows["Luftleitung 150 x 500 mm"]["quantity"], round(2 * 0.65 * 4.162, 3))
		self.assertEqual(rows["Bogen DN100 90°"]["quantity"], 8)
		self.assertEqual(rows["Abzweigstück"]["quantity"], 3)
		self.assertTrue(all(p["source_page"] == 76 for p in rows.values()))


class FakeClient:
	def __init__(self, payload=None, error=None):
		self.payload, self.error, self.calls = payload, error, 0
		self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

	def create(self, **kwargs):
		self.calls += 1
		assert kwargs["response_format"]["type"] == "json_schema"
		if self.error:
			raise self.error
		return SimpleNamespace(
			choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))]
		)


class TestGPT4oClassifier(unittest.TestCase):
	POSITION: ClassVar[dict] = {
		"title": "Regenhut",
		"description_original": "Regenhut\nMaterial V2A",
		"label": "B x H 110 x 35 cm",
	}
	ANSWER: ClassVar[dict] = {
		"kind": "rain_hat",
		"description_en": "Stainless steel rain hat",
		"attributes": {
			"dn_mm": None,
			"width_mm": 1100,
			"height_mm": 350,
			"length_mm": None,
			"thickness_mm": None,
			"angle": None,
			"weatherproof": None,
		},
	}

	def classifier(self, client):
		c = GPT4oClassifier(tempfile.mkdtemp(), api_key="test")
		c._client = client
		return c

	def test_result_is_validated_and_cached(self):
		client = FakeClient(self.ANSWER)
		c = self.classifier(client)
		first = c(self.POSITION)
		second = c(self.POSITION)
		self.assertEqual(first, second)
		self.assertEqual(first["kind"], "rain_hat")
		self.assertEqual(first["attributes"], {"dims_mm": [1100, 350]})
		self.assertEqual(client.calls, 1)

	def test_unknown_kind_is_rejected(self):
		c = self.classifier(FakeClient({**self.ANSWER, "kind": "price_is_42"}))
		self.assertIsNone(c(self.POSITION)["kind"])

	def test_api_failure_is_reported_not_raised(self):
		c = self.classifier(FakeClient(error=TimeoutError("read timeout")))
		result = c(self.POSITION)
		self.assertIsNone(result["kind"])
		self.assertIn("TimeoutError", result["error"])
		self.assertEqual(c.errors, 1)

	def test_pipeline_uses_llm_only_for_unrecognised(self):
		seen = []

		def enrich(position):
			seen.append(position["title"])
			return {"kind": None}

		extract_positions(PDF, catalog_rows(), [78], enrich=enrich)
		self.assertNotIn("Zuluft - Tellerventil", seen)  # recognised by rules
		self.assertNotIn("Regenhut", seen)  # recognised by rules
		self.assertIn("Sockelrohr V2A", seen)  # unrecognised -> LLM fallback


if __name__ == "__main__":
	unittest.main()
