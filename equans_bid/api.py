"""Whitelisted API for the estimator SPA. All money is computed here, in Python."""

import json
from collections import defaultdict
from pathlib import Path

import frappe
from frappe import _

from equans_bid.extraction.llm import get_enricher
from equans_bid.extraction.pdf_text import file_sha256
from equans_bid.extraction.pipeline import STARTER, extract_positions
from equans_bid.pricing.engine import factor_keys_for_system, price_position
from equans_bid.pricing.project import bid_range, effective_assumptions, indicative_price, project_baseline

PRICED_STATUSES = {"calculated", "supplier_quote_required", "assumption_applied"}
PROVISIONAL_STATUSES = {"supplier_quote_required", "assumption_applied"}
EXCLUDED_STATUSES = {"out_of_scope", "non_priceable"}
COST_FIELDS = ("net_unit_cost", "material_cost", "labour_hours", "labour_rate", "labour_cost", "direct_cost")


def get_params() -> dict:
	raw = frappe.get_single("Project Parameter").parameters
	if not raw:
		frappe.throw(_("Project parameters are missing. Run equans_bid.commands.seed_data.run first."))
	return json.loads(raw) if isinstance(raw, str) else raw


def _catalog_rows() -> list[dict]:
	return frappe.get_all(
		"Catalog Item",
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
		],
	)


def _rules() -> dict:
	rows = frappe.get_all(
		"Productivity Rule",
		fields=["install_code", "base_hours_per_unit", "default_hourly_rate_chf", "factor_keys"],
	)
	return {r.install_code: r for r in rows}


def _tender_pdf_path(tender) -> Path:
	if tender.tender_file:
		file = frappe.get_doc("File", {"file_url": tender.tender_file})
		return Path(file.get_full_path())
	return STARTER / "BKP_244_LV_Lueftung_260804.pdf"


def _price_item(item, catalog: dict, rules: dict, params: dict):
	"""Fill an item's cost fields. Unpriced statuses keep zero costs and say so in the UI."""
	for f in COST_FIELDS:
		item.set(f, 0)
	product = catalog.get(item.matched_product)
	if item.status not in PRICED_STATUSES or not product or not item.quantity:
		item.price_source = None
		return
	rule = rules.get(product.install_code)
	if not rule:
		item.status = "review_required"
		item.status_reason = f"Keine Leistungsregel {product.install_code}"
		return
	cost = price_position(
		item.quantity,
		product.net_cost_chf,
		rule.base_hours_per_unit,
		rule.default_hourly_rate_chf,
		factor_keys_for_system(rule.factor_keys, item.system),
		params,
		quote_override=item.quote_override or None,
	)
	item.install_code = product.install_code
	item.net_unit_cost = product.net_cost_chf
	item.price_source = "supplier_quote" if item.quote_override else product.source_type
	item.update(cost.as_dict())


def _recalculate(tender, params: dict | None = None):
	"""Reprice every position, then the tender totals."""
	params = params or get_params()
	catalog = {c.product_id: c for c in _catalog_rows()}
	rules = _rules()
	for item in tender.items:
		_price_item(item, catalog, rules, params)
	_apply_totals(tender, catalog, params)


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


@frappe.whitelist()
def process_tender_pdf(tender: str, pages: str | list | None = None):
	"""Extract, match and price every position of the tender PDF. Replaces existing items."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	if isinstance(pages, str):
		pages = json.loads(pages)
	doc.db_set("status", "Processing")
	try:
		path = _tender_pdf_path(doc)
		enrich = get_enricher(frappe.get_site_path("private", "extraction_cache"))
		positions = extract_positions(path, _catalog_rows(), pages, enrich=enrich)
		doc.file_hash = file_sha256(path)
		doc.set("items", [])
		for p in positions:
			doc.append("items", {**p, "attributes": json.dumps(p["attributes"])})
		_recalculate(doc)
		doc.status = "Completed"
		# Record which provider saw the tender text (data-handling requirement).
		llm = enrich.stats() if enrich else "LLM: nicht konfiguriert (nur Regeln)"
		doc.processing_log = f"{len(positions)} Positionen aus {path.name} extrahiert. {llm}"
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
	frappe.enqueue("equans_bid.api.process_tender_pdf", tender=tender, queue="long", timeout=1800)
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
	tender: str, item: str, quote_override=None, matched_product: str | None = None, status: str | None = None
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
		row.status_reason = "Produkt durch Kalkulator gesetzt"
	if status:
		allowed = row.meta.get_field("status").options.split("\n")
		if status not in allowed:
			frappe.throw(_("Unknown status {0}").format(status))
		row.status = status
		row.status_reason = "Status durch Kalkulator gesetzt"

	params = get_params()
	catalog = {c.product_id: c for c in _catalog_rows()}
	_price_item(row, catalog, _rules(), params)
	_apply_totals(doc, catalog, params)
	row.db_update()
	doc.db_update()
	return {"item": row.as_dict(), "summary": get_tender_summary(tender)}


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

	by_system = defaultdict(lambda: {"direct_cost": 0.0, "positions": 0})
	by_category = defaultdict(lambda: {"direct_cost": 0.0, "positions": 0})
	by_status = defaultdict(lambda: {"direct_cost": 0.0, "positions": 0})
	for i in doc.items:
		product = catalog.get(i.matched_product)
		category = product.category if product and i.status in PRICED_STATUSES else "-"
		for bucket in (by_system[i.system or "-"], by_category[category], by_status[i.status]):
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
		"bid_range": bid_range(baseline, params, overrides),
		"assumptions": effective_assumptions(params, overrides),
		"default_assumptions": effective_assumptions(params),
		"win_probability_note": "Model estimate from project parameters, not calibrated on past bids.",
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


EXPORT_COLUMNS = [
	("position_id", "LV-ID"),
	("golden_lv_id", "Referenz-LV"),
	("system", "Anlage"),
	("source_page", "Seite"),
	("description", "Beschreibung"),
	("quantity", "Menge"),
	("unit", "Einheit"),
	("matched_product", "Produkt"),
	("status", "Status"),
	("status_reason", "Begründung"),
	("price_source", "Preisquelle"),
	("quote_override", "Offerte CHF"),
	("material_cost", "Material CHF"),
	("labour_hours", "Stunden"),
	("labour_rate", "Ansatz CHF/h"),
	("labour_cost", "Arbeit CHF"),
	("direct_cost", "Direkte Kosten CHF"),
]

STATUS_DE = {
	"calculated": "Berechnet",
	"supplier_quote_required": "Offerte nötig",
	"assumption_applied": "Annahme",
	"review_required": "Prüfung nötig",
	"insufficient_information": "Angaben fehlen",
	"out_of_scope": "Ausser Umfang",
	"non_priceable": "Nicht kalkulierbar",
}
SCENARIO_DE = {"Aggressive": "Aggressiv", "Target": "Zielmarge", "Conservative": "Konservativ"}
UNIT_DE = {"pc": "Stk", "m": "m", "m2": "m2", "m3": "m3", "h": "Std", "LS": "psch", "system": "Anlage"}

BUILD_UP_LABELS = [
	("catalog_material", "Material Katalog"),
	("supplier_material", "Lieferpakete"),
	("labour", "Montage (Arbeit)"),
	("small_material", "Kleinmaterial"),
	("supplier_contingency", "Reserve Lieferpakete"),
	("project_costs", "Projektkosten (Engineering, IBS, Hygiene, Doku)"),
	("direct_cost", "Direkte Kosten"),
	("transport_equipment", "Transport & Geräte"),
	("overhead", "Gemeinkosten"),
	("cost_baseline", "Kostenbasis"),
]


@frappe.whitelist()
def export_tender(tender: str):
	"""Priced offer as CSV (semicolon, UTF-8 with BOM, opens directly in Excel CH)."""
	import csv
	import io

	summary = get_tender_summary(tender)
	doc = frappe.get_doc("Tender", tender)
	buf = io.StringIO()
	w = csv.writer(buf, delimiter=";")
	w.writerow([f"Erstpreis {doc.project_name}", f"Stand {frappe.utils.now_datetime():%d.%m.%Y %H:%M}"])
	w.writerow([])
	w.writerow([label for _, label in EXPORT_COLUMNS])
	for i in doc.items:
		row = {f: i.get(f) for f, _ in EXPORT_COLUMNS}
		row["status"] = STATUS_DE.get(i.status, i.status)
		row["unit"] = UNIT_DE.get(i.unit, i.unit)
		w.writerow(["" if row[f] is None else row[f] for f, _ in EXPORT_COLUMNS])
	w.writerow([])
	w.writerow(["Kostenaufbau", "CHF"])
	for key, label in BUILD_UP_LABELS:
		w.writerow([label, summary["build_up"][key]])
	w.writerow(["Offene Positionen ohne Preis", summary["totals"]["unresolved_count"]])
	w.writerow([])
	w.writerow(
		[
			"Szenario",
			"Angebotspreis CHF",
			"Marge %",
			"Gewinnchance",
			"Deckungsbeitrag bei Zuschlag CHF",
			"Erwarteter Beitrag CHF",
			"Empfohlen",
		]
	)
	for sc in summary["bid_range"]:
		w.writerow(
			[
				SCENARIO_DE.get(sc["scenario"], sc["scenario"]),
				sc["bid_price_chf"],
				sc["margin_pct"],
				sc["estimated_win_probability"],
				sc["contribution_if_won_chf"],
				sc["expected_contribution_chf"],
				"ja" if sc["recommended"] else "",
			]
		)
	w.writerow(
		[
			"Richtpreis (Zielmarge)",
			summary["indicative_price"]["bid_price_chf"],
			summary["indicative_price"]["margin_pct"],
		]
	)
	w.writerow(
		[
			"Gewinnchance: Modellschätzung aus den Projektparametern, nicht auf historische Angebote kalibriert."
		]
	)

	safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in doc.project_name)[:60]
	frappe.local.response.filename = f"Erstpreis_{safe}_{frappe.utils.nowdate()}.csv"
	frappe.local.response.filecontent = "\ufeff" + buf.getvalue()
	frappe.local.response.type = "download"


@frappe.whitelist()
def calculate_tender_position(item: str):
	"""Price one Tender Item by row name (kept for the SRS interface)."""
	parent = frappe.db.get_value("Tender Item", item, "parent")
	return recalculate_tender(parent)
