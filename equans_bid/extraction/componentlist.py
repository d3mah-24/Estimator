"""Parse the CAD component lists ("Bauteilliste Lüftung") that carry the ductwork quantities.

These pages are machine-generated tables, not LV prose. Count / length and the code are glued:
	33860R-R Wickelfalzrohr 100          -> 33,860 mm round duct DN100
	15720L Luftleitung 1100 350          -> 15,720 mm rectangular duct 1100 x 350
	8BGE Bogen 100 90                    -> 8 round bends DN100, 90°
	4BS Bogen symmetrisch 150 500 45     -> 4 rectangular bends

Lines of the same item on one page are summed into one position, so each position still
points at a single source page.
"""

import re
from collections import OrderedDict

ROW = re.compile(
	r"^(?P<count>\d+)(?P<code>[A-Z]{1,3}(?:-[A-Z])?)\s+(?P<name>[^\d]+?)\s+(?P<nums>[\d\s°]+?)\s*(?P<note>[A-Za-zÄÖÜäöü].*)?$"
)
SECTION = re.compile(r"^Auflistung der (?P<section>Rohre|Kanäle|Formstücke rund|Kanalformstücke)")


def is_component_page(text: str) -> bool:
	return text.lstrip().startswith("Bauteilliste")


def parse_component_page(page_number: int, text: str, system: str) -> list[dict]:
	"""Return position dicts with kind, attributes, quantity and unit already set."""
	groups: "OrderedDict[tuple, dict]" = OrderedDict()
	section = None
	for line in (l.strip() for l in text.splitlines()):
		m = SECTION.match(line)
		if m:
			section = m.group("section")
			continue
		m = ROW.match(line)
		if not m or not section:
			continue
		count = int(m.group("count"))
		name = m.group("name").strip()
		nums = [int(n) for n in m.group("nums").replace("°", " ").split()]
		note = (m.group("note") or "").strip()

		if section == "Rohre" and nums:
			key = ("duct_round", nums[0], note)
			label = f"Wickelfalzrohr DN{nums[0]}" + (f" ({note})" if note else "")
			g = groups.setdefault(
				key, _new(page_number, system, "duct_round", {"dn_mm": [nums[0]]}, label, "m")
			)
			g["quantity"] += count / 1000
			g["lines"].append(line)
		elif section == "Kanäle" and len(nums) >= 2:
			a, b = nums[0], nums[1]
			key = ("duct_rect", a, b, note)
			label = f"Luftleitung {a} x {b} mm" + (f" ({note})" if note else "")
			g = groups.setdefault(
				key, _new(page_number, system, "duct_rect", {"dims_mm": [a, b]}, label, "m2")
			)
			g["quantity"] += 2 * (a + b) / 1000 * count / 1000  # duct surface = perimeter x length
			g["lines"].append(line)
		elif section == "Formstücke rund" and name.startswith("Bogen") and len(nums) >= 2:
			dn, angle = nums[0], nums[-1]
			key = ("bend", dn, angle, note)
			label = f"Bogen DN{dn} {angle}°" + (f" ({note})" if note else "")
			g = groups.setdefault(
				key, _new(page_number, system, "bend", {"dn_mm": [dn], "angle": angle}, label, "pc")
			)
			g["quantity"] += count
			g["lines"].append(line)
		else:
			# Other fittings: one position per fitting type and page, sizes listed in the text.
			kind = "fitting_round" if section in ("Rohre", "Formstücke rund") else "fitting_rect"
			key = (kind, name)
			g = groups.setdefault(key, _new(page_number, system, kind, {}, name, "pc"))
			g["quantity"] += count
			g["lines"].append(line)

	out = []
	for g in groups.values():
		g["quantity"] = round(g["quantity"], 3)
		g["description_original"] = "Bauteilliste Lüftung\n" + "\n".join(g.pop("lines"))
		out.append(g)
	return out


def _new(page, system, kind, attrs, label, unit):
	return {
		"source_page": page,
		"system": system,
		"kind": kind,
		"attrs": attrs,
		"title": "Bauteilliste Lüftung",
		"label": label,
		"quantity": 0.0,
		"unit": unit,
		"lines": [],
	}
