"""Load trades, product families, catalogue and productivity rules from data/trades/ into Frappe.

Idempotent upserts keyed by their natural codes (trade_code, family_code, product_id,
install_code): re-running updates, never duplicates. Used by `commands.seed_data`, the
migration patches and `after_install`.
"""

import json

import frappe

from equans_bid.extraction.attributes import catalog_attributes
from equans_bid.trades import available_trades, catalog_family, load_trade, read_catalog, read_productivity

ROLES = ("Estimator", "Catalogue Manager")


def ensure_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def _upsert(doctype, name, values) -> str:
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		before = doc.as_dict(no_default_fields=True)
		doc.update(values)
		if doc.as_dict(no_default_fields=True) == before:
			return "unchanged"
		doc.save(ignore_permissions=True)
		return "updated"
	frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
	return "created"


def _js(value):
	return json.dumps(value, ensure_ascii=False) if value is not None else None


def sync_trade(code: str) -> dict:
	"""Trade + its Product Families from data/trades/<code>/."""
	trade = load_trade(code)
	counts = {
		"trade": _upsert(
			"Trade",
			trade.code,
			{
				"trade_code": trade.code,
				"labels": _js(trade.labels),
				"system_header_pattern": trade.system_header_pattern,
				"continuation_labels": _js(trade.continuation_labels),
				"attribute_labels": _js(trade.attribute_labels),
				"attribute_rules": _js(trade.attribute_rules),
				"catalog_attribute_rules": _js(trade.catalog_attribute_rules),
				"table_parsers": _js(trade.table_parsers),
				"factor_rules": _js(trade.factor_rules),
			},
		)
	}
	for fam in trade.families:
		result = _upsert(
			"Product Family",
			fam.code,
			{
				"family_code": fam.code,
				"trade": trade.code,
				"priority": fam.priority,
				"labels": _js(fam.labels),
				"key_attributes": _js(fam.key_attributes),
				"soft_attributes": _js(fam.soft_attributes),
				"size_strategy": fam.size_strategy,
				"catalog_match": _js(fam.catalog_match),
				"patterns": [{"pattern": p} for p in fam.patterns],
			},
		)
		counts[result] = counts.get(result, 0) + 1
	return counts


def sync_productivity(code: str) -> int:
	trade = load_trade(code)
	if not trade.productivity_file:
		return 0
	rows = read_productivity(trade)
	for r in rows:
		_upsert(
			"Productivity Rule",
			r["install_code"],
			{
				"install_code": r["install_code"],
				"work_type": r["work_type"],
				"unit": r["unit"],
				"base_hours_per_unit": float(r["base_hours_per_unit"]),
				"labour_role": r["labour_role"],
				"default_hourly_rate_chf": float(r["default_hourly_rate_chf"]),
				"factor_keys": r["factor_keys"],
				"trade": trade.code,
			},
		)
	return len(rows)


def sync_catalog(code: str, price_version: str | None = None) -> dict:
	"""Upsert the trade's catalogue; family and normalised attributes come from the CSV columns
	when present, else from the trade's catalog_match / catalog_attribute_rules."""
	trade = load_trade(code)
	if not trade.catalog_file:
		return {}
	counts: dict = {}
	for r in read_catalog(trade):
		values = {
			"product_id": r["product_id"],
			"category": r.get("category"),
			"subcategory": r.get("subcategory"),
			"manufacturer": r.get("manufacturer"),
			"model": r.get("model"),
			"description": r["description"],
			"unit": r["unit"],
			"list_price_chf": float(r.get("list_price_chf") or 0),
			"discount_pct": float(r.get("discount_pct") or 0),
			"net_cost_chf": float(r["net_cost_chf"]),
			"install_code": r["install_code"],
			"source_type": r.get("source_type") or "catalog",
			"supplier_quote_required": 1 if r["supplier_quote_required"] else 0,
			"trade": trade.code,
			"family": catalog_family(r, trade),
			"attributes": _js(catalog_attributes(r, trade)),
		}
		if price_version:
			values["price_version"] = price_version
		result = _upsert("Catalog Item", r["product_id"], values)
		counts[result] = counts.get(result, 0) + 1
	return counts


def sync_all(price_version: str | None = None) -> dict:
	ensure_roles()
	report = {}
	for folder in available_trades():
		code = load_trade(folder).code
		report[code] = {
			"families": sync_trade(folder),
			"productivity": sync_productivity(folder),
			"catalog": sync_catalog(folder, price_version),
		}
	return report
