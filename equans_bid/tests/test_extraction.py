"""Extraction tests. Pure Python; the LLM mapper is tested with a fake client (no network)."""

import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from equans_bid.extraction import matcher
from equans_bid.extraction.attributes import custom_attributes
from equans_bid.extraction.benchmark import (
	GOLDEN_PAGES,
	assign_golden_ids,
	validate_extraction_against_benchmark,
)
from equans_bid.extraction.llm_mapper import PageMapper, check, schema
from equans_bid.extraction.pipeline import STARTER, extract_positions, prepare_catalog
from equans_bid.extraction.segmenter import page_system
from equans_bid.extraction.verify import verify
from equans_bid.trades import load_trade, read_catalog
from equans_bid.trades.hvac.component_list import parse_page

APP = Path(__file__).resolve().parent.parent
PDF = STARTER / "BKP_244_LV_Lueftung_260804.pdf"
HVAC = load_trade("HVAC")
CATALOG_ROWS = prepare_catalog(read_catalog(HVAC), HVAC)
CATALOG = matcher.index_catalog(CATALOG_ROWS)
FAMILIES = HVAC.family_map


def match(family, attrs, text, unit):
	return matcher.match(family, attrs, text, CATALOG, FAMILIES, unit)


class TestOberglattRegression(unittest.TestCase):
	"""Gate 1: the data-driven pipeline reproduces the pre-refactoring result exactly."""

	@classmethod
	def setUpClass(cls):
		cls.positions = extract_positions(PDF, CATALOG_ROWS, trade=HVAC)
		assign_golden_ids(cls.positions, CATALOG_ROWS)
		cls.baseline = json.loads((APP / "tests" / "fixtures" / "oberglatt_baseline.json").read_text())

	def test_identical_to_baseline(self):
		keys = (
			"source_page",
			"system",
			"quantity",
			"unit",
			"matched_product",
			"status",
			"reason_code",
			"golden_lv_id",
			"reason_args",
		)
		got = {
			p["position_id"]: {k: p[k] for k in keys} | {"kind": p["attributes"]["kind"]}
			for p in self.positions
		}
		want = {r["position_id"]: {k: r[k] for k in (*keys, "kind")} for r in self.baseline}
		self.assertEqual(set(got), set(want))
		diffs = {pid: (want[pid], got[pid]) for pid in want if want[pid] != got[pid]}
		self.assertEqual(diffs, {})

	def test_priced_positions_do_not_drop(self):
		priced = sum(
			p["status"] in ("calculated", "assumption_applied", "supplier_quote_required")
			for p in self.positions
		)
		self.assertGreaterEqual(priced, 214)


class TestBenchmark(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.positions = extract_positions(PDF, CATALOG_ROWS, GOLDEN_PAGES, trade=HVAC)

	def test_22_verified_positions_by_page_quantity_unit(self):
		report = validate_extraction_against_benchmark(self.positions, catalog_rows=CATALOG_ROWS)
		self.assertTrue(report.passed, report.summary())
		self.assertEqual(report.found, 22)

	def test_22_verified_positions_with_product_and_status(self):
		report = validate_extraction_against_benchmark(
			self.positions, catalog_rows=CATALOG_ROWS, require_product=True
		)
		self.assertTrue(
			report.passed, [(r.lv_id, r.outcome, r.detail) for r in report.rows if r.outcome != "OK"]
		)

	def test_a_wrong_quantity_is_a_miss(self):
		broken = [dict(p) for p in self.positions]
		lv1 = next(p for p in broken if p["source_page"] == 78 and p["quantity"] == 5)
		lv1["quantity"] = 4
		report = validate_extraction_against_benchmark(broken, catalog_rows=CATALOG_ROWS)
		self.assertFalse(report.passed)
		self.assertEqual(next(r for r in report.rows if r.lv_id == "LV0001").outcome, "MISS")

	def test_every_position_has_a_status_page_and_evidence(self):
		for p in self.positions:
			self.assertTrue(p["status"] and p["source_page"], p["position_id"])
			self.assertIsInstance(p["custom_attributes"], dict)

	def test_empty_quantity_is_insufficient_information(self):
		p = next(p for p in self.positions if p["description"].startswith("Thermische Aussendämmung 100/15"))
		self.assertIsNone(p["quantity"])
		self.assertEqual(p["status"], "insufficient_information")

	def test_custom_attributes_keep_printed_labels(self):
		lv1 = next(p for p in self.positions if p["source_page"] == 78 and p["quantity"] == 5)
		self.assertEqual(lv1["custom_attributes"]["Grösse"], "Ø 10 cm")
		self.assertEqual(lv1["custom_attributes"]["Fabrikat"], "z.B Trox Hesco")
		lv2 = next(p for p in self.positions if p["source_page"] == 78 and p["quantity"] == 6)
		self.assertEqual(lv2["custom_attributes"]["Grösse"], "Ø 12.5 cm")  # inherited label


class TestMatcher(unittest.TestCase):
	def test_size_guard_wrong_dn_never_auto_accepted(self):
		m = match("exhaust_valve", {"dn_mm": [125]}, "Abluft Tellerventil", "pc")
		self.assertNotEqual(m.confidence, matcher.CONFIDENT)
		self.assertEqual(m.reason_args["detail"]["code"], "dn_mismatch")

	def test_bend_other_angle_is_an_assumption_at_nearest_angle(self):
		m = match("bend", {"dn_mm": [125], "angle": 45}, "Bogen", "pc")
		self.assertEqual(m.product_id, "P-FTG-B-125-30")
		self.assertEqual(m.confidence, matcher.ASSUMED)

	def test_rect_duct_priced_at_size_class(self):
		m = match("duct_rect", {"dims_mm": [300, 200]}, "Luftleitung", "m2")
		self.assertEqual(m.product_id, "P-DCT-X-400x200")  # tie 200x200 / 400x200 -> larger
		self.assertEqual(m.confidence, matcher.ASSUMED)

	def test_family_without_catalogue_item_is_named(self):
		m = match("thermometer", {}, "Zeigerthermometer", "pc")
		self.assertIsNone(m.product_id)
		self.assertEqual((m.reason_code, m.reason_args), ("no_catalog_item", {"family": "thermometer"}))

	def test_unknown_attribute_key_uses_generic_reason(self):
		catalog = [
			{
				"product_id": "X1",
				"kind": "cable",
				"attrs": {"cross_section_mm2": 1.5},
				"unit": "m",
				"description": "cable",
			}
		]
		m = matcher.match("cable", {"cross_section_mm2": 2.5}, "Kabel", catalog, {}, "m")
		self.assertEqual(m.reason_args["detail"]["code"], "attribute_mismatch")


class TestTradeAgnostic(unittest.TestCase):
	"""No product vocabulary in the generic code: it must come from data/trades/."""

	DENY = (
		"lüftung",
		"tellerventil",
		"schalldämpfer",
		"brandschutz",
		"volumenstrom",
		"drosselklappe",
		"wickelfalz",
		"luftleitung",
		"mineralwoll",
		"turnhalle",
		"regenhut",
		"ventilator",
		"silencer",
		"damper",
		"diffuser",
		"duct",
	)

	def test_no_trade_vocabulary_in_generic_code(self):
		offenders = []
		for folder in ("extraction", "pricing"):
			for path in (APP / folder).glob("*.py"):
				text = path.read_text().lower()
				code = re.sub(r'""".*?"""|#.*', "", text, flags=re.S)  # docstrings/comments may give examples
				offenders += [f"{path.name}: {w}" for w in self.DENY if re.search(rf"\b{w}", code)]
		api = re.sub(r'""".*?"""|#.*', "", (APP / "api.py").read_text().lower(), flags=re.S)
		offenders += [f"api.py: {w}" for w in self.DENY if re.search(rf"\b{w}", api)]
		self.assertEqual(offenders, [])

	def test_every_family_has_labels_in_all_locales(self):
		for folder in ("hvac", "electrical"):
			trade = load_trade(folder)
			for f in trade.families:
				self.assertTrue(all(f.labels.get(l) for l in ("de-CH", "fr-CH", "en")), (folder, f.code))


class TestPageSystem(unittest.TestCase):
	def test_footer_wins_when_header_has_wrong_section(self):
		text = (
			"SH Erlenstrasse Oberglatt 244.03 LA03 Küche/Abwaschen Seite 9 / 20\nPos. Gegenstand\n"
			"H:\\Projekt\\08 Baukosten\\02 L\\244.05 LA05 Turnhalle.docx 31.07.2026"
		)
		system, conflict = page_system(text, HVAC.system_header)
		self.assertEqual(system, "244.05 LA05 Turnhalle")
		self.assertEqual(
			conflict, {"header": "244.03 LA03 Küche/Abwaschen", "source": "244.05 LA05 Turnhalle"}
		)

	def test_header_kept_when_consistent(self):
		text = "SH Erlenstrasse Oberglatt 244.04 Schulzimmer OG Seite 1 / 24\nx\nH:\\a\\244.04 LA04 Schulzimmer OG.docx 28.07.2026"
		self.assertEqual(page_system(text, HVAC.system_header), ("244.04 Schulzimmer OG", {}))


class TestHvacTablePlugin(unittest.TestCase):
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
		rows = {p["label"]: p for p in parse_page(76, self.PAGE, "244.01 LA01 Nebenräume")}
		self.assertAlmostEqual(rows["Wickelfalzrohr DN100"]["quantity"], 33.86)
		self.assertAlmostEqual(rows["Wickelfalzrohr DN100 (Einlage)"]["quantity"], 12.54)
		# Lengths of the same size are summed; area = perimeter x length.
		self.assertAlmostEqual(rows["Luftleitung 150 x 500 mm"]["quantity"], round(2 * 0.65 * 4.162, 3))
		self.assertEqual(rows["Bogen DN100 90°"]["quantity"], 8)
		self.assertEqual(rows["Abzweigstück"]["quantity"], 3)
		self.assertTrue(all(p["source_page"] == 76 and p["source_kind"] == "table" for p in rows.values()))


class TestCustomAttributes(unittest.TestCase):
	def test_labels_from_trade_data(self):
		context = ["Zuluft - Tellerventil", "aus Kunststoff", "Fabrikat z.B Trox Hesco", "Typ z.B Z-LVS"]
		attrs, key = custom_attributes(context, "Grösse Ø 10 cm", HVAC)
		self.assertEqual(attrs, {"Fabrikat": "z.B Trox Hesco", "Typ": "z.B Z-LVS", "Grösse": "Ø 10 cm"})
		self.assertEqual(key, "Grösse")
		attrs, _ = custom_attributes(context, "Ø 12.5 cm", HVAC, inherited_key=key)
		self.assertEqual(attrs["Grösse"], "Ø 12.5 cm")


class FakeClient:
	def __init__(self, payload=None, error=None):
		self.payload, self.error, self.calls = payload, error, 0
		self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

	def create(self, **kwargs):
		self.calls += 1
		assert kwargs["response_format"]["type"] == "json_schema"
		assert kwargs["temperature"] == 0
		if self.error:
			raise self.error
		return SimpleNamespace(
			choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))]
		)


BLOCK = {
	"block_text": "Zuluft - Tellerventil\naus Kunststoff\nFabrikat z.B Trox Hesco\nGrösse Ø 10 cm",
	"source_page": 78,
	"quantity": 5.0,
	"unit": "pc",
}
CONTRACT = {
	"position_ref": None,
	"description": "Zuluft - Tellerventil",
	"quantity": 5,
	"unit": "pc",
	"source_page": 78,
	"family_hint": "supply_valve",
	"custom_attributes": [
		{"label": "Fabrikat", "value": "z.B Trox Hesco"},
		{"label": "Grösse", "value": "Ø 10 cm"},
	],
}


LV_PAGE = 78
LV1_TEXT = "Zuluft - Tellerventil"


def rules_positions(pages=(LV_PAGE,)):
	return extract_positions(PDF, CATALOG_ROWS, list(pages), None, HVAC)


def fake_mapper(answer_for):
	"""A mapper that answers through `answer_for(position, offered)` and the real checks."""

	def mapper(page, page_text, positions, catalog):
		offered = PageMapper.page_items(positions, catalog)
		return [check(answer_for(p, offered), p, page_text, offered, set(FAMILIES)) for p in positions]

	return mapper


def answer(position, product_id, fit="exact", **extra):
	return {
		"index": 0,
		"last_line": [line for line in position["block_text"].splitlines() if line.strip()][-1],
		"quantity": position["quantity"],
		"unit": position["unit"],
		"family": "other",
		"product_id": product_id,
		"fit": fit,
		"note": "test",
		"custom_attributes": [],
		**extra,
	}


class TestPageMapper(unittest.TestCase):
	def mapper(self, client):
		m = PageMapper(sorted(FAMILIES), tempfile.mkdtemp(), {"api_key": "test", "model": "test-model"})
		m._client = client
		return m

	def position(self):
		return {**BLOCK, "kind": "supply_valve", "attrs": {"dn_mm": [100]}}

	def test_schema_enums_come_from_master_data_and_the_shortlist(self):
		props = schema(sorted(FAMILIES), ["P-AIR-001"])["schema"]["properties"]["positions"]["items"]
		self.assertEqual(set(props["properties"]["family"]["enum"]), set(FAMILIES) | {"other"})
		self.assertEqual(props["properties"]["product_id"]["enum"], ["P-AIR-001", None])

	def test_shortlist_same_unit_and_family_first(self):
		offered = PageMapper.shortlist(self.position(), CATALOG)
		self.assertTrue(all(c["unit"] == "pc" for c in offered))
		self.assertEqual(offered[0]["kind"], "supply_valve")

	def test_cached_after_first_call(self):
		client = FakeClient({"positions": [answer(BLOCK, "P-AIR-001")]})
		m = self.mapper(client)
		first = m(LV_PAGE, "Grösse Ø 10 cm Stk 5", [self.position()], CATALOG)
		second = m(LV_PAGE, "Grösse Ø 10 cm Stk 5", [self.position()], CATALOG)
		self.assertEqual(first[0].product_id, "P-AIR-001")
		self.assertEqual(first, second)
		self.assertEqual((client.calls, m.cache_hits), (1, 1))

	def test_api_failure_is_reported_not_cached(self):
		client = FakeClient(error=TimeoutError("read timeout"))
		m = self.mapper(client)
		result = m(LV_PAGE, "Stk 5", [self.position()], CATALOG)
		self.assertEqual(result[0].failures, ["llm_error"])
		self.assertIn("TimeoutError", m.last_error)
		m(LV_PAGE, "Stk 5", [self.position()], CATALOG)
		self.assertEqual(client.calls, 2)  # retried, not served from cache

	def test_checks_reject_invented_or_wrong_answers(self):
		pos, page = self.position(), "Grösse Ø 10 cm Stk 5"
		offered = PageMapper.shortlist(pos, CATALOG)
		self.assertIn(
			"quantity_not_on_page",
			check(answer(pos, None, quantity=7), pos, page, offered, set(FAMILIES)).failures,
		)
		wrong_dn = check(answer(pos, "P-AIR-002"), pos, page, offered, set(FAMILIES))  # DN125 item
		self.assertIsNone(wrong_dn.product_id)
		self.assertIn("product_attributes_disagree", wrong_dn.failures)
		not_offered = check(answer(pos, "P-NOPE"), pos, page, offered, set(FAMILIES))
		self.assertEqual(not_offered.failures, ["product_not_offered"])
		self.assertEqual(
			check(answer(pos, "P-AIR-001"), pos, page, offered, set(FAMILIES)).product_id, "P-AIR-001"
		)


class TestLlmInPipeline(unittest.TestCase):
	"""Rules + LLM: agreement confirms, disagreement goes to a human, the PDF quantity is priced."""

	@classmethod
	def setUpClass(cls):
		cls.rules = {p["position_id"]: p for p in rules_positions()}
		cls.rules_by_text = {p["description_original"]: p for p in cls.rules.values()}

	def run_with(self, answer_for):
		return {
			p["position_id"]: p
			for p in extract_positions(PDF, CATALOG_ROWS, [LV_PAGE], fake_mapper(answer_for), HVAC)
		}

	def lv1(self, positions):
		return next(p for p in positions.values() if p["quantity"] == 5 and LV1_TEXT in p["description"])

	def test_agreement_is_confirmed(self):
		out = self.run_with(
			lambda p, offered: answer(p, self.rules_by_text[p["block_text"]]["matched_product"])
		)
		lv1 = self.lv1(out)
		self.assertEqual(lv1["matched_product"], "P-AIR-001")
		self.assertEqual(lv1["status"], "calculated")
		self.assertEqual(lv1["attributes"]["matched_by"], "llm+rules")

	def test_certain_rules_match_is_not_overruled(self):
		# The DN100 exhaust valve is another kind of product than the supply valve matched exactly.
		out = self.run_with(
			lambda p, offered: answer(p, "P-AIR-003" if LV1_TEXT in p["block_text"] else None)
		)
		lv1 = self.lv1(out)
		self.assertEqual((lv1["matched_product"], lv1["status"]), ("P-AIR-001", "calculated"))
		self.assertEqual(lv1["attributes"]["llm"]["product_id"], "P-AIR-003")  # visible in review

	def llm_only(self, family_known: bool):
		"""Run with the LLM mapping one position the rules could not map to a catalogue item."""
		target = next(
			p
			for p in self.rules.values()
			if p["attributes"]["source_kind"] == "lv"
			and not p["matched_product"]
			and bool(p["attributes"]["kind"]) == family_known
		)
		pick = "P-CTL-002"  # temperature sensor: a family the rules did not recognise here
		out = self.run_with(
			lambda p, o: answer(p, pick if p["block_text"] == target["description_original"] else None)
		)
		return out[target["position_id"]], pick

	def test_llm_finds_what_the_rules_missed(self):
		found, pick = self.llm_only(family_known=False)
		self.assertEqual(found["matched_product"], pick)
		self.assertEqual(found["reason_code"], "llm_classified")
		self.assertEqual(found["family"], "temp_sensor")
		self.assertEqual(found["status"], "assumption_applied")  # priced provisionally, confirm in review
		self.assertEqual(found["attributes"]["matched_by"], "llm")

	def test_llm_item_of_another_family_is_only_proposed(self):
		# The rules recognised the family (e.g. rain hat) but the catalogue has none: an item of
		# another family is a proposal for review, never priced automatically.
		found, pick = self.llm_only(family_known=True)
		self.assertEqual(found["matched_product"], pick)
		self.assertEqual(found["status"], "review_required")

	def test_answer_for_another_position_is_dropped(self):
		out = self.run_with(lambda p, o: answer(p, "P-AIR-003", last_line="Grösse Ø 99 cm"))
		lv1 = self.lv1(out)
		self.assertEqual(lv1["attributes"]["llm"]["failures"], ["position_mismatch"])
		self.assertEqual((lv1["matched_product"], lv1["status"]), ("P-AIR-001", "calculated"))

	def test_quantity_conflict_goes_to_review_and_pdf_quantity_stays(self):
		out = self.run_with(lambda p, o: answer(p, None, quantity=6) if LV1_TEXT in p["block_text"] else None)
		lv1 = next(p for p in out.values() if p["position_id"] == self.lv1(self.rules)["position_id"])
		self.assertEqual(lv1["quantity"], 5)
		# 6 is printed on the page too (the DN125 variant), so it is a conflict, not an invention.
		self.assertEqual(lv1["reason_code"], "llm_conflict")
		self.assertEqual(lv1["status"], "review_required")

	def test_llm_failure_keeps_the_rules_result(self):
		out = self.run_with(lambda p, o: None)
		for pid, p in out.items():
			self.assertEqual(
				(p["matched_product"], p["status"]),
				(self.rules[pid]["matched_product"], self.rules[pid]["status"]),
			)


class TestVerify(unittest.TestCase):
	PAGE = "Zuluft - Tellerventil Grösse Ø 10 cm Stk 5"

	def test_verified_contract_is_used(self):
		v = verify(CONTRACT, BLOCK, self.PAGE, set(FAMILIES))
		self.assertEqual(v.failures, [])
		self.assertEqual(v.family_hint, "supply_valve")
		self.assertEqual(v.custom_attributes, {"Fabrikat": "z.B Trox Hesco", "Grösse": "Ø 10 cm"})

	def test_invented_values_are_rejected(self):
		bad = {
			**CONTRACT,
			"quantity": 7,
			"source_page": 12,
			"family_hint": "made_up",
			"custom_attributes": [{"label": "Preis", "value": "CHF 99"}],
		}
		v = verify(bad, BLOCK, self.PAGE, set(FAMILIES))
		self.assertEqual(
			set(v.failures),
			{"quantity_not_on_page", "page_mismatch", "family_unknown_code", "attribute_not_in_block"},
		)
		self.assertIsNone(v.family_hint)
		self.assertEqual(v.custom_attributes, {})

	def test_different_quantity_on_page_is_a_conflict(self):
		v = verify({**CONTRACT, "quantity": 6}, BLOCK, self.PAGE + " Stk 6", set(FAMILIES))
		self.assertEqual(v.conflicts, {"quantity": 6})


if __name__ == "__main__":
	unittest.main()
