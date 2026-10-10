"""Generic attribute parsing: notation and units only, no product vocabulary.

Normalised attributes (`attributes`) use canonical keys and SI-style units so a tender and a
catalogue compare directly. Raw project columns (`custom_attributes`) keep their printed label
and value, untranslated, as source evidence. Trade-specific rules (e.g. which words mean
"weatherproof") come from the trade's `attribute_rules` data.
"""

import re

from equans_bid.trades import TradeConfig, apply_rule

NUM = r"\d+(?:[.,]\d+)?"
DIAMETER = re.compile(rf"(?:Ø\s*({NUM})\s*(cm|mm)|({NUM})\s*Ø\s*(cm|mm))")
# "x" or the multiplication sign U+00D7.
DIMS = re.compile(rf"({NUM})\s*[x×]\s*({NUM})(?:\s*[x×]\s*({NUM}))?\s*(cm|mm)?")
TABLE_UNIT = re.compile(r"^(cm|mm)\b")
DIAMETER_HEADER = re.compile(r"\bDN\b|Ø")
DIMS_LINE = re.compile(r"^B\s*x\s*H")  # "B x H": width x height notation

# How each canonical key compares. Unknown keys compare by equality.
KEY_TYPES = {
	"dn_mm": "candidates",  # position may carry several candidate nominal sizes (table rows)
	"dims_mm": "dims",  # width/height in either order, length in place
	"weatherproof": "flag",
}


def _num(s: str) -> float:
	return float(s.replace(",", "."))


def _mm(value: float, unit: str) -> int:
	return round(value * 10) if unit == "cm" else round(value)


def _context_unit(context: list[str]) -> str:
	"""Unit for dimensions written without one: a table header ('cm' / 'mm') or '(mm)' in the text."""
	for line in reversed(context):
		m = TABLE_UNIT.match(line)
		if m:
			return m.group(1)
		if "(mm)" in line:
			return "mm"
	return "cm"


def tender_attributes(label: str, context: list[str], trade: TradeConfig) -> dict:
	"""Normalised attributes of one position; the quantity line's label wins over the block text."""
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
			if DIMS_LINE.match(line):
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

	for rule in trade.attribute_rules:
		value = apply_rule(rule, text + "\n" + label)
		if value is not None:
			attrs[rule["key"]] = value
	return attrs


def catalog_attributes(row: dict, trade: TradeConfig) -> dict:
	"""Normalised attributes of a catalogue row: an explicit `attributes` JSON column wins,
	else generic notation in the description plus the trade's catalog_attribute_rules."""
	if row.get("attributes"):
		import json

		value = row["attributes"]
		return json.loads(value) if isinstance(value, str) else dict(value)
	description = row.get("description") or ""
	attrs: dict = {}
	m = re.search(r"DN(\d+)", description)
	if m:
		attrs["dn_mm"] = int(m.group(1))
	m = re.search(r"(\d+)x(\d+)(?:x(\d+))?\s*mm", description)
	if m:
		attrs["dims_mm"] = [int(g) for g in m.groups() if g]
	for rule in trade.catalog_attribute_rules:
		value = apply_rule(rule, row.get(rule.get("field", "description")) or "")
		if value is not None:
			attrs[rule["key"]] = value
	m = re.search(r"(\d+)°", description)
	if m:
		attrs["angle"] = int(m.group(1))
	return attrs


def custom_attributes(
	context: list[str], label: str, trade: TradeConfig, inherited_key: str | None = None
) -> tuple[dict, str | None]:
	"""(columns, label key of the quantity line). Project columns as printed: lines that start
	with one of the trade's attribute labels.

	The quantity line's own label ("Grösse Ø 10 cm") is included; a variant line without a label
	("Ø 12.5 cm") inherits the label of the variant before it (`inherited_key`).
	"""
	labels = sorted(trade.attribute_labels, key=len, reverse=True)  # longest label first
	out: dict = {}

	def split(line: str):
		for key in labels:
			if line == key or line.startswith(key + " "):
				value = line[len(key) :].strip()
				return (key, value) if value else None
		return None

	for line in context:
		hit = split(line)
		if hit and hit[0] not in out:
			out[hit[0]] = hit[1][:200]
	label_key = None
	if label:
		hit = split(label)
		if hit:
			out[hit[0]] = hit[1][:200]
			label_key = hit[0]
		elif inherited_key:
			out[inherited_key] = label[:200]
			label_key = inherited_key
	return dict(list(out.items())[:30]), label_key
