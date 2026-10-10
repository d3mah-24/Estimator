"""Rule-based classification and attribute parsing for tender positions and catalogue items.

A `kind` is a product family shared by both sides (tender wording is German, catalogue English).
Attributes are numbers in millimetres so both sides compare directly.
"""

import re

# Ordered: the first rule that matches wins, so specific phrases come before generic ones.
TENDER_KIND_RULES: list[tuple[str, re.Pattern]] = [
	("inspection_cover", re.compile(r"revisi\w*deckel|revisionsdeckel")),
	("support_set", re.compile(r"anschlusswink|befestigungswink")),
	("fire_damper", re.compile(r"brandschutzklappe")),
	("fire_seal", re.compile(r"durchdringung|abschottung")),
	("fire_insulation", re.compile(r"brandschutzdämm|dämmung ei\s?\d")),
	("insulation", re.compile(r"ummantelung|wetterfest|aussendämmung|dämmung")),
	("supply_valve", re.compile(r"zuluft\W+tellerventil|tellerventil.*zuluft")),
	("exhaust_valve", re.compile(r"abluft\W+tellerventil|tellerventil.*abluft")),
	("manual_damper", re.compile(r"drosselklappe")),
	("silencer", re.compile(r"schalldämpfer")),
	("cav", re.compile(r"volumenstromregler.*konstant|konstant.*volumenstromregler|\bvfc\b")),
	("vav", re.compile(r"volumenstromregler|\bvvs\b|tvj-d|tvr-d")),
	("grille", re.compile(r"gitter")),
	("air_outlet", re.compile(r"wirbelstrahl|düsenrohr|überströmer|überströmelement|durchlass")),
	("ahu", re.compile(r"lüftungsgerät|monoblock|klimagerät")),
	("fan", re.compile(r"ventilator")),
	("humidity_sensor", re.compile(r"feuchtefühler")),
	("frost_thermostat", re.compile(r"frostschutz")),
	("dp_transmitter", re.compile(r"druckdifferenz")),
	("temp_sensor", re.compile(r"temperaturfühler")),
	("thermometer", re.compile(r"thermometer")),
	("cleaning_cover", re.compile(r"putzdeckel|kontrolldeckel")),
	("rain_hat", re.compile(r"regenhut|lamellenhut")),
	("earth_duct", re.compile(r"erdverlegung|erdverlegt")),
	("labels", re.compile(r"bezeichnungsschild")),
	("leak_test", re.compile(r"dichtheitsprüfung")),
	("service", re.compile(r"^montage\b|montage und transport|inbetriebsetz|einregulierung")),
]

# Families the tender asks for that the catalogue has no item for: named, so the
# estimator sees what is missing instead of "not recognised".
NO_CATALOG_LABELS = {
	"grille": "Luftgitter",
	"air_outlet": "Luftauslass / Überströmer",
	"fire_insulation": "Brandschutzdämmung",
	"humidity_sensor": "Feuchtefühler",
	"frost_thermostat": "Frostschutzwächter",
	"thermometer": "Zeigerthermometer",
	"cleaning_cover": "Kontroll- / Putzdeckel",
	"rain_hat": "Regenhut / Lamellenhut",
	"earth_duct": "erdverlegte Lüftungsleitung",
	"labels": "Bezeichnungsschilder",
	"leak_test": "Kanaldichtheitsprüfung (Dienstleistung)",
	"service": "Montage- / Inbetriebsetzungsleistung",
	"fitting_round": "Formstück rund",
	"fitting_rect": "Kanalformstück",
}

CATALOG_FIELD_DEVICE_KINDS = [
	("dp_transmitter", "differential pressure"),
	("temp_sensor", "temperature sensor"),
	("actuator", "actuator"),
	("flow_transmitter", "volume flow"),
]

CATALOG_KIND_BY_SUBCATEGORY = {
	"Supply valve": "supply_valve",
	"Exhaust valve": "exhaust_valve",
	"Fire damper": "fire_damper",
	"Manual damper": "manual_damper",
	"Rectangular": "silencer",
	"Compact": "silencer",
	"VAV rectangular": "vav",
	"VAV circular": "vav",
	"CAV circular": "cav",
	"Thermal 30 mm": "insulation",
	"Thermal 60 mm": "insulation",
	"Weatherproof 100 mm": "insulation",
	"Rectangular seal": "fire_seal",
	"Circular seal": "fire_seal",
	"Angle set": "support_set",
	"Inspection cover": "inspection_cover",
	"Circular duct": "duct_round",
	"Circular bend": "bend",
	"Rectangular duct": "duct_rect",
	"Air-handling unit": "ahu",
	"Fan": "fan",
	"Field device": "field_device",
}

NUM = r"\d+(?:[.,]\d+)?"
DIAMETER = re.compile(rf"(?:Ø\s*({NUM})\s*(cm|mm)|({NUM})\s*Ø\s*(cm|mm))")
# "x" or the multiplication sign U+00D7, both used in the tender.
DIMS = re.compile(rf"({NUM})\s*[x\u00d7]\s*({NUM})(?:\s*[x\u00d7]\s*({NUM}))?\s*(cm|mm)?")
THICKNESS = re.compile(r"aus\s+(\d+)\s*mm\s+mineralwoll|(\d+)\s*mm\s+(?:mineral wool|external)", re.I)
TABLE_UNIT = re.compile(r"^(cm|mm)\b")
DIAMETER_HEADER = re.compile(r"\bDN\b|Ø")


def _num(s: str) -> float:
	return float(s.replace(",", "."))


def _mm(value: float, unit: str) -> int:
	return round(value * 10) if unit == "cm" else round(value)


def tender_kind(title: str, text: str, label: str = "") -> str | None:
	for haystack in (title.lower(), label.lower(), text.lower()):
		for kind, pattern in TENDER_KIND_RULES:
			if pattern.search(haystack):
				return kind
	return None


def pick_title(block_lines: list[str]) -> str | None:
	"""The first block line that names a product family, else None (segmenter uses line 1)."""
	for line in block_lines:
		if tender_kind(line, ""):
			return line
	return None


def _context_unit(context: list[str]) -> str:
	"""Unit for dimensions written without one: a table header ('cm' / 'mm') or '(mm)' in the text."""
	for line in reversed(context):
		m = TABLE_UNIT.match(line)
		if m:
			return m.group(1)
		if "(mm)" in line:
			return "mm"
	return "cm"


def tender_attributes(label: str, context: list[str]) -> dict:
	"""Size attributes of one position. The quantity line's label wins over the block text."""
	attrs: dict = {}
	unit = _context_unit(context)
	text = "\n".join(context)

	for source in (label, text):
		m = DIAMETER.search(source)
		if m:
			value, u = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
			attrs["dn_mm"] = [_mm(_num(value), u)]
			break

	m = DIMS.search(label)
	if m:
		u = m.group(4) or unit
		attrs["dims_mm"] = [_mm(_num(g), u) for g in m.groups()[:3] if g]
	else:
		for line in context:
			if re.match(r"^B\s*x\s*H", line):
				m = DIMS.search(line)
				if m:
					u = m.group(4) or unit
					attrs["dims_mm"] = [_mm(_num(g), u) for g in m.groups()[:3] if g]
					break

	# Table rows ("TVR-D 12.5 60 200 150"): every number is a candidate nominal size, when there
	# are no dimensions or the column header names a diameter ("Mod. DN ...", "Länge Ø aussen").
	diameter_header = any(DIAMETER_HEADER.search(l) and not re.search(r"\d", l) for l in context)
	if "dn_mm" not in attrs and label and ("dims_mm" not in attrs or diameter_header):
		numbers = [_mm(_num(n), unit) for n in re.findall(NUM, label)]
		if numbers:
			attrs["dn_mm"] = numbers

	m = THICKNESS.search(text + "\n" + label)
	if m:
		attrs["thickness_mm"] = int(m.group(1) or m.group(2))
	if re.search(r"wetterfest|ummantelung", (text + label).lower()):
		attrs["weatherproof"] = True
	return attrs


def catalog_attributes(description: str, subcategory: str = "") -> dict:
	attrs: dict = {}
	m = re.search(r"DN(\d+)", description)
	if m:
		attrs["dn_mm"] = int(m.group(1))
	m = re.search(r"(\d+)x(\d+)(?:x(\d+))?\s*mm", description)
	if m:
		attrs["dims_mm"] = [int(g) for g in m.groups() if g]
	m = THICKNESS.search(description)
	if m:
		attrs["thickness_mm"] = int(m.group(1) or m.group(2))
	if subcategory.lower().startswith("weatherproof"):
		attrs["weatherproof"] = True
	m = re.search(r"(\d+)°", description)
	if m:
		attrs["angle"] = int(m.group(1))
	return attrs


def catalog_kind(subcategory: str, category: str = "", description: str = "") -> str | None:
	if subcategory == "Field device":
		low = description.lower()
		return next((kind for kind, phrase in CATALOG_FIELD_DEVICE_KINDS if phrase in low), "field_device")
	return CATALOG_KIND_BY_SUBCATEGORY.get(subcategory)
