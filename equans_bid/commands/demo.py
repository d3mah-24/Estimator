"""Demo hardening: one command to a clean demo state, one to check it before going on stage.

bench --site equans.localhost execute equans_bid.commands.demo.reset
bench --site equans.localhost execute equans_bid.commands.demo.smoke
"""

import json
from pathlib import Path

import frappe

from equans_bid.commands import seed_data, seed_demo

APP = Path(__file__).resolve().parent.parent
GOLDEN = APP / "data" / "starter" / "expected_output_example.json"


def reset():
	"""Reseed reference data and reprocess the demo tender: no quotes, no custom assumptions."""
	seed_data.run()
	name = seed_demo.run()
	frappe.db.set_value("Tender", name, "bid_assumptions", None)
	frappe.db.commit()
	print(f"Demo ready: /estimator/tender/{name}")
	smoke()


def _check(results: list, label: str, ok: bool, detail: str = "", fix: str = ""):
	"""`detail` is always shown; `fix` only when the check fails."""
	results.append(ok)
	note = ", ".join(x for x in (detail, "" if ok else fix) if x)
	print(f"{'OK  ' if ok else 'FAIL'} {label}{f' — {note}' if note else ''}")


def smoke():
	"""Everything the live demo depends on. Prints OK/FAIL per check."""
	r: list[bool] = []
	from equans_bid.trades import (
		available_trades,
		load_trade,
		read_catalog,
		read_productivity,
	)

	for folder in available_trades():
		trade = load_trade(folder)
		want_items, want_rules = len(read_catalog(trade)), len(read_productivity(trade))
		items = frappe.db.count("Catalog Item", {"trade": trade.code})
		rules = frappe.db.count("Productivity Rule", {"trade": trade.code})
		_check(
			r,
			f"{trade.code}: catalogue and rules loaded",
			(items, rules) == (want_items, want_rules),
			f"{items}/{want_items} items, {rules}/{want_rules} rules",
			fix="run commands.seed_data.run",
		)
	_check(
		r,
		"Project parameters loaded",
		bool(frappe.get_single("Project Parameter").parameters),
	)

	name = frappe.db.get_value("Tender", {"project_name": seed_demo.DEMO_NAME})
	_check(r, "Demo tender exists", bool(name), name or "", fix="run demo.reset")
	if name:
		doc = frappe.get_doc("Tender", name)
		_check(
			r,
			"Demo tender processed",
			doc.status == "Completed",
			f"{doc.status}, {len(doc.items)} positions",
		)
		path = None
		if doc.tender_file:
			path = Path(frappe.get_doc("File", {"file_url": doc.tender_file}).get_full_path())
		_check(
			r,
			"Tender PDF attached and readable",
			bool(path and path.exists()),
			doc.tender_file or "missing",
		)

		golden = {p["lv_id"]: p for p in json.loads(GOLDEN.read_text())["position_results"]}
		rows = {i.golden_lv_id: i for i in doc.items if i.golden_lv_id}
		_check(
			r,
			"All 22 reference positions found",
			len(rows) == len(golden),
			f"{len(rows)}/{len(golden)}",
		)
		lv1 = rows.get("LV0001")
		_check(
			r,
			"LV0001 = 806.26 CHF",
			bool(lv1 and abs(lv1.direct_cost - 806.26) < 0.005),
			lv1 and f"{lv1.direct_cost}",
		)
		off = [
			k
			for k, g in golden.items()
			if k in rows and abs(rows[k].direct_cost - g["direct_position_cost_chf"]) > 0.01
		]
		_check(
			r,
			"Reference positions match the golden costs",
			not off,
			", ".join(off) or "22/22",
		)
		quotes = [i.position_id for i in doc.items if i.quote_override]
		_check(r, "No leftover supplier quotes", not quotes, ", ".join(quotes[:5]))
		_check(r, "Default bid assumptions", not doc.bid_assumptions)

	www = APP / "www" / "estimator.html"
	_check(
		r,
		"Frontend built",
		www.exists() and (APP / "public" / "frontend" / "index.html").exists(),
		fix="cd frontend && yarn build",
	)
	_check(
		r,
		"CSRF protection on",
		not frappe.conf.get("ignore_csrf"),
		fix="ignore_csrf is set; use it only with yarn dev",
	)
	from frappe.gettext.translate import get_mo_path

	missing_mo = [lang for lang in ("de", "fr") if not get_mo_path("equans_bid", lang).exists()]
	_check(
		r,
		"Translations compiled (de, fr)",
		not missing_mo,
		", ".join(missing_mo),
		fix="bench compile-po-to-mo --app equans_bid",
	)
	try:
		from frappe.utils.background_jobs import get_workers

		workers = len(get_workers())
	except Exception:
		workers = 0
	_check(
		r,
		"Background worker running (uploads)",
		workers > 0,
		f"{workers} worker(s)",
		fix="start with bench start",
	)
	print(f"\n{sum(r)}/{len(r)} checks passed" + ("" if all(r) else " — fix the FAIL lines before the demo"))
	return all(r)
