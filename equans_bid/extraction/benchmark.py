"""Extraction benchmark against the verified positions (example_lv_positions.csv).

The tender prints no LV IDs (LV0001… exist only in the CSV), so a golden row is found by what
the PDF does print: page, unit and quantity. When several positions on a page share those,
the row's expected install code (via the family's catalogue items) and the sizes in its
description decide; `require_product` additionally checks the matched catalogue product and the
status, testing extraction and matching together.

	cd apps/equans_bid && ../../env/bin/python -m equans_bid.extraction.benchmark [--all] [--strict] [-v]
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from equans_bid.extraction.matcher import _agrees

STARTER = Path(__file__).resolve().parent.parent / "data" / "starter"
GOLDEN_CSV = STARTER / "example_lv_positions.csv"
GOLDEN_PAGES = [78, 79, 80, 106, 107, 163, 164, 169, 170, 171]
QTY_TOLERANCE = 0.001


@dataclass
class RowResult:
	lv_id: str
	outcome: str  # OK, MISS, AMBIGUOUS, WRONG_PRODUCT, WRONG_STATUS
	position_id: str | None = None
	detail: str = ""


@dataclass
class BenchmarkReport:
	rows: list[RowResult] = field(default_factory=list)
	extra_positions: int = 0

	@property
	def found(self) -> int:
		return sum(r.outcome == "OK" for r in self.rows)

	@property
	def passed(self) -> bool:
		return bool(self.rows) and self.found == len(self.rows)

	def summary(self) -> str:
		counts = Counter(r.outcome for r in self.rows)
		detail = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
		return f"{self.found}/{len(self.rows)} verified positions ({detail})"


def read_golden(path: Path = GOLDEN_CSV) -> list[dict]:
	with open(path, newline="") as fh:
		return list(csv.DictReader(fh))


def _description_attributes(text: str) -> dict:
	"""Sizes stated in a golden description: DN and W x H [x L] mm."""
	attrs = {}
	m = re.search(r"DN(\d+)", text)
	if m:
		attrs["dn_mm"] = int(m.group(1))
	m = re.search(r"(\d+)x(\d+)(?:x(\d+))?\s*mm", text)
	if m:
		attrs["dims_mm"] = [int(g) for g in m.groups() if g]
	return attrs


def family_install_codes(catalog_rows: list[dict]) -> dict[str, set]:
	codes = defaultdict(set)
	for r in catalog_rows:
		if r.get("family"):
			codes[r["family"]].add(r.get("install_code"))
	return codes


def validate_extraction_against_benchmark(
	positions: list[dict],
	golden_csv: Path = GOLDEN_CSV,
	catalog_rows: list[dict] | None = None,
	require_product: bool = False,
) -> BenchmarkReport:
	"""Compare extracted positions with the verified rows; the report passes only at all-OK.

	`positions`: pipeline output (source_page, unit, quantity, family, attributes, matched_product,
	status). `catalog_rows` (with `family`) lets the expected install code break ties.
	"""
	install = family_install_codes(catalog_rows or [])
	report = BenchmarkReport()
	used: set[str] = set()
	for g in read_golden(golden_csv):
		page, qty, unit = int(g["source_page"]), float(g["quantity"]), g["unit"]
		cands = [
			p
			for p in positions
			if p["source_page"] == page
			and p["unit"] == unit
			and p["quantity"] is not None
			and abs(p["quantity"] - qty) <= QTY_TOLERANCE
		]
		if len(cands) > 1 and install:
			by_code = [p for p in cands if g["expected_install_code"] in install.get(p.get("family"), set())]
			cands = by_code or cands
		if len(cands) > 1:
			want = _description_attributes(g["description"])
			by_size = [
				p
				for p in cands
				if want and all(_agrees(k, (p.get("attributes") or {}).get(k), v) for k, v in want.items())
			]
			cands = by_size or cands
		if not cands:
			report.rows.append(
				RowResult(g["lv_id"], "MISS", detail=f"no position on page {page} with {qty:g} {unit}")
			)
			continue
		if len(cands) > 1:
			ids = ", ".join(p["position_id"] for p in cands)
			report.rows.append(RowResult(g["lv_id"], "AMBIGUOUS", detail=f"candidates {ids}"))
			continue
		p = cands[0]
		used.add(p["position_id"])
		if require_product and p.get("matched_product") != g["suggested_product_id"]:
			detail = f"{p.get('matched_product')} != {g['suggested_product_id']}"
			report.rows.append(RowResult(g["lv_id"], "WRONG_PRODUCT", p["position_id"], detail))
		elif require_product and p.get("status") != g["ground_truth_status"]:
			detail = f"{p.get('status')} != {g['ground_truth_status']}"
			report.rows.append(RowResult(g["lv_id"], "WRONG_STATUS", p["position_id"], detail))
		else:
			report.rows.append(RowResult(g["lv_id"], "OK", p["position_id"]))
	report.extra_positions = sum(1 for p in positions if p["position_id"] not in used)
	return report


def assign_golden_ids(
	positions: list[dict], catalog_rows: list[dict] | None = None, golden_csv: Path = GOLDEN_CSV
) -> int:
	"""Write the golden lv_id onto the positions the benchmark identifies (UI badge, tests)."""
	report = validate_extraction_against_benchmark(positions, golden_csv, catalog_rows)
	by_id = {p["position_id"]: p for p in positions}
	for r in report.rows:
		if r.outcome == "OK":
			by_id[r.position_id]["golden_lv_id"] = r.lv_id
	return report.found


def main():
	from equans_bid.extraction.pipeline import extract_positions, prepare_catalog
	from equans_bid.extraction.structurer import get_structurer
	from equans_bid.trades import load_trade, read_catalog

	trade = load_trade("HVAC")
	catalog = prepare_catalog(read_catalog(trade), trade)
	structurer = None
	if "--llm" in sys.argv:
		structurer = get_structurer([f.code for f in trade.families], STARTER.parent / "llm_cache")
	pages = None if "--all" in sys.argv else GOLDEN_PAGES
	pdf = STARTER / "BKP_244_LV_Lueftung_260804.pdf"
	positions = extract_positions(pdf, catalog, pages, structurer, trade)
	report = validate_extraction_against_benchmark(
		positions, catalog_rows=catalog, require_product="--strict" in sys.argv
	)
	for r in report.rows:
		print(f"{r.outcome:<13} {r.lv_id} {r.position_id or '':<8} {r.detail}")
	print(f"\n{report.summary()} · {len(positions)} positions, {report.extra_positions} not in the benchmark")
	if structurer:
		print(structurer.stats())
	if "-v" in sys.argv:
		for p in positions:
			print(
				p["position_id"],
				p["quantity"],
				p["unit"],
				p["family"],
				p["matched_product"],
				p["status"],
				"|",
				p["description"][:70],
				"|",
				p["custom_attributes"],
			)
	sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
	main()
