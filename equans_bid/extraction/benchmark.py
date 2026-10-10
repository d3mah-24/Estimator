"""Extraction benchmark against the 22 verified positions.

cd apps/equans_bid && ../../env/bin/python -m equans_bid.extraction.benchmark [--all] [--llm] [-v]
"""

import csv
import sys
from collections import Counter

from equans_bid.extraction.llm import get_enricher
from equans_bid.extraction.pipeline import STARTER, extract_positions

GOLDEN_PAGES = [78, 79, 80, 106, 107, 163, 164, 169, 170, 171]


def catalog_rows():
	with open(STARTER / "catalog.csv", newline="") as fh:
		rows = list(csv.DictReader(fh))
	for r in rows:
		r["supplier_quote_required"] = r["supplier_quote_required"].lower() == "true"
	return rows


def main(all_pages=False):
	with open(STARTER / "example_lv_positions.csv", newline="") as fh:
		golden = list(csv.DictReader(fh))
	enrich = get_enricher(STARTER.parent / "llm_cache") if "--llm" in sys.argv else None
	positions = extract_positions(
		STARTER / "BKP_244_LV_Lueftung_260804.pdf",
		catalog_rows(),
		None if all_pages else GOLDEN_PAGES,
		enrich=enrich,
	)
	found = {p["golden_lv_id"]: p for p in positions if p["golden_lv_id"]}
	hits = 0
	for g in golden:
		p = found.get(g["lv_id"])
		ok = p is not None and p["status"] == g["ground_truth_status"]
		hits += ok
		print(
			f"{'OK ' if ok else 'MISS'} {g['lv_id']} p{g['source_page']} {g['quantity']} {g['unit']} {g['suggested_product_id']}"
			+ (f" -> {p['status']}" if p else "")
		)
	print(f"\nGolden recall: {hits}/{len(golden)}")
	print(f"Positions extracted: {len(positions)}")
	if enrich:
		print("LLM:", enrich.stats())
	print("By status:", dict(Counter(p["status"] for p in positions)))
	if "-v" in sys.argv:
		for p in positions:
			print(
				p["position_id"],
				p["quantity"],
				p["unit"],
				p["attributes"].get("kind"),
				p["matched_product"],
				p["status"],
				"|",
				p["description"][:70],
				"|",
				p["status_reason"],
			)


if __name__ == "__main__":
	main(all_pages="--all" in sys.argv)
