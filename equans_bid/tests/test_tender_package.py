"""The synthetic tender-package generator: format of the starter package, and consistency with
the app (the generated golden rows are found and priced by the real pipeline)."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from equans_bid.extraction.benchmark import validate_extraction_against_benchmark
from equans_bid.extraction.pipeline import STARTER, extract_positions, prepare_catalog
from equans_bid.tools.tender_package import generate
from equans_bid.trades import load_trade, read_catalog

SCENARIO = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "talacker_hvac.json"
FILES = {
	"catalog.csv",
	"productivity.csv",
	"project_parameters.json",
	"example_lv_positions.csv",
	"expected_output_example.json",
	"README.md",
	"manifest.json",
	"scenario.json",
}


class TestTenderPackage(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.out = Path(tempfile.mkdtemp())
		cls.manifest = generate(SCENARIO, cls.out)
		cls.pdf = cls.out / json.loads(SCENARIO.read_text())["project"]["pdf_name"]
		trade = load_trade("HVAC")
		cls.catalog = prepare_catalog(read_catalog(trade), trade)
		cls.positions = extract_positions(cls.pdf, cls.catalog, trade=trade)

	def test_all_files_of_a_starter_package(self):
		self.assertEqual({p.name for p in self.out.iterdir()}, FILES | {self.pdf.name})
		self.assertTrue(self.pdf.read_bytes().startswith(b"%PDF-"))
		self.assertTrue(self.manifest["synthetic"])

	def test_same_schema_as_the_equans_starter_files(self):
		with (
			open(STARTER / "example_lv_positions.csv") as a,
			open(self.out / "example_lv_positions.csv") as b,
		):
			self.assertEqual(next(csv.reader(a)), next(csv.reader(b)))
		starter = json.loads((STARTER / "expected_output_example.json").read_text())
		generated = json.loads((self.out / "expected_output_example.json").read_text())
		self.assertEqual(set(starter), set(generated))
		self.assertEqual(set(starter["position_results"][0]), set(generated["position_results"][0]))
		self.assertEqual(
			set(starter["recommended_bid_range"]["scenarios"][0]),
			set(generated["recommended_bid_range"]["scenarios"][0]),
		)
		params = json.loads((self.out / "project_parameters.json").read_text())
		self.assertEqual(params["project"]["source_tender_file"], self.pdf.name)

	def test_golden_rows_found_and_priced_by_the_app(self):
		report = validate_extraction_against_benchmark(
			self.positions, self.out / "example_lv_positions.csv", self.catalog, require_product=True
		)
		self.assertTrue(
			report.passed, [(r.lv_id, r.outcome, r.detail) for r in report.rows if r.outcome != "OK"]
		)
		self.assertEqual(report.found, self.manifest["golden_positions"])

	def test_page_numbers_come_from_the_layout(self):
		golden = list(csv.DictReader(open(self.out / "example_lv_positions.csv")))
		pages = {int(g["source_page"]) for g in golden}
		self.assertLessEqual(max(pages), self.manifest["pages"])
		self.assertGreater(len(pages), 1)

	def test_regeneration_is_reproducible(self):
		again = Path(tempfile.mkdtemp())
		second = generate(SCENARIO, again)
		for name, digest in self.manifest["files"].items():
			if not name.endswith(".pdf"):  # PDF metadata carries a creation time
				self.assertEqual(second["files"][name], digest, name)
