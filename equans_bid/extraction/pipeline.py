"""PDF -> extracted, matched positions with a status. No pricing and no Frappe here.

Everything trade-specific comes from a `TradeConfig` (equans_bid.trades): page header, family
recognition, attribute rules, table-parser plug-ins. The optional `structurer` (LLM) only adds
verified information (family hint, custom attributes); the rules result stays the reference for
quantity, unit and page.
"""

import re
from collections import defaultdict
from pathlib import Path

from equans_bid.extraction import matcher
from equans_bid.extraction.attributes import catalog_attributes, custom_attributes, tender_attributes
from equans_bid.extraction.families import FamilyClassifier
from equans_bid.extraction.pdf_text import read_pages
from equans_bid.extraction.segmenter import page_system, segment
from equans_bid.extraction.verify import verify
from equans_bid.reasons import reason, render
from equans_bid.trades import TradeConfig, catalog_family, load_trade

SAME_AS_ABOVE = re.compile(r"^wie vor(be)?schrieben", re.I)  # German LV phrasing, any trade
STARTER = Path(__file__).resolve().parent.parent / "data" / "starter"


def extraction_confidence(raw, page_text: str) -> float:
	"""Checks, not model output: quantity present literally, unit allowed, title found."""
	score = 0.0
	if raw.quantity_raw and raw.quantity_raw in page_text:
		score += 0.5
	if raw.unit in {"pc", "m", "m2", "h", "LS", "system"}:
		score += 0.3
	if raw.title:
		score += 0.2
	return round(score, 2)


def status_for(position: dict, m: matcher.Match, catalog_by_id: dict) -> tuple[str, dict]:
	"""(status, reason) where reason is {"code", "args"} (see equans_bid/reasons.py)."""
	match_reason = {"code": m.reason_code, "args": m.reason_args}
	if position["quantity"] is None:
		return "insufficient_information", reason("quantity_missing")
	if not m.product_id:
		return "review_required", match_reason
	if m.confidence < matcher.CONFIDENT:
		status = "assumption_applied" if m.confidence >= 0.75 else "review_required"
		return status, match_reason
	if catalog_by_id[m.product_id]["supplier_quote_required"]:
		return "supplier_quote_required", reason("supplier_package_provisional")
	return "calculated", match_reason


def prepare_catalog(rows: list[dict], trade: TradeConfig) -> list[dict]:
	"""Catalogue rows with `family` and normalised `attributes` (from columns or trade rules)."""
	return [
		{**r, "family": catalog_family(r, trade), "attributes": catalog_attributes(r, trade)} for r in rows
	]


def page_systems(pages, trade: TradeConfig, parsers) -> dict[int, str]:
	"""System of every page; table pages take the system of the LV pages around them."""
	header = trade.system_header
	systems, last = {}, ""
	for p in pages:
		is_table = any(parser.is_table_page(p.text) for parser in parsers)
		system, _ = page_system(p.text, header) if not is_table else ("", {})
		if system and p.text.strip() and header.search(p.text.splitlines()[0]):
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
	pdf_path,
	catalog_rows: list[dict],
	pages: list[int] | None = None,
	structurer=None,
	trade: TradeConfig | None = None,
	similarity=None,
) -> list[dict]:
	"""`catalog_rows`: product_id, subcategory, description, unit, supplier_quote_required, and
	optionally `family` / `attributes` (else derived from the trade's rules).

	`structurer(block) -> contract` is the optional LLM step (equans_bid.extraction.structurer).
	"""
	trade = trade or load_trade("HVAC")
	parsers = trade.parsers()
	header = trade.system_header
	classifier = FamilyClassifier(trade)
	family_codes = {f.code for f in trade.families}

	page_objs = read_pages(pdf_path, pages)
	text_by_page = {p.number: p.text for p in page_objs}
	systems = page_systems(page_objs, trade, parsers)
	# Only LV pages (with the trade's "<code> <system> Seite n / m" header) hold positions.
	lv_pages = [p for p in page_objs if p.text.strip() and header.search(p.text.splitlines()[0])]

	candidates = []
	label_key_by_block: dict[int, str] = {}
	for raw in segment(lv_pages, classifier.pick_title, header, trade.continuation_labels):
		custom, label_key = custom_attributes(
			raw.context, raw.label, trade, label_key_by_block.get(raw.block_id)
		)
		if label_key:
			label_key_by_block[raw.block_id] = label_key
		candidates.append(
			{
				"source_page": raw.source_page,
				"system": raw.system,
				"title": raw.title,
				"label": raw.label,
				"description_original": raw.text,
				"block_text": raw.text,
				"evidence_lines": [raw.label] if raw.label else [],
				"quantity_raw": raw.quantity_raw,
				"unit_raw": raw.unit_raw,
				"quantity": raw.quantity,
				"unit": raw.unit,
				"kind": classifier.classify(raw.title, "\n".join(raw.context), raw.label),
				"attrs": tender_attributes(raw.label, raw.context, trade),
				"custom_attributes": custom,
				"extraction_confidence": extraction_confidence(raw, text_by_page[raw.source_page]),
				"system_conflict": raw.system_conflict,
				"source_kind": "lv",
			}
		)
	for page in page_objs:
		for parser in parsers:
			if parser.is_table_page(page.text):
				for c in parser.parse_page(page.number, page.text, systems[page.number]):
					# Machine-generated table: values are read exactly, so extraction confidence is high.
					candidates.append(
						{
							**c,
							"block_text": c["description_original"],
							"quantity_raw": str(c["quantity"]),
							"unit_raw": c["unit"],
							"extraction_confidence": 0.9,
						}
					)
	candidates.sort(key=lambda c: c["source_page"])

	catalog = matcher.index_catalog(
		catalog_rows if all("family" in r for r in catalog_rows) else prepare_catalog(catalog_rows, trade)
	)
	catalog_by_id = {c["product_id"]: c for c in catalog}
	families = trade.family_map
	per_page = defaultdict(int)

	def english_label(code):
		return families[code].label("en") if code in families else code

	out = []
	previous_kind = None
	for c in candidates:
		per_page[c["source_page"]] += 1
		kind, attrs, source, error = c["kind"], c["attrs"], "rules", None
		custom = dict(c.get("custom_attributes") or {})
		llm_failures, llm_conflicts, position_ref = [], {}, None
		if kind is None and SAME_AS_ABOVE.match(c["title"]):
			# "wie vorbeschrieben, jedoch ..." repeats the previous position's family.
			kind = previous_kind
		if structurer is not None and c["source_kind"] == "lv":
			contract = structurer(c)
			checked = verify(contract, c, text_by_page[c["source_page"]], family_codes)
			error = contract.get("error") if isinstance(contract, dict) else None
			llm_failures, llm_conflicts, position_ref = (
				checked.failures,
				checked.conflicts,
				checked.position_ref,
			)
			for label, value in checked.custom_attributes.items():
				custom.setdefault(label, value)
			if kind is None and checked.family_hint:
				kind, source = checked.family_hint, "llm"
		previous_kind = kind
		m = matcher.match(kind, attrs, f"{c['title']} {c['label']}", catalog, families, c["unit"], similarity)
		status, why = status_for(c, m, catalog_by_id)
		if source == "llm":
			why = reason("llm_classified", family=kind, detail=why)
		if llm_conflicts and status in ("calculated", "supplier_quote_required"):
			# The model read a different quantity or unit than the rules: a human decides.
			status, why = "review_required", reason("llm_conflict", fields=", ".join(sorted(llm_conflicts)))
		description = re.sub(r"\s+", " ", f"{c['title']} — {c['label']}" if c["label"] else c["title"]).strip(
			" —"
		)
		out.append(
			{
				"position_id": f"P{c['source_page']:03d}-{per_page[c['source_page']]:02d}",
				"position_ref": position_ref,
				"golden_lv_id": None,
				"system": c["system"],
				"source_page": c["source_page"],
				"description_original": c["description_original"],
				# Tender wording is source evidence: never replaced by model text.
				"description": description,
				"quantity_raw": c["quantity_raw"],
				"unit_raw": c["unit_raw"],
				"quantity": c["quantity"],
				"unit": c["unit"],
				"family": kind if kind in family_codes else None,
				"custom_attributes": custom,
				"attributes": {
					"kind": kind,
					"classified_by": source,
					"source_kind": c["source_kind"],
					"evidence_lines": c.get("evidence_lines") or [],
					**attrs,
					**({"system_conflict": c["system_conflict"]} if c.get("system_conflict") else {}),
					**({"llm_failures": llm_failures} if llm_failures else {}),
					**({"llm_conflicts": llm_conflicts} if llm_conflicts else {}),
				},
				"extraction_confidence": c["extraction_confidence"],
				"matched_product": m.product_id,
				"match_confidence": m.confidence,
				"status": status,
				"reason_code": why["code"],
				"reason_args": why["args"],
				"status_reason": render(why["code"], why["args"], family_label=english_label),  # for logs
				"error": error,
			}
		)
	return out
