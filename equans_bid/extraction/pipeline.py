"""PDF -> extracted, matched positions with a status. No pricing and no Frappe here.

Statuses follow the starter README. Pricing (calculated vs supplier_quote_required) is decided
from the catalogue flag; anything uncertain is left unpriced for the estimator.
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

from equans_bid.extraction import classify, matcher
from equans_bid.extraction.componentlist import is_component_page, parse_component_page
from equans_bid.extraction.pdf_text import read_pages
from equans_bid.extraction.segmenter import SYSTEM_HEADER, page_system, segment

SAME_AS_ABOVE = re.compile(r"^wie vor(be)?schrieben", re.I)
STARTER = Path(__file__).resolve().parent.parent / "data" / "starter"


def load_golden() -> dict[tuple, str]:
	"""(source_page, product_id, quantity) -> golden lv_id from example_lv_positions.csv."""
	with open(STARTER / "example_lv_positions.csv", newline="") as fh:
		return {
			(int(r["source_page"]), r["suggested_product_id"], float(r["quantity"])): r["lv_id"]
			for r in csv.DictReader(fh)
		}


def extraction_confidence(raw, page_text: str) -> float:
	"""Checks, not model output: quantity present literally, unit allowed, size parsed."""
	score = 0.0
	if raw.quantity_raw and raw.quantity_raw in page_text:
		score += 0.5
	if raw.unit in {"pc", "m", "m2", "h", "LS", "system"}:
		score += 0.3
	if raw.title:
		score += 0.2
	return round(score, 2)


def status_for(position: dict, kind, m: matcher.Match, catalog_by_id: dict) -> tuple[str, str]:
	if position["quantity"] is None:
		return "insufficient_information", "Mengenspalte im LV ist leer"
	if not m.product_id:
		return "review_required", m.reason
	if m.confidence < matcher.CONFIDENT:
		status = "assumption_applied" if m.confidence >= 0.75 else "review_required"
		return status, m.reason
	if catalog_by_id[m.product_id]["supplier_quote_required"]:
		return (
			"supplier_quote_required",
			"Lieferpaket: Katalogpreis ist provisorisch, bis eine Offerte erfasst ist",
		)
	return "calculated", m.reason


def page_systems(pages) -> dict[int, str]:
	"""System of every page. Component-list pages have no LV header; they take the
	system of the LV pages around them (previous, else next)."""
	systems, last = {}, ""
	for p in pages:
		system, _ = page_system(p.text) if not is_component_page(p.text) else ("", "")
		if system and SYSTEM_HEADER.search(p.text.splitlines()[0]):
			last = system
		systems[p.number] = last
	upcoming = ""
	for p in reversed(pages):
		if systems[p.number]:
			upcoming = systems[p.number]
		elif upcoming:
			systems[p.number] = upcoming
	return systems


def extract_positions(
	pdf_path, catalog_rows: list[dict], pages: list[int] | None = None, enrich=None
) -> list[dict]:
	"""`catalog_rows` need product_id, category, subcategory, description, unit, supplier_quote_required.

	`enrich(position) -> {"kind", "attributes", "description_en"} | None` is an optional LLM
	fallback, called only for positions the rules cannot classify.
	"""
	page_objs = read_pages(pdf_path, pages)
	text_by_page = {p.number: p.text for p in page_objs}
	systems = page_systems(page_objs)
	# Only LV pages (with a "244.0x ... Seite n / m" header) hold positions; the general
	# conditions, schedules and plan lists around them do not.
	lv_pages = [p for p in page_objs if p.text.strip() and SYSTEM_HEADER.search(p.text.splitlines()[0])]
	component_pages = [p for p in page_objs if is_component_page(p.text)]

	candidates = []
	for raw in segment(lv_pages, title_picker=classify.pick_title):
		candidates.append(
			{
				"source_page": raw.source_page,
				"system": raw.system,
				"title": raw.title,
				"label": raw.label,
				"description_original": raw.text,
				"quantity_raw": raw.quantity_raw,
				"unit_raw": raw.unit_raw,
				"quantity": raw.quantity,
				"unit": raw.unit,
				"kind": classify.tender_kind(raw.title, "\n".join(raw.context), raw.label),
				"attrs": classify.tender_attributes(raw.label, raw.context),
				"extraction_confidence": extraction_confidence(raw, text_by_page[raw.source_page]),
				"system_conflict": raw.system_conflict,
			}
		)
	for page in component_pages:
		for c in parse_component_page(page.number, page.text, systems[page.number]):
			# Machine-generated table: values are read exactly, so extraction confidence is high.
			candidates.append(
				{**c, "quantity_raw": str(c["quantity"]), "unit_raw": c["unit"], "extraction_confidence": 0.9}
			)
	candidates.sort(key=lambda c: c["source_page"])

	catalog = matcher.index_catalog(catalog_rows)
	catalog_by_id = {c["product_id"]: c for c in catalog}
	golden = load_golden()
	per_page = defaultdict(int)

	out = []
	previous_kind = None
	for c in candidates:
		per_page[c["source_page"]] += 1
		kind, attrs, source, description_en, error = c["kind"], c["attrs"], "rules", None, None
		if kind is None and SAME_AS_ABOVE.match(c["title"]):
			# "wie vorbeschrieben, jedoch ..." repeats the previous position's family.
			kind = previous_kind
		if kind is None and enrich is not None:
			enriched = enrich(c) or {}
			error = enriched.get("error")
			if enriched.get("kind"):
				kind = enriched["kind"]
				attrs = {
					**attrs,
					**{
						k: v for k, v in (enriched.get("attributes") or {}).items() if v not in (None, [], "")
					},
				}
				description_en = enriched.get("description_en")
				source = "llm"
		previous_kind = kind
		m = matcher.match(kind, attrs, f"{c['title']} {c['label']}", catalog, c["unit"])
		status, reason = status_for(c, kind, m, catalog_by_id)
		if source == "llm":
			reason = f"Von LLM klassifiziert als {kind}. {reason}"
		description = re.sub(r"\s+", " ", f"{c['title']} — {c['label']}" if c["label"] else c["title"]).strip(
			" —"
		)
		out.append(
			{
				"position_id": f"P{c['source_page']:03d}-{per_page[c['source_page']]:02d}",
				"golden_lv_id": golden.get((c["source_page"], m.product_id, c["quantity"])),
				"system": c["system"],
				"source_page": c["source_page"],
				"description_original": c["description_original"],
				"description": description_en or description,
				"quantity_raw": c["quantity_raw"],
				"unit_raw": c["unit_raw"],
				"quantity": c["quantity"],
				"unit": c["unit"],
				"attributes": {
					"kind": kind,
					"classified_by": source,
					**attrs,
					**({"system_conflict": c["system_conflict"]} if c.get("system_conflict") else {}),
				},
				"extraction_confidence": c["extraction_confidence"],
				"matched_product": m.product_id,
				"match_confidence": m.confidence,
				"status": status,
				"status_reason": reason,
				"error": error,
			}
		)
	return out
