"""PDF -> extracted, matched positions with a status. No pricing and no Frappe here.

Everything trade-specific comes from a `TradeConfig` (equans_bid.trades): page header, family
recognition, attribute rules, table-parser plug-ins. With an LLM configured (`mapper`), the model
reads every LV position and maps it to the catalogue; its answer is verified against the page and
the catalogue and combined with the rules result (see `combine`). Quantity, unit and page priced
are always the ones read from the PDF, and nothing here computes money.
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


def combine(c: dict, m: matcher.Match, status: str, why: dict, checked, catalog_by_id: dict):
	"""Rules match + verified LLM answer -> (match, status, reason, matched_by).

	- both pick the same item: confirmed by two independent methods;
	- the LLM finds a stronger match than the rules: priced as an assumption (exact fit, and of
	  the family the rules recognised, if any) or proposed for review; a weaker one is ignored;
	- the rules are certain (family and sizes agree) and the LLM picks another item: the rules
	  match stands, the LLM answer is kept for review;
	- the LLM read another quantity or unit than printed: a human decides.
	The quantity and unit priced are always the ones read from the page.
	"""
	pid = checked.product_id
	matched_by = "rules"
	if pid and pid == m.product_id:
		matched_by = "llm+rules"
		if checked.fit == "exact" and m.confidence < matcher.CONFIDENT:
			m = matcher.Match(pid, matcher.CONFIDENT, "llm_confirmed", {"product": pid})
			status, why = status_for(c, m, catalog_by_id)
	elif pid and m.product_id and m.confidence >= matcher.CONFIDENT:
		# Family and every key size already agree with the rules item, and the checks reject an
		# LLM item with other sizes: a different pick here is another kind of product or a guess.
		# The certain rules match stands; the answer stays visible in the review panel.
		pass
	elif pid:
		# A product of another family than the one the rules recognised is only a proposal.
		other_family = c.get("kind") and catalog_by_id[pid]["kind"] != c["kind"]
		exact = checked.fit == "exact" and not other_family
		confidence = matcher.ASSUMED if exact else matcher.PROPOSED
		if confidence > m.confidence or not m.product_id:
			# Only an answer that is stronger than the rules result replaces it.
			matched_by = "llm"
			m = matcher.Match(pid, confidence, "llm_matched", {"product": pid})
			status, why = status_for(c, m, catalog_by_id)
	if checked.conflicts and status in ("calculated", "supplier_quote_required", "assumption_applied"):
		status = "review_required"
		why = reason("llm_conflict", fields=", ".join(sorted(checked.conflicts)))
	return m, status, why, matched_by


def _llm_evidence(checked) -> dict:
	"""What the model answered, for the review panel (model text is English, never translated)."""
	return {
		"llm": {
			"product_id": checked.product_id,
			"fit": checked.fit,
			"note": checked.note,
			**({"failures": checked.failures} if checked.failures else {}),
			**({"conflicts": checked.conflicts} if checked.conflicts else {}),
		}
	}


def prepare_catalog(rows: list[dict], trade: TradeConfig) -> list[dict]:
	"""Catalogue rows with `family` and normalised `attributes` (from columns or trade rules)."""
	return [
		{**r, "family": catalog_family(r, trade), "attributes": catalog_attributes(r, trade)} for r in rows
	]


def detect_trade(pdf_path, trades: list[TradeConfig], samples: int = 60) -> tuple[str | None, dict]:
	"""(trade code, LV pages found per trade) from the PDF itself: the trade whose LV page header
	("244.01 LA01 … Seite 3/20") starts the most sampled pages. None when no header matches."""
	import pdfplumber

	with pdfplumber.open(Path(pdf_path)) as pdf:
		n = len(pdf.pages)
	numbers = list(range(1, n + 1, max(1, n // samples)))
	first_lines = [p.text.strip().splitlines()[0] for p in read_pages(pdf_path, numbers) if p.text.strip()]
	scores = {t.code: sum(1 for line in first_lines if t.system_header.search(line)) for t in trades}
	best = max(scores, key=scores.get, default=None)
	return (best if best and scores[best] else None), scores


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
	mapper=None,
	trade: TradeConfig | None = None,
	similarity=None,
) -> list[dict]:
	"""`catalog_rows`: product_id, subcategory, description, unit, supplier_quote_required, and
	optionally `family` / `attributes` (else derived from the trade's rules).

	`mapper(page, page_text, positions, catalog) -> [Checked]` is the LLM step
	(equans_bid.extraction.llm_mapper); without it the rules extract and match alone.
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

	# Family per position from the rules; "wie vorbeschrieben, jedoch ..." repeats the previous one.
	previous_kind = None
	for c in candidates:
		if c["kind"] is None and SAME_AS_ABOVE.match(c["title"]):
			c["kind"] = previous_kind
		previous_kind = c["kind"]

	# LLM: reads every LV position and maps it to the catalogue, one request per page.
	answers = {}
	if mapper is not None:
		by_page = defaultdict(list)
		for c in candidates:
			if c["source_kind"] == "lv":
				by_page[c["source_page"]].append(c)
		for page, group in by_page.items():
			for c, answer in zip(group, mapper(page, text_by_page[page], group, catalog), strict=True):
				answers[id(c)] = answer

	out = []
	for c in candidates:
		per_page[c["source_page"]] += 1
		kind, attrs, source, matched_by, error = c["kind"], c["attrs"], "rules", "rules", None
		custom = dict(c.get("custom_attributes") or {})
		checked = answers.get(id(c))
		if checked is not None and kind is None and checked.family:
			kind, source = checked.family, "llm"
		m = matcher.match(kind, attrs, f"{c['title']} {c['label']}", catalog, families, c["unit"], similarity)
		status, why = status_for(c, m, catalog_by_id)
		if checked is not None:
			for label, value in checked.custom_attributes.items():
				custom.setdefault(label, value)
			m, status, why, matched_by = combine(c, m, status, why, checked, catalog_by_id)
			if "llm_error" in checked.failures:
				error = getattr(mapper, "last_error", None)
		if source == "llm":
			# Only the LLM recognised what the product is: priced at most as an assumption.
			matched_by = "llm"
			if why["code"] not in ("llm_conflict", "llm_disagrees"):
				why = reason("llm_classified", family=kind, detail=why)
			if status == "calculated":
				status = "assumption_applied"
		product_kind = catalog_by_id[m.product_id]["kind"] if m.product_id else None
		kind = kind or product_kind
		description = re.sub(r"\s+", " ", f"{c['title']} — {c['label']}" if c["label"] else c["title"]).strip(
			" —"
		)
		out.append(
			{
				"position_id": f"P{c['source_page']:03d}-{per_page[c['source_page']]:02d}",
				"position_ref": None,
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
					"matched_by": matched_by,
					**(_llm_evidence(checked) if checked is not None else {}),
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
