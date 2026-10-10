"""Whitelisted API for the estimator SPA. All money is computed here, in Python."""

import json
from collections import defaultdict
from pathlib import Path

import frappe
from frappe import _

from equans_bid.extraction.benchmark import assign_golden_ids
from equans_bid.extraction.llm_mapper import get_mapper
from equans_bid.extraction.pdf_text import file_sha256
from equans_bid.extraction.pipeline import STARTER, detect_trade, extract_positions
from equans_bid.pricing.engine import (
	apply_factor_rules,
	parse_factor_keys,
	price_position,
)
from equans_bid.pricing.project import (
	bid_range,
	effective_assumptions,
	indicative_price,
	project_baseline,
	selected_bid,
	validate_selection,
)
from equans_bid.reasons import render
from equans_bid.trades import TradeConfig, from_documents

PRICED_STATUSES = {"calculated", "supplier_quote_required", "assumption_applied"}
PROVISIONAL_STATUSES = {"supplier_quote_required", "assumption_applied"}
EXCLUDED_STATUSES = {"out_of_scope", "non_priceable"}
# Computed on every recalculation. The snapshot (net_unit_cost, base_hours_per_unit, labour_rate,
# factor_keys, price_version) is only taken when a position is first priced, its product changes,
# or the estimator confirms a price refresh.
COST_FIELDS = ("material_cost", "labour_hours", "labour_cost", "direct_cost")
STARTER_PDF = STARTER / "BKP_244_LV_Lueftung_260804.pdf"


def get_params() -> dict:
	raw = frappe.get_single("Project Parameter").parameters
	if not raw:
		frappe.throw(_("Project parameters are missing. Run equans_bid.commands.seed_data.run first."))
	return json.loads(raw) if isinstance(raw, str) else raw


def _catalog_rows(trade: str | None = None) -> list[dict]:
	"""Central catalogue (global master), optionally limited to one trade; attributes parsed."""
	filters = {"trade": ["in", [trade, ""]]} if trade else {}
	rows = frappe.get_all(
		"Catalog Item",
		filters=filters,
		fields=[
			"product_id",
			"category",
			"subcategory",
			"description",
			"unit",
			"net_cost_chf",
			"install_code",
			"source_type",
			"supplier_quote_required",
			"family",
			"attributes",
			"price_version",
		],
	)
	for r in rows:
		r.attributes = (
			json.loads(r.attributes)
			if isinstance(r.attributes, str) and r.attributes
			else (r.attributes or {})
		)
	return rows


@frappe.whitelist()
def family_labels() -> dict:
	"""Display labels of all product families, by code (master data, for UI and export)."""
	out = {}
	for row in frappe.get_all("Product Family", fields=["family_code", "labels"]):
		labels = row.labels
		out[row.family_code] = json.loads(labels) if isinstance(labels, str) and labels else (labels or {})
	return out


def trade_config(code: str | None) -> TradeConfig:
	"""Trade + Product Family master data as the pipeline's TradeConfig."""
	code = code or "HVAC"
	if not frappe.db.exists("Trade", code):
		frappe.throw(_("Trade {0} is not configured. Run equans_bid.commands.seed_data.run.").format(code))
	families = [
		frappe.get_doc("Product Family", name)
		for name in frappe.get_all("Product Family", {"trade": code}, pluck="name", order_by="priority asc")
	]
	return from_documents(frappe.get_doc("Trade", code), families)


def _detect_trade(path) -> str:
	"""The trade of a tender PDF, recognised from its LV page headers (master data)."""
	trades = [trade_config(code) for code in frappe.get_all("Trade", pluck="name")]
	code, _scores = detect_trade(path, trades)
	if not code:
		frappe.throw(_("The trade of this tender could not be recognised. Please select it."))
	return code


def _rules() -> dict:
	rows = frappe.get_all(
		"Productivity Rule",
		fields=[
			"install_code",
			"base_hours_per_unit",
			"default_hourly_rate_chf",
			"factor_keys",
		],
	)
	return {r.install_code: r for r in rows}


def _tender_pdf_path(tender) -> Path:
	if tender.tender_file:
		file = frappe.get_doc("File", {"file_url": tender.tender_file})
		return Path(file.get_full_path())
	return STARTER / "BKP_244_LV_Lueftung_260804.pdf"


def _set_reason(item, code: str, **args):
	"""Store the reason as a code (translated at display time) plus its English text for logs."""
	item.reason_code = code
	item.reason_args = json.dumps(args) if args else None
	item.status_reason = render(code, args)


def _snapshot(item, product, rule, factor_rules: list) -> None:
	"""Freeze the catalogue and productivity values this position is priced with."""
	item.install_code = product.install_code
	item.net_unit_cost = product.net_cost_chf
	item.base_hours_per_unit = rule.base_hours_per_unit
	item.labour_rate = rule.default_hourly_rate_chf
	keys = apply_factor_rules(
		rule.factor_keys,
		{"system": item.system, "page": item.source_page},
		factor_rules,
	)
	item.factor_keys = "|".join(keys)
	item.price_version = product.price_version or "unversioned"


def _price_item(
	item,
	catalog: dict,
	rules: dict,
	params: dict,
	factor_rules: list,
	refresh: bool = False,
):
	"""Fill an item's cost fields from its snapshot (taken now if missing or `refresh`).
	Unpriced statuses keep zero costs and the UI shows "—"."""
	for f in COST_FIELDS:
		item.set(f, 0)
	product = catalog.get(item.matched_product)
	if item.status not in PRICED_STATUSES or not product or not item.quantity:
		item.price_source = None
		return
	if refresh or not item.price_version or item.install_code != product.install_code:
		rule = rules.get(product.install_code)
		if not rule:
			item.status = "review_required"
			_set_reason(item, "no_productivity_rule", install_code=product.install_code)
			return
		_snapshot(item, product, rule, factor_rules)
	cost = price_position(
		item.quantity,
		item.net_unit_cost,
		item.base_hours_per_unit,
		item.labour_rate,
		parse_factor_keys(item.factor_keys),
		params,
		quote_override=item.quote_override or None,
	)
	item.price_source = "supplier_quote" if item.quote_override else product.source_type
	item.update(cost.as_dict())


def _recalculate(tender, params: dict | None = None, refresh: bool = False):
	"""Reprice every position (from snapshots unless `refresh`), then the tender totals."""
	params = params or get_params()
	catalog = {c.product_id: c for c in _catalog_rows()}
	rules = _rules()
	factor_rules = trade_config(tender.trade).factor_rules
	for item in tender.items:
		_price_item(item, catalog, rules, params, factor_rules, refresh)
	_apply_totals(tender, catalog, params)
	if refresh or not tender.catalog_priced_at:
		tender.catalog_priced_at = frappe.utils.now_datetime()
		versions = sorted({i.price_version for i in tender.items if i.price_version})
		tender.price_version = ", ".join(versions)[:140]


def _apply_totals(tender, catalog: dict, params: dict):
	"""Tender totals from the already-priced positions. A missing price never counts as CHF 0:
	unpriced positions are counted in `unresolved_count`, not summed."""
	material = labour = confirmed = provisional = 0.0
	unresolved = 0
	for item in tender.items:
		material += item.material_cost or 0
		labour += item.labour_cost or 0
		if item.status == "calculated" or (item.status == "supplier_quote_required" and item.quote_override):
			confirmed += item.direct_cost or 0
		elif item.status in PROVISIONAL_STATUSES:
			provisional += item.direct_cost or 0
		elif item.status not in EXCLUDED_STATUSES:
			unresolved += 1
	tender.material_cost = material
	tender.labour_cost = labour
	tender.direct_cost = material + labour
	tender.confirmed_cost = confirmed
	tender.provisional_cost = provisional
	tender.unresolved_count = unresolved
	tender.cost_baseline = float(_build_up(tender, catalog, params)["cost_baseline"])


def _build_up(tender, catalog: dict, params: dict) -> dict:
	catalog_material = supplier_material = labour = 0.0
	for item in tender.items:
		product = catalog.get(item.matched_product)
		if product and product.source_type == "supplier_package":
			supplier_material += item.material_cost
		else:
			catalog_material += item.material_cost
		labour += item.labour_cost
	return project_baseline(catalog_material, supplier_material, labour, params)


def _position_key(item) -> tuple:
	"""The same position in a rerun: page, printed text, unit and quantity (not the row name)."""
	text = " ".join(str(item.get("description_original") or "").split())
	return (item.get("source_page"), text, item.get("unit"), float(item.get("quantity") or 0))


def _estimator_edits(doc) -> dict:
	"""What the estimator entered on the current positions, by position key."""
	edits = {}
	for i in doc.items:
		edit = {}
		if i.quote_override:
			edit["quote_override"] = i.quote_override
		if i.reason_code == "product_set_by_estimator" and i.matched_product:
			edit["matched_product"] = i.matched_product
		if i.reason_code == "status_set_by_estimator":
			edit["status"] = i.status
		if edit:
			edits[_position_key(i)] = edit
	return edits


def _restore_edits(row, edit: dict | None) -> None:
	"""Apply an earlier estimator edit to the re-extracted position (it wins over the machine)."""
	if not edit:
		return
	if "matched_product" in edit and frappe.db.exists("Catalog Item", edit["matched_product"]):
		row.matched_product = edit["matched_product"]
		row.match_confidence = 1.0
		quote = frappe.db.get_value("Catalog Item", row.matched_product, "supplier_quote_required")
		row.status = "supplier_quote_required" if quote else "calculated"
		_set_reason(row, "product_set_by_estimator")
	if "status" in edit:
		row.status = edit["status"]
		_set_reason(row, "status_set_by_estimator")
	if "quote_override" in edit:
		row.quote_override = edit["quote_override"]


@frappe.whitelist()
def process_tender_pdf(tender: str, pages: str | list | None = None):
	"""Extract, match and price every position of the tender PDF. Replaces existing items, but
	keeps the estimator's work: quotes, hand-picked products and statuses (see _estimator_edits)."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	if isinstance(pages, str):
		pages = json.loads(pages)
	doc.db_set("status", "Processing")
	try:
		path = _tender_pdf_path(doc)
		if not doc.trade:
			doc.trade = _detect_trade(path)
		trade = trade_config(doc.trade)
		catalog = _catalog_rows(trade.code)
		mapper = get_mapper(
			[f.code for f in trade.families], frappe.get_site_path("private", "extraction_cache")
		)
		positions = extract_positions(path, catalog, pages, mapper, trade)
		doc.file_hash = file_sha256(path)
		if doc.file_hash == file_sha256(STARTER_PDF):
			# Verified example rows exist for this tender only (the UI shows their LV IDs).
			assign_golden_ids(positions, catalog)
		edits = _estimator_edits(doc)
		doc.set("items", [])
		for p in positions:
			row = doc.append(
				"items",
				{
					**p,
					"attributes": json.dumps(p["attributes"], ensure_ascii=False),
					"custom_attributes": json.dumps(p["custom_attributes"], ensure_ascii=False),
					"reason_args": json.dumps(p["reason_args"] or {}),
				},
			)
			_restore_edits(row, edits.get(_position_key(row)))
		doc.catalog_priced_at = None
		_recalculate(doc)
		doc.status = "Completed"
		# Record which provider saw the tender text (data-handling requirement). Structured, so the
		# UI shows it in the user's language; processing_log keeps an English line for admins.
		llm = mapper.info() if mapper else None
		doc.processing_info = json.dumps({"positions": len(positions), "file": path.name, "llm": llm})
		doc.processing_log = f"{len(positions)} positions extracted from {path.name}. " + (
			mapper.stats() if mapper else "LLM: not configured (rules only)"
		)
		doc.save()
	except Exception as e:
		frappe.db.rollback()
		frappe.db.set_value("Tender", tender, {"status": "Failed", "processing_log": str(e)[:500]})
		frappe.db.commit()
		raise
	return get_tender_summary(tender)


@frappe.whitelist()
def start_processing(tender: str):
	"""Queue extraction in the background so the UI stays responsive."""
	frappe.get_doc("Tender", tender).check_permission("write")
	frappe.db.set_value("Tender", tender, "status", "Processing")
	frappe.enqueue(
		"equans_bid.api.process_tender_pdf", tender=tender, queue="long", timeout=5400
	)  # first LLM run of a large PDF on a rate-limited tier
	return {"status": "Processing"}


@frappe.whitelist()
def recalculate_tender(tender: str):
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	_recalculate(doc)
	doc.save()
	return get_tender_summary(tender)


@frappe.whitelist()
def update_item(
	tender: str,
	item: str,
	quote_override=None,
	matched_product: str | None = None,
	status: str | None = None,
):
	"""Estimator edits one position (supplier quote, product, status).

	Only that row is repriced and written, then the tender totals: a full save of ~450 child
	rows would miss the 500 ms budget for an inline edit.
	"""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	row = next((i for i in doc.items if i.name == item), None)
	if not row:
		frappe.throw(_("Position {0} not found in tender {1}").format(item, tender))
	if quote_override is not None:
		quote = float(quote_override) if quote_override not in ("", None) else 0
		if quote < 0:
			frappe.throw(_("A supplier quote cannot be negative"))
		row.quote_override = quote
	if matched_product:
		product = frappe.get_doc("Catalog Item", matched_product)
		row.matched_product = matched_product
		row.match_confidence = 1.0
		row.status = "supplier_quote_required" if product.supplier_quote_required else "calculated"
		_set_reason(row, "product_set_by_estimator")
	if status:
		allowed = row.meta.get_field("status").options.split("\n")
		if status not in allowed:
			frappe.throw(_("Unknown status {0}").format(status))
		row.status = status
		_set_reason(row, "status_set_by_estimator")

	params = get_params()
	catalog = {c.product_id: c for c in _catalog_rows()}
	factor_rules = trade_config(doc.trade).factor_rules
	# A new product means new catalogue values: take a fresh snapshot for this row only.
	_price_item(row, catalog, _rules(), params, factor_rules, refresh=bool(matched_product))
	_apply_totals(doc, catalog, params)
	row.db_update()
	doc.db_update()
	return {"item": row.as_dict(), "summary": get_tender_summary(tender)}


def _refresh_diff(doc) -> dict:
	"""What a price refresh would change, per position and in total (nothing is saved)."""
	before = {i.name: i.direct_cost or 0 for i in doc.items}
	total_before = doc.direct_cost or 0
	_recalculate(doc, refresh=True)
	changes = [
		{
			"item": i.name,
			"position_id": i.position_id,
			"before": before[i.name],
			"after": i.direct_cost or 0,
		}
		for i in doc.items
		if abs((i.direct_cost or 0) - before[i.name]) >= 0.005
	]
	return {
		"changes": changes,
		"total_before": total_before,
		"total_after": doc.direct_cost or 0,
	}


@frappe.whitelist()
def preview_price_refresh(tender: str):
	"""Diff between the tender's frozen prices and today's catalogue; changes nothing."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("read")
	return _refresh_diff(doc)


@frappe.whitelist()
def apply_price_refresh(tender: str):
	"""Re-snapshot every position from today's catalogue (after the estimator saw the diff)."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	diff = _refresh_diff(doc)
	doc.save()
	return {**diff, "summary": get_tender_summary(tender)}


@frappe.whitelist()
def get_tender_pdf(tender: str):
	"""Serve the tender PDF inline for the traceability viewer."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("read")
	path = _tender_pdf_path(doc)
	frappe.local.response.filename = path.name
	frappe.local.response.filecontent = path.read_bytes()
	frappe.local.response.type = "pdf"


def _assumptions(doc) -> dict:
	raw = doc.bid_assumptions
	if not raw:
		return {}
	return json.loads(raw) if isinstance(raw, str) else raw


@frappe.whitelist()
def get_tender_summary(tender: str, assumptions: str | dict | None = None):
	"""Totals by system, category and status, the project build-up and the Recommended Bid Range.

	`assumptions` previews bid overrides without saving them; otherwise the tender's saved
	overrides apply.
	"""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("read")
	params = get_params()
	if isinstance(assumptions, str):
		assumptions = json.loads(assumptions)
	overrides = assumptions if assumptions is not None else _assumptions(doc)
	catalog = {c.product_id: c for c in _catalog_rows()}
	build_up = _build_up(doc, catalog, params)
	baseline = build_up["cost_baseline"]

	scenarios = bid_range(baseline, params, overrides)
	chosen = selected_bid(baseline, params, overrides, _selection(doc))
	for sc in scenarios:
		sc["selected"] = bool(chosen) and chosen["scenario"] == sc["scenario"]

	by_system = defaultdict(lambda: {"direct_cost": 0.0, "positions": 0})
	by_category = defaultdict(lambda: {"direct_cost": 0.0, "positions": 0})
	by_status = defaultdict(lambda: {"direct_cost": 0.0, "positions": 0})
	for i in doc.items:
		product = catalog.get(i.matched_product)
		category = product.category if product and i.status in PRICED_STATUSES else "-"
		for bucket in (
			by_system[i.system or "-"],
			by_category[category],
			by_status[i.status],
		):
			bucket["direct_cost"] += i.direct_cost
			bucket["positions"] += 1

	return {
		"tender": doc.name,
		"status": doc.status,
		"totals": {
			"material_cost": doc.material_cost,
			"labour_cost": doc.labour_cost,
			"direct_cost": doc.direct_cost,
			"confirmed_cost": doc.confirmed_cost,
			"provisional_cost": doc.provisional_cost,
			"unresolved_count": doc.unresolved_count,
		},
		"build_up": {k: float(v) for k, v in build_up.items()},
		"parameters": {
			"overhead_pct": params["commercial"]["overhead_pct"],
			"target_margin_pct": params["commercial"]["target_margin_pct"],
			**{k: params["allowances"][k] for k in params["allowances"]},
		},
		"by_system": dict(by_system),
		"by_category": dict(by_category),
		"by_status": dict(by_status),
		"indicative_price": indicative_price(baseline, params),
		"bid_range": scenarios,
		"selected_bid": chosen,
		"assumptions": effective_assumptions(params, overrides),
		"default_assumptions": effective_assumptions(params),
	}


@frappe.whitelist()
def set_bid_assumptions(tender: str, assumptions: str | dict | None = None):
	"""Save (or with None, reset) the tender's bid overrides; values are validated and clamped."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	if isinstance(assumptions, str):
		assumptions = json.loads(assumptions) if assumptions else None
	clean = effective_assumptions(get_params(), assumptions) if assumptions else None
	doc.db_set("bid_assumptions", json.dumps(clean) if clean else None)
	return get_tender_summary(tender)


def _selection(doc) -> dict | None:
	raw = doc.bid_selection
	if not raw:
		return None
	return json.loads(raw) if isinstance(raw, str) else raw


@frappe.whitelist()
def set_bid_selection(tender: str, scenario: str | None = None, margin_pct=None, price_chf=None) -> dict:
	"""Choose the bid to submit: a scenario name, or "custom" with a margin (%) or a price (CHF).
	Without a scenario the choice is cleared."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	selection = None
	margin_pct = None if margin_pct in ("", None) else margin_pct
	price_chf = None if price_chf in ("", None) else price_chf
	if scenario:
		try:
			selection = validate_selection(
				{"scenario": scenario, "margin_pct": margin_pct, "price_chf": price_chf}, get_params()
			)
		except (TypeError, ValueError) as e:
			frappe.throw(_("Invalid bid selection: {0}").format(e))
	doc.db_set("bid_selection", json.dumps(selection) if selection else None)
	return get_tender_summary(tender)


@frappe.whitelist()
def export_tender(tender: str, lang: str | None = None, format: str = "xlsx"):
	"""Priced offer as an Excel workbook (default) or CSV, in the given UI locale (default de-CH)."""
	from equans_bid.export import build_csv, build_xlsx

	summary = get_tender_summary(tender)
	doc = frappe.get_doc("Tender", tender)
	now = frappe.utils.now_datetime()
	if format == "csv":
		filename, content = build_csv(doc, summary, lang, now, family_labels=family_labels())
	else:
		descriptions = {c.product_id: c.description for c in _catalog_rows()}
		filename, content = build_xlsx(
			doc, summary, lang, now, family_labels=family_labels(), catalog=descriptions
		)
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"


@frappe.whitelist()
def calculate_tender_position(item: str):
	"""Price one Tender Item by row name (kept for the SRS interface)."""
	parent = frappe.db.get_value("Tender Item", item, "parent")
	return recalculate_tender(parent)
