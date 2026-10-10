"""Generate tender scenarios automatically from wording templates and the trade's catalogue.

	cd frappe-bench
	env/bin/python -m equans_bid.tools.scenario_generator --seed 7 --out <folder> [--count 5] [--systems 3]

Each seed gives one fictional school tender: systems, positions (catalogue items in the LV
wording of data/scenarios/templates/<trade>.json), sizes and quantities, a few positions with no
catalogue item, and a CAD duct list. The same seed always gives the same scenario. With
`--out`, every scenario is built into a full package (equans_bid.tools.tender_package) and
self-checked: the real pipeline must find and price every verified position, else it fails.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from equans_bid.extraction.attributes import catalog_attributes
from equans_bid.trades import load_trade, read_catalog

TEMPLATES = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "templates"


def _placeholders(product: dict, attrs: dict) -> dict:
	values = {}
	if "dn_mm" in attrs:
		values |= {"dn_mm": attrs["dn_mm"], "dn_cm": f"{attrs['dn_mm'] / 10:g}"}
	if "dims_mm" in attrs:
		dims = attrs["dims_mm"]
		for name, v in zip(("w", "h", "l"), dims, strict=False):
			values |= {f"{name}_mm": v, f"{name}_cm": f"{v / 10:g}"}
	if "thickness_mm" in attrs:
		values["thickness_mm"] = attrs["thickness_mm"]
	return values


def _fmt(text: str, values: dict) -> str:
	return text.format(**values)


class Quantities:
	"""Quantities unique per (system, unit), so no two positions on a page share page+unit+qty."""

	def __init__(self, rng: random.Random):
		self.rng, self.used = rng, set()

	def draw(self, unit: str, lo: int, hi: int) -> int:
		"""A quantity not yet used for this unit; the range widens when it is exhausted."""
		while True:
			free = [q for q in range(lo, hi + 1) if (unit, q) not in self.used]
			if free:
				q = self.rng.choice(free)
				self.used.add((unit, q))
				return q
			hi *= 2


def generate_scenario(seed: int, systems: int = 3, trade_code: str = "HVAC") -> dict:
	rng = random.Random(seed)
	templates = json.loads((TEMPLATES / f"{trade_code.lower()}.json").read_text())
	trade = load_trade(trade_code)
	catalog = {r["product_id"]: r for r in read_catalog(trade)}
	attrs = {pid: catalog_attributes(r, trade) for pid, r in catalog.items()}

	school, town = rng.choice(templates["schools"]), rng.choice(templates["towns"])
	slug = f"{school}_{town}".replace("ü", "ue").replace("ä", "ae").replace("ö", "oe")
	names = rng.sample(templates["systems"], k=min(systems, len(templates["systems"])))
	scenario = {
		"trade": trade_code,
		"generated": {"seed": seed, "systems": systems, "generator": "equans_bid.tools.scenario_generator"},
		"project": {
			"id": f"{slug.upper()}_LUEFTUNG_SYNTH_{seed}",
			"name": f"Primary School {school} {town} - Ventilation (SYNTHETIC, seed {seed})",
			"short_name": f"{school} {town}",
			"pdf_name": f"BKP_{templates['bkp']}_LV_{slug}_SYNTH_{seed}.pdf",
			"date": f"{rng.randint(1, 28):02d}.{rng.randint(1, 12):02d}.2026",
		},
		"systems": [],
	}

	for i, name in enumerate(names, start=1):
		qty = Quantities(rng)
		picks = rng.sample(templates["positions"], k=rng.randint(4, min(7, len(templates["positions"]))))
		positions = []
		for tpl in picks:
			single = any("{" in line for line in tpl["lines"])  # size in the description: one variant
			n_variants = 1 if single else rng.randint(1, len(tpl["products"]))
			products = rng.sample(tpl["products"], k=n_variants)
			first_values = _placeholders(catalog[products[0]], attrs[products[0]])
			lines = [_fmt(line, first_values) for line in tpl["lines"]]
			variants = []
			for j, pid in enumerate(products):
				values = _placeholders(catalog[pid], attrs[pid]) | {
					"pressure": rng.randint(15, 45),
					"row": tpl.get("rows", {}).get(pid, ""),
				}
				label = tpl["label"] if j == 0 or "variant_label" not in tpl else tpl["variant_label"]
				variants.append(
					{
						"label": _fmt(label, values),
						"quantity": qty.draw(tpl["unit"], *tpl["qty"]),
						"unit": tpl["unit"],
						"product_id": pid,
						"golden": {
							"description": _fmt(tpl["golden"]["description"], values),
							**{k: v for k, v in tpl["golden"].items() if k != "description"},
						},
					}
				)
			positions.append({"lines": lines, "variants": variants})
		for tpl in rng.sample(templates["distractors"], k=rng.randint(1, 2)):
			positions.insert(
				rng.randint(0, len(positions)),
				{
					"lines": tpl["lines"],
					"variants": [
						{
							"label": tpl["label"],
							# Not verified rows: no unique quantity needed (the benchmark
							# excludes them by install code).
							"quantity": rng.randint(*tpl["qty"]),
							"unit": tpl["unit"],
						}
					],
				},
			)
		system = {
			"code": f"{templates['bkp']}.{i:02d}",
			"la": f"LA{i:02d}",
			"name": name,
			"positions": positions,
		}
		if rng.random() < 0.6:
			cl = templates["component_list"]
			rows = ["Auflistung der Rohre", "lKZ Bezeichnung dBemerkung"]
			for pid in rng.sample(cl["duct_round"], k=2):
				rows.append(f"{rng.randint(4, 60) * 500}R-R Wickelfalzrohr {attrs[pid]['dn_mm']}")
			rows += ["Auflistung der Formstücke rund", "StkKZ Bezeichnung d1 d2 d3 wBemerkung"]
			for pid in rng.sample(cl["bends"], k=2):
				rows.append(f"{rng.randint(2, 14)}BGE Bogen {attrs[pid]['dn_mm']} {attrs[pid]['angle']}")
			system["component_lists"] = [rows]
		scenario["systems"].append(system)
	return scenario


def build_and_verify(scenario: dict, out_dir: Path) -> dict:
	"""Write the package and check that the app finds and prices every verified position."""
	from equans_bid.extraction.benchmark import validate_extraction_against_benchmark
	from equans_bid.extraction.pipeline import extract_positions, prepare_catalog
	from equans_bid.tools.tender_package import generate

	out_dir.mkdir(parents=True, exist_ok=True)
	scenario_path = out_dir / "scenario.json"
	scenario_path.write_text(json.dumps(scenario, indent=2, ensure_ascii=False) + "\n")
	manifest = generate(scenario_path, out_dir)
	trade = load_trade(scenario["trade"])
	catalog = prepare_catalog(read_catalog(trade), trade)
	positions = extract_positions(out_dir / scenario["project"]["pdf_name"], catalog, trade=trade)
	report = validate_extraction_against_benchmark(
		positions, out_dir / "example_lv_positions.csv", catalog, require_product=True
	)
	if not report.passed:
		problems = [(r.lv_id, r.outcome, r.detail) for r in report.rows if r.outcome != "OK"]
		raise RuntimeError(f"Self-check failed for {out_dir.name}: {problems}")
	manifest["self_check"] = report.summary()
	(out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
	return manifest


def main(argv=None):
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--seed", type=int, default=1)
	ap.add_argument("--count", type=int, default=1, help="number of tenders (seeds seed, seed+1, …)")
	ap.add_argument("--systems", type=int, default=3)
	ap.add_argument("--trade", default="HVAC")
	ap.add_argument("--out", type=Path, help="build full packages here; without it, print the scenario")
	args = ap.parse_args(argv)
	for seed in range(args.seed, args.seed + args.count):
		scenario = generate_scenario(seed, args.systems, args.trade)
		if not args.out:
			print(json.dumps(scenario, indent=2, ensure_ascii=False))
			continue
		folder = args.out / scenario["project"]["pdf_name"].removesuffix(".pdf")
		manifest = build_and_verify(scenario, folder)
		print(
			f"{folder}: {manifest['pages']} pages, {manifest['lv_positions']} positions, {manifest['self_check']}"
		)


if __name__ == "__main__":
	sys.exit(main())
