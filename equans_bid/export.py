"""Priced-offer CSV in the estimator's locale.

Every amount appears twice: formatted for the locale (babel) and as a raw dot-decimal number,
so the file reads well and still calculates in Excel whatever its regional settings. A position
without a price shows "—" (formatted) and an empty raw cell, never 0. Tender text is copied
as extracted, untranslated.
"""

import csv
import io

from equans_bid.localization import CTX_EXPORT, Localizer

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
	w.writerow(
		[h("Win probability is a model estimate from the project parameters, not calibrated on past bids.")]
	)

	safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in doc.project_name)[:60]
	prefix = "".join(ch if ch.isalnum() else "_" for ch in h("First price"))
	return f"{prefix}_{safe}_{now:%Y-%m-%d}_{loc.ui}.csv", "﻿" + buf.getvalue()


def _args(value):
	if not value:
		return {}
	if isinstance(value, str):
		import json

		return json.loads(value)
	return value
