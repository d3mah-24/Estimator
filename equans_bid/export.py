"""Priced offer in the estimator's locale: an Excel workbook (main output) or a CSV.

Excel (`build_xlsx`): sheets Positions, Summary, Bid range, Open points, Assumptions. Amounts
are real numbers with a CHF number format, so they sum and sort in Excel; a position without a
price shows "—", never 0. CSV (`build_csv`): every amount appears twice: formatted for the locale (babel) and as a raw dot-decimal number,
so the file reads well and still calculates in Excel whatever its regional settings. A position
without a price shows "—" (formatted) and an empty raw cell, never 0. Tender text is copied
as extracted, untranslated.
"""

import csv
import io

from equans_bid.localization import CTX_EXPORT, MISSING, Localizer

PRICED_STATUSES = {"calculated", "supplier_quote_required", "assumption_applied"}

# (field, header) for plain columns, in order.
TEXT_COLUMNS = [
	("position_id", "LV ID"),
	("golden_lv_id", "Reference LV"),
	("system", "System"),
	("source_page", "Page"),
	("description", "Description"),
	("quantity", "Quantity"),
	("unit", "Unit"),
	("matched_product", "Product"),
	("status", "Status"),
	("reason", "Reason"),
	("price_source", "Price source"),
]
# (field, header) for amounts: a formatted column and a raw-number column each.
AMOUNT_COLUMNS = [
	("quote_override", "Supplier quote"),
	("material_cost", "Material"),
	("labour_rate", "Hourly rate"),
	("labour_cost", "Labour"),
	("direct_cost", "Direct cost"),
]

BUILD_UP = [
	("catalog_material", "Catalogue material"),
	("supplier_material", "Supplier packages"),
	("labour", "Installation labour"),
	("small_material", "Small material"),
	("supplier_contingency", "Supplier package contingency"),
	("project_costs", "Project costs (engineering, commissioning, hygiene, documentation)"),
	("direct_cost", "Direct cost"),
	("transport_equipment", "Transport and equipment"),
	("overhead", "Overhead"),
	("cost_baseline", "Cost baseline"),
]


def raw(value) -> str:
	"""Dot-decimal number for spreadsheets; empty when there is no value."""
	return "" if value is None else f"{float(value):.2f}"


def build_csv(
	doc, summary: dict, ui_locale: str | None, now, translate=None, family_labels: dict | None = None
) -> tuple[str, str]:
	"""(filename, csv text with BOM). `doc` is the Tender, `summary` get_tender_summary(),
	`family_labels` the Product Family labels by code."""
	loc = Localizer(ui_locale, translate, family_labels)

	def h(label):
		return loc.t(label, CTX_EXPORT)

	raw_suffix = h("number, CHF")
	buf = io.StringIO()
	w = csv.writer(buf, delimiter=";")
	w.writerow([h("First price"), doc.project_name, h("As of"), loc.datetime(now), loc.ui])
	w.writerow([])

	header = [h(label) for _, label in TEXT_COLUMNS]
	for _, label in AMOUNT_COLUMNS:
		header += [h(label), f"{h(label)} ({raw_suffix})"]
	# Project-specific columns: every printed attribute label in this tender, as printed.
	custom_keys = []
	for i in doc.items:
		for key in _args(i.custom_attributes):
			if key not in custom_keys:
				custom_keys.append(key)
	header += custom_keys
	w.writerow(header)

	for i in doc.items:
		priced = i.status in PRICED_STATUSES
		row = []
		for field, _ in TEXT_COLUMNS:
			if field == "status":
				row.append(loc.status(i.status))
			elif field == "unit":
				row.append(loc.unit(i.unit))
			elif field == "reason":
				row.append(loc.reason(i.reason_code, _args(i.reason_args)) or (i.status_reason or ""))
			elif field == "price_source":
				row.append(loc.price_source(i.price_source))
			elif field == "quantity":
				row.append("" if i.quantity is None else loc.number(i.quantity))
			else:
				value = i.get(field)
				row.append("" if value is None else value)
		for field, _ in AMOUNT_COLUMNS:
			if field == "quote_override":
				value = i.quote_override or None  # no quote entered: empty, not a price
				row += [loc.chf(value) if value else "", raw(value)]
			elif priced:
				row += [loc.chf(i.get(field)), raw(i.get(field))]
			else:
				row += [loc.chf(None), ""]  # "—": no price until reviewed
		custom = _args(i.custom_attributes)
		row += [custom.get(key, "") for key in custom_keys]
		w.writerow(row)

	w.writerow([])
	w.writerow([h("Cost build-up"), h("Amount"), f"{h('Amount')} ({raw_suffix})"])
	for key, label in BUILD_UP:
		value = summary["build_up"][key]
		w.writerow([h(label), loc.chf(value), raw(value)])
	w.writerow([h("Positions without a price"), summary["totals"]["unresolved_count"]])

	w.writerow([])
	w.writerow(
		[
			h("Scenario"),
			h("Bid price"),
			f"{h('Bid price')} ({raw_suffix})",
			h("Margin"),
			h("Win probability"),
			h("Contribution if won"),
			h("Expected contribution"),
			f"{h('Expected contribution')} ({raw_suffix})",
			h("Recommended"),
		]
	)
	for sc in summary["bid_range"]:
		w.writerow(
			[
				loc.scenario(sc["scenario"]),
				loc.chf(sc["bid_price_chf"]),
				raw(sc["bid_price_chf"]),
				loc.percent(sc["margin_pct"] / 100),
				loc.percent(sc["estimated_win_probability"]),
				loc.chf(sc["contribution_if_won_chf"]),
				loc.chf(sc["expected_contribution_chf"]),
				raw(sc["expected_contribution_chf"]),
				h("yes") if sc["recommended"] else "",
			]
		)
	ip = summary["indicative_price"]
	w.writerow(
		[
			h("Standard offer (target margin)"),
			loc.chf(ip["bid_price_chf"]),
			raw(ip["bid_price_chf"]),
			loc.percent(ip["margin_pct"] / 100),
		]
	)
	chosen = summary.get("selected_bid")
	if chosen:
		w.writerow(
			[
				h("Selected bid"),
				loc.chf(chosen["bid_price_chf"]),
				raw(chosen["bid_price_chf"]),
				loc.percent(chosen["margin_pct"] / 100),
				_selection_text(chosen, loc, h),
			]
		)
	else:
		w.writerow([h("Selected bid"), h("not selected yet")])
	w.writerow(
		[h("Win probability is a model estimate from the project parameters, not calibrated on past bids.")]
	)

	safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in doc.project_name)[:60]
	prefix = "".join(ch if ch.isalnum() else "_" for ch in h("First price"))
	return f"{prefix}_{safe}_{now:%Y-%m-%d}_{loc.ui}.csv", "﻿" + buf.getvalue()


# Positions sheet, in order: (field, header, kind). kind: text, int, qty, chf, hours.
XLSX_COLUMNS = [
	("position_id", "LV ID", "text"),
	("golden_lv_id", "Reference LV", "text"),
	("system", "System", "text"),
	("source_page", "Page", "int"),
	("description", "Description", "text"),
	("quantity", "Quantity", "qty"),
	("unit", "Unit", "text"),
	("matched_product", "Product", "text"),
	("product_description", "Catalogue description", "text"),
	("matched_by", "Matched by", "text"),
	("status", "Status", "text"),
	("reason", "Reason", "text"),
	("price_source", "Price source", "text"),
	("quote_override", "Supplier quote", "chf"),
	("material_cost", "Material", "chf"),
	("labour_hours", "Labour hours", "hours"),
	("labour_rate", "Hourly rate", "chf"),
	("labour_cost", "Labour", "chf"),
	("direct_cost", "Direct cost", "chf"),
]
# Who mapped the position to the catalogue (Tender Item attributes.matched_by).
MATCHED_BY = {"rules": "Rules", "llm": "LLM", "llm+rules": "LLM and rules"}
CHF_FORMAT = "#,##0.00"
NUMBER_FORMATS = {"chf": CHF_FORMAT, "hours": "#,##0.00", "qty": "#,##0.###", "int": "0"}
WIDTHS = {"text": 16, "int": 7, "qty": 10, "chf": 14, "hours": 11}
WIDE = {"description": 60, "reason": 50, "product_description": 40, "system": 28}


def build_xlsx(
	doc,
	summary: dict,
	ui_locale: str | None,
	now,
	translate=None,
	family_labels: dict | None = None,
	catalog: dict | None = None,
) -> tuple[str, bytes]:
	"""(filename, workbook bytes). `catalog`: catalogue descriptions by product_id."""
	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Font, PatternFill
	from openpyxl.utils import get_column_letter

	loc = Localizer(ui_locale, translate, family_labels)
	catalog = catalog or {}

	def h(label):
		return loc.t(label, CTX_EXPORT)

	bold = Font(bold=True)
	head_fill = PatternFill("solid", fgColor="DDE4EE")

	def header_row(ws, row: int, labels: list[str]):
		for col, label in enumerate(labels, start=1):
			cell = ws.cell(row=row, column=col, value=label)
			cell.font, cell.fill = bold, head_fill
			cell.alignment = Alignment(vertical="top", wrap_text=True)

	def money(ws, row: int, col: int, value, fmt=CHF_FORMAT):
		cell = ws.cell(row=row, column=col, value=MISSING if value is None else float(value))
		if value is None:
			cell.alignment = Alignment(horizontal="right")
		else:
			cell.number_format = fmt
		return cell

	wb = Workbook()
	chosen = summary.get("selected_bid")

	# Positions: one row per tender position, plus every printed attribute label of the tender.
	ws = wb.active
	ws.title = _sheet(h("Positions"))
	ws.append([h("First price"), doc.project_name])
	ws.append([h("As of"), loc.datetime(now)])
	ws["A1"].font = Font(bold=True, size=13)
	custom_keys = []
	for i in doc.items:
		for key in _args(i.custom_attributes):
			if key not in custom_keys:
				custom_keys.append(key)
	top = 4
	header_row(ws, top, [h(label) for _, label, _ in XLSX_COLUMNS] + custom_keys)
	for r, i in enumerate(doc.items, start=top + 1):
		priced = i.status in PRICED_STATUSES
		attrs = _args(i.attributes)
		for c, (field, _, kind) in enumerate(XLSX_COLUMNS, start=1):
			if kind in ("chf", "hours"):
				value = i.get(field)
				if field == "quote_override":
					value = value or None
					if value is None:
						continue  # no quote entered: empty, not a price
				elif not priced:
					value = None  # "—": no price until reviewed
				money(ws, r, c, value, NUMBER_FORMATS[kind])
				continue
			if field == "status":
				value = loc.status(i.status)
			elif field == "unit":
				value = loc.unit(i.unit)
			elif field == "reason":
				value = loc.reason(i.reason_code, _args(i.reason_args)) or (i.status_reason or "")
			elif field == "price_source":
				value = loc.price_source(i.price_source)
			elif field == "product_description":
				value = catalog.get(i.matched_product, "") if i.matched_product else ""
			elif field == "matched_by":
				value = h(MATCHED_BY.get(attrs.get("matched_by") or attrs.get("classified_by"), "Rules"))
			else:
				value = i.get(field)
			cell = ws.cell(row=r, column=c, value=value)
			if kind in NUMBER_FORMATS and value is not None:
				cell.number_format = NUMBER_FORMATS[kind]
		custom = _args(i.custom_attributes)
		for c, key in enumerate(custom_keys, start=len(XLSX_COLUMNS) + 1):
			ws.cell(row=r, column=c, value=custom.get(key))
	last = top + len(doc.items)
	total_row = last + 1
	ws.cell(row=total_row, column=1, value=h("Total")).font = bold
	for c, (field, _, kind) in enumerate(XLSX_COLUMNS, start=1):
		if field in ("material_cost", "labour_hours", "labour_cost", "direct_cost"):
			letter = get_column_letter(c)
			cell = ws.cell(row=total_row, column=c, value=f"=SUM({letter}{top + 1}:{letter}{last})")
			cell.number_format, cell.font = NUMBER_FORMATS[kind], bold
	for c, (field, _, kind) in enumerate(XLSX_COLUMNS, start=1):
		ws.column_dimensions[get_column_letter(c)].width = WIDE.get(field, WIDTHS[kind])
	for c in range(len(XLSX_COLUMNS) + 1, len(XLSX_COLUMNS) + len(custom_keys) + 1):
		ws.column_dimensions[get_column_letter(c)].width = 14
	ws.freeze_panes = ws.cell(row=top + 1, column=2)
	ws.auto_filter.ref = f"A{top}:{get_column_letter(len(XLSX_COLUMNS) + len(custom_keys))}{last}"

	# Summary: cost build-up, confirmed / provisional / unpriced, totals per system.
	ws = wb.create_sheet(_sheet(h("Summary")))
	ws.append([h("First price"), doc.project_name])
	ws["A1"].font = Font(bold=True, size=13)
	ws.append([h("As of"), loc.datetime(now)])
	ws.append([])
	header_row(ws, 4, [h("Cost build-up"), h("Amount")])
	row = 5
	for key, label in BUILD_UP:
		ws.cell(row=row, column=1, value=h(label))
		cell = money(ws, row, 2, summary["build_up"][key])
		if key in ("direct_cost", "cost_baseline"):
			ws.cell(row=row, column=1).font = cell.font = bold
		row += 1
	ws.cell(row=row, column=1, value=h("Selected bid")).font = bold
	if chosen:
		cell = money(ws, row, 2, chosen["bid_price_chf"])
		cell.font = bold
		ws.cell(row=row, column=3, value=_selection_text(chosen, loc, h))
	else:
		ws.cell(row=row, column=2, value=h("not selected yet"))
	row += 2
	totals = summary["totals"]
	for label, value in (
		(h("Confirmed (calculated)"), totals["confirmed_cost"]),
		(h("Provisional (assumption or supplier package)"), totals["provisional_cost"]),
	):
		ws.cell(row=row, column=1, value=label)
		money(ws, row, 2, value)
		row += 1
	ws.cell(row=row, column=1, value=h("Positions without a price"))
	ws.cell(row=row, column=2, value=totals["unresolved_count"])
	row += 2
	header_row(ws, row, [h("System"), h("Positions"), h("Direct cost")])
	for system, bucket in sorted(summary["by_system"].items()):
		row += 1
		ws.cell(row=row, column=1, value=system)
		ws.cell(row=row, column=2, value=bucket["positions"])
		money(ws, row, 3, bucket["direct_cost"])
	ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 60, 16
	ws.column_dimensions["C"].width = 16

	# Bid range: the three scenarios and the standard offer.
	ws = wb.create_sheet(_sheet(h("Bid range")))
	header_row(
		ws,
		1,
		[
			h("Scenario"),
			h("Bid price"),
			h("Margin"),
			h("Win probability"),
			h("Contribution if won"),
			h("Expected contribution"),
			h("Recommended"),
			h("Selected"),
		],
	)
	rows = list(summary["bid_range"])
	if chosen and chosen["scenario"] == "custom":
		rows.append({**chosen, "recommended": False, "selected": True})
	for row, sc in enumerate(rows, start=2):
		ws.cell(row=row, column=1, value=loc.scenario(sc["scenario"]))
		money(ws, row, 2, sc["bid_price_chf"])
		ws.cell(row=row, column=3, value=sc["margin_pct"] / 100).number_format = "0.0%"
		ws.cell(row=row, column=4, value=sc["estimated_win_probability"]).number_format = "0.0%"
		money(ws, row, 5, sc["contribution_if_won_chf"])
		money(ws, row, 6, sc["expected_contribution_chf"])
		ws.cell(row=row, column=7, value=h("yes") if sc["recommended"] else "")
		ws.cell(row=row, column=8, value=h("yes") if sc.get("selected") else "")
		if sc.get("selected"):
			for c in range(1, 9):
				ws.cell(row=row, column=c).font = bold
				ws.cell(row=row, column=c).fill = PatternFill("solid", fgColor="E3F1E4")
	row = len(rows) + 3
	ip = summary["indicative_price"]
	ws.cell(row=row, column=1, value=h("Standard offer (target margin)"))
	money(ws, row, 2, ip["bid_price_chf"])
	ws.cell(row=row, column=3, value=ip["margin_pct"] / 100).number_format = "0.0%"
	ws.cell(
		row=row + 2,
		column=1,
		value=h(
			"Win probability is a model estimate from the project parameters, not calibrated on past bids."
		),
	)
	for c, width in zip("ABCDEFGH", (30, 16, 10, 16, 20, 22, 14, 14), strict=True):
		ws.column_dimensions[c].width = width

	# Open points: everything the estimator still has to confirm, with the PDF page.
	ws = wb.create_sheet(_sheet(h("Open points")))
	header_row(
		ws, 1, [h("LV ID"), h("Page"), h("Description"), h("Quantity"), h("Unit"), h("Status"), h("Reason")]
	)
	row = 1
	for i in doc.items:
		if i.status == "calculated" or i.status in ("out_of_scope", "non_priceable"):
			continue
		row += 1
		ws.append(
			[
				i.position_id,
				i.source_page,
				i.description,
				i.quantity,
				loc.unit(i.unit),
				loc.status(i.status),
				loc.reason(i.reason_code, _args(i.reason_args)) or (i.status_reason or ""),
			]
		)
	for c, width in zip("ABCDEFG", (12, 7, 60, 10, 8, 24, 60), strict=True):
		ws.column_dimensions[c].width = width
	ws.freeze_panes = "A2"
	ws.auto_filter.ref = f"A1:G{max(row, 2)}"

	# Assumptions: the parameters the price was computed with (keys as stored).
	ws = wb.create_sheet(_sheet(h("Assumptions")))
	header_row(ws, 1, [h("Parameter"), h("Value")])
	for key, value in _flatten({"parameters": summary["parameters"], "bid": summary["assumptions"]}):
		ws.append([key, value])
	ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 50, 20

	buf = io.BytesIO()
	wb.save(buf)
	safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in doc.project_name)[:60]
	prefix = "".join(ch if ch.isalnum() else "_" for ch in h("First price"))
	return f"{prefix}_{safe}_{now:%Y-%m-%d}_{loc.ui}.xlsx", buf.getvalue()


def _selection_text(chosen: dict, loc, h) -> str:
	"""What was chosen, e.g. "Target margin" or "Own offer: fixed price" (plus a warning)."""
	text = loc.scenario(chosen["scenario"])
	if chosen["scenario"] == "custom":
		text += ": " + (h("fixed price") if "price_chf" in chosen["input"] else h("own margin"))
	if chosen.get("below_baseline"):
		text += " · " + h("below the cost baseline")
	return text


def _sheet(name: str) -> str:
	"""Excel sheet names: at most 31 characters, none of []:*?/\\."""
	return "".join(ch for ch in name if ch not in "[]:*?/\\")[:31]


def _flatten(value, prefix: str = ""):
	if isinstance(value, dict):
		for k, v in value.items():
			yield from _flatten(v, f"{prefix}.{k}" if prefix else str(k))
	elif isinstance(value, list | tuple):
		yield prefix, ", ".join(str(v) for v in value)
	else:
		yield prefix, value


def _args(value):
	if not value:
		return {}
	if isinstance(value, str):
		import json

		return json.loads(value)
	return value
