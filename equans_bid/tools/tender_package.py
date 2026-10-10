"""Generate a complete, SYNTHETIC tender package in the format of the Equans starter package.

	cd frappe-bench
	env/bin/python -m equans_bid.tools.tender_package <scenario.json> <output folder>

A scenario (JSON) describes the project, its systems and positions; the generator writes

	<pdf_name>                     the tender, laid out like a Swiss LV (header "… Seite n / m",
	                               quantity column, source-document footer)
	catalog.csv, productivity.csv  copied from the trade data (default: the Equans starter files)
	project_parameters.json        the starter parameters with this project's id, name and file
	example_lv_positions.csv       the verified rows, with the source page from the layout
	expected_output_example.json   golden results computed by equans_bid.pricing (same schema)
	README.md, manifest.json       what the package is, and how to rebuild it (hashes)

Golden numbers come from our own engine, so a package is a regression test for extraction,
matching and pricing — not independent ground truth. Everything is labelled synthetic.
"""

import csv
import hashlib
import html
import json
import shutil
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from equans_bid.extraction.pipeline import STARTER
from equans_bid.pricing.engine import apply_factor_rules, money, price_position
from equans_bid.pricing.project import bid_range, subset_baseline
from equans_bid.trades import load_trade, read_catalog, read_productivity

GENERATOR_VERSION = "1"
UNIT_PRINT = {"pc": "Stk", "m": "m", "m2": "m2", "m3": "m3", "h": "Std", "LS": "psch"}
ROWS_PER_PAGE = 32  # fits one A4 page at 9.5 pt; checked after rendering (check_layout)
GOLDEN_FIELDS = [
	"lv_id",
	"system",
	"source_page",
	"category",
	"description",
	"quantity",
	"unit",
	"manufacturer_hint",
	"model_hint",
	"expected_install_code",
	"suggested_product_id",
	"ground_truth_status",
]


def _qty_text(q) -> str:
	return f"{q:g}"


def layout(scenario: dict) -> list[dict]:
	"""Pages of rows. A position block is never split across pages; each system starts a page.
	Every row: {"text", "unit", "qty", "variant"}; variant rows carry the golden metadata."""
	pages = []
	for system in scenario["systems"]:
		sys_pages = [[]]
		for block in system["positions"]:
			rows = [{"text": t} for t in block.get("lines", [])]
			for v in block["variants"]:
				rows.append(
					{
						"text": v.get("label", ""),
						"unit": UNIT_PRINT[v["unit"]],
						"qty": _qty_text(v["quantity"]),
						"variant": v,
					}
				)
			if len(sys_pages[-1]) + len(rows) > ROWS_PER_PAGE:
				sys_pages.append([])
			sys_pages[-1].extend(rows)
		for table in system.get("component_lists", []):
			sys_pages.append(
				[{"text": "Bauteilliste Lüftung", "raw": True}, *({"text": l, "raw": True} for l in table)]
			)
		for i, rows in enumerate(sys_pages):
			pages.append({"system": system, "index": i + 1, "count": len(sys_pages), "rows": rows})
	for n, page in enumerate(pages, start=1):
		page["number"] = n
		for row in page["rows"]:
			if "variant" in row:
				row["variant"]["_page"] = n
	return pages


def render_pdf(scenario: dict, pages: list[dict], path: Path):
	from weasyprint import HTML

	project = html.escape(scenario["project"]["short_name"])
	parts = []
	for p in pages:
		s = p["system"]
		title = f"{s['code']} {s['la']} {s['name']}"
		if p["rows"] and p["rows"][0].get("raw"):  # CAD component list: no LV header, plain lines
			body = "".join(f"<p class='r'>{html.escape(r['text'])}</p>" for r in p["rows"])
			parts.append(
				f"<section>{body}<p class='f'>\\\\server\\CAD\\{project} {p['index']} / {p['count']}</p></section>"
			)
			continue
		rows = "".join(
			f"<tr><td class='d'>{html.escape(r['text'])}</td><td class='u'>{r.get('unit', '')}</td>"
			f"<td class='q'>{r.get('qty', '')}</td></tr>"
			for r in p["rows"]
		)
		parts.append(
			f"<section><p class='h'>SH {project} (SYNTHETIC) {html.escape(title)} Seite {p['index']} / {p['count']}</p>"
			"<p class='h'>Pos. Gegenstand Mass- Mass- Einheits- Betrag</p><p class='h'>Gattg. betrag Preis Fr.</p>"
			f"<table>{rows}</table>"
			f"<p class='f'>H:\\Projekt\\{project}\\02 L\\{html.escape(title)}.docx {scenario['project']['date']}</p></section>"
		)
	css = """
	@page { size: A4; margin: 16mm }
	body { font-family: sans-serif; font-size: 9.5pt }
	section { page-break-after: always; position: relative; height: 262mm }
	table { width: 100%; border-collapse: collapse; margin-top: 4mm }
	td { padding: 0.9mm 0; white-space: nowrap; overflow: hidden }
	td.d { width: 74% } td.u { width: 10% } td.q { width: 16% }
	p { margin: 0 0 1mm 0 } p.r { white-space: pre }
	p.f { position: absolute; bottom: 0; font-size: 7.5pt }
	"""
	HTML(string=f"<html><head><style>{css}</style></head><body>{''.join(parts)}</body></html>").write_pdf(
		path
	)


def check_layout(pdf: Path, pages: list[dict]):
	"""The rendered PDF must have exactly the planned pages, each starting with its own header,
	or the source pages written to the verified rows would be wrong."""
	from equans_bid.extraction.pdf_text import read_pages

	rendered = read_pages(pdf)
	if len(rendered) != len(pages):
		raise RuntimeError(f"{pdf.name}: rendered {len(rendered)} pages, layout planned {len(pages)}")
	for plan, page in zip(pages, rendered, strict=True):
		if plan["rows"] and plan["rows"][0].get("raw"):
			ok = page.text.lstrip().startswith(plan["rows"][0]["text"])
		else:
			ok = f"Seite {plan['index']} / {plan['count']}" in page.text.splitlines()[0]
		if not ok:
			raise RuntimeError(f"{pdf.name}: page {plan['number']} does not start as planned")


def golden_rows(scenario: dict, catalog: dict) -> list[dict]:
	rows, n = [], 0
	for system in scenario["systems"]:
		sys_name = f"{system['code']} {system['la']} {system['name']}"
		for block in system["positions"]:
			for v in block["variants"]:
				if not v.get("golden"):
					continue
				n += 1
				product = catalog[v["product_id"]]
				rows.append(
					{
						"lv_id": f"LV{n:04d}",
						"system": sys_name,
						"source_page": v["_page"],
						"category": product["category"],
						"description": v["golden"]["description"],
						"quantity": _qty_text(v["quantity"]),
						"unit": v["unit"],
						"manufacturer_hint": v["golden"].get("manufacturer_hint", ""),
						"model_hint": v["golden"].get("model_hint", ""),
						"expected_install_code": product["install_code"],
						"suggested_product_id": v["product_id"],
						"ground_truth_status": "supplier_quote_required"
						if product["supplier_quote_required"]
						else "calculated",
					}
				)
	return rows


def expected_output(
	rows: list[dict], catalog: dict, rules: dict, params: dict, factor_rules: list, pdf_name: str
) -> dict:
	results, material, labour = [], Decimal(0), Decimal(0)
	for g in rows:
		product, rule = (
			catalog[g["suggested_product_id"]],
			rules[catalog[g["suggested_product_id"]]["install_code"]],
		)
		keys = apply_factor_rules(rule["factor_keys"], {"system": g["system"]}, factor_rules)
		cost = price_position(
			float(g["quantity"]),
			product["net_cost_chf"],
			rule["base_hours_per_unit"],
			rule["default_hourly_rate_chf"],
			keys,
			params,
		)
		material += cost.material_cost
		labour += cost.labour_cost
		results.append(
			{
				"lv_id": g["lv_id"],
				"source_page": g["source_page"],
				"matched_product_id": g["suggested_product_id"],
				"install_code": product["install_code"],
				"quantity": float(g["quantity"]),
				"unit": g["unit"],
				"net_unit_cost_chf": float(product["net_cost_chf"]),
				"material_cost_chf": float(cost.material_cost),
				"adjusted_install_hours": float(money(cost.labour_hours)),
				"labour_cost_chf": float(cost.labour_cost),
				"direct_position_cost_chf": float(cost.direct_cost),
				"price_source": product["source_type"],
				"match_confidence": 0.92,
				"review_required": False,
				"status": g["ground_truth_status"],
			}
		)
	direct = material + labour
	baseline = subset_baseline(direct, params)
	keep = (
		"scenario",
		"bid_price_chf",
		"margin_pct",
		"estimated_win_probability",
		"expected_contribution_chf",
	)
	return {
		"schema_version": "2.0",
		"scope": "Verified example subset of a SYNTHETIC tender; golden values computed by equans_bid.pricing.",
		"source_tender_file": pdf_name,
		"position_results": results,
		"example_subset_summary": {
			"material_cost_chf": float(money(material)),
			"labour_cost_chf": float(money(labour)),
			"direct_cost_chf": float(money(direct)),
			"cost_baseline_chf": float(baseline),
		},
		"recommended_bid_range": {
			"scenarios": [{k: s[k] for k in keep} for s in bid_range(baseline, params)],
			"selection_logic": "Compare bid price, margin, estimated win probability and expected contribution.",
		},
	}


def _sha(path: Path) -> str:
	return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(scenario_path: Path, out_dir: Path) -> dict:
	scenario = json.loads(Path(scenario_path).read_text())
	trade = load_trade(scenario.get("trade", "HVAC"))
	out = Path(out_dir)
	out.mkdir(parents=True, exist_ok=True)

	catalog = {r["product_id"]: r for r in read_catalog(trade)}
	rules = {r["install_code"]: r for r in read_productivity(trade)}
	for block in (b for s in scenario["systems"] for b in s["positions"]):
		for v in block["variants"]:
			if v.get("product_id") and v["product_id"] not in catalog:
				raise ValueError(f"Unknown product {v['product_id']} in scenario")

	pdf_name = scenario["project"]["pdf_name"]
	pages = layout(scenario)
	render_pdf(scenario, pages, out / pdf_name)
	check_layout(out / pdf_name, pages)

	shutil.copyfile(trade.catalog_file, out / "catalog.csv")
	shutil.copyfile(trade.productivity_file, out / "productivity.csv")
	# Project parameters of the trade's data folder, else the Equans starter parameters.
	own = trade.catalog_file.parent / "project_parameters.json"
	params = json.loads((own if own.exists() else STARTER / "project_parameters.json").read_text())
	params["project"].update(
		{"id": scenario["project"]["id"], "name": scenario["project"]["name"], "source_tender_file": pdf_name}
	)
	(out / "project_parameters.json").write_text(json.dumps(params, indent=2, ensure_ascii=False) + "\n")

	rows = golden_rows(scenario, catalog)
	with open(out / "example_lv_positions.csv", "w", newline="") as fh:
		w = csv.DictWriter(fh, fieldnames=GOLDEN_FIELDS)
		w.writeheader()
		w.writerows(rows)
	expected = expected_output(rows, catalog, rules, params, trade.factor_rules, pdf_name)
	(out / "expected_output_example.json").write_text(
		json.dumps(expected, indent=2, ensure_ascii=False) + "\n"
	)

	first = expected["position_results"][0] if expected["position_results"] else None
	(out / "README.md").write_text(_readme(scenario, len(pages), rows, first, pdf_name))
	files = sorted(p.name for p in out.iterdir() if p.name != "manifest.json")
	manifest = {
		"generator": "equans_bid.tools.tender_package",
		"generator_version": GENERATOR_VERSION,
		"generated_on": date.today().isoformat(),
		"scenario": Path(scenario_path).name,
		"trade": trade.code,
		"synthetic": True,
		"pages": len(pages),
		"lv_positions": sum(len(b["variants"]) for s in scenario["systems"] for b in s["positions"]),
		"component_list_pages": sum(len(s.get("component_lists", [])) for s in scenario["systems"]),
		"golden_positions": len(rows),
		"files": {name: _sha(out / name) for name in files},
	}
	(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
	if Path(scenario_path).resolve() != (out / "scenario.json").resolve():
		shutil.copyfile(scenario_path, out / "scenario.json")
	return manifest


def _readme(scenario: dict, pages: int, rows: list[dict], first: dict | None, pdf_name: str) -> str:
	p = scenario["project"]
	golden = (
		f"Start with `{first['lv_id']}` on PDF page {first['source_page']}: {first['quantity']:g} {first['unit']} "
		f"matched to `{first['matched_product_id']}`, direct cost {first['direct_position_cost_chf']:.2f} CHF."
		if first
		else ""
	)
	return f"""# {p["name"]} — SYNTHETIC tender package

**Synthetic.** Generated by `equans_bid.tools.tender_package` from `scenario.json`. The project,
positions and quantities are invented; catalogue, productivity rules and parameters are the
Equans starter-package files. Golden values are computed by the equans_bid pricing engine, so
this package tests extraction, matching and pricing for consistency — it is not independent
ground truth.

## Files
- `{pdf_name}`: the tender ({pages} pages, Swiss LV layout).
- `catalog.csv`, `productivity.csv`: product catalogue and installation rules.
- `project_parameters.json`: factors, allowances, overhead, margin, bid optimisation.
- `example_lv_positions.csv`: {len(rows)} verified positions with their PDF page.
- `expected_output_example.json`: golden position results, subset baseline, bid range.
- `scenario.json`, `manifest.json`: the input and file hashes; rebuild with
  `env/bin/python -m equans_bid.tools.tender_package scenario.json <folder>`.

## Golden example
{golden}

The tender prints no LV IDs; the `lv_id` values exist only in the CSV, as in the original package.
"""


if __name__ == "__main__":
	if len(sys.argv) != 3:
		sys.exit("usage: python -m equans_bid.tools.tender_package <scenario.json> <output folder>")
	print(json.dumps(generate(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
