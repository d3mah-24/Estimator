"""Split tender pages into candidate positions using layout rules (no LLM).

An LV page has a 3-line header (project + system + page, column titles) and a file-path footer.
A position is a block of description lines that ends in one or more quantity lines, e.g.

	Zuluft - Tellerventil              <- title
	aus Kunststoff, ...                <- context
	Grösse  Ø 10 cm      Stk 5         <- quantity line (one position)
	        Ø 12.5 cm    Stk 6         <- quantity line (next position, same block)

Quantity lines that follow each other share the block's title and context.
"""

import re
from dataclasses import dataclass, field

UNITS = r"Stk|m2|m²|m3|m|LS|psch|Std|h"
QTY_LINE = re.compile(rf"^(?P<label>.*?)(?:^|\s)(?P<unit>{UNITS})\s+(?P<qty>\d[\d'`\u2019]*(?:[.,]\d+)?)\s*$")
# A quantity column left blank ("... gestiftet m2"). Only m2: "Anzahl Kulissen 2 Stk" is an attribute.
UNIT_ONLY_LINE = re.compile(r"^(?P<label>.*[^\d\s])\s+(?P<unit>m2|m²)\s*$")
# "244.01 LA01 Nebenräume Seite 10 / 20"; some sections have no LA code ("244.04 Schulzimmer OG").
SYSTEM_HEADER = re.compile(r"(?P<system>24\d\.\d+\s+(?:LA\s?\d+\s+)?\S.*?)\s+Seite\s+\d+\s*/\s*\d+")
# Footer: "H:\\Projekt\\...\\02 L\\244.05 LA05 Turnhalle.docx 31.07.2026" (the source document).
FOOTER_SOURCE = re.compile(r"[\\/](?P<system>24\d\.\d+\s[^\\/]*?)\.docx")
SECTION_CODE = re.compile(r"^(24\d\.\d+)")
SECTION_HEADING = re.compile(r"^[A-Z]\s+[A-ZÄÖÜ][A-ZÄÖÜ ,/&-]+$")
TRAILING_DOTS = re.compile(r"[\s.…_]{3,}$")
ATTRIBUTE_PREFIX = re.compile(r"^(Fabrikat|Typ|Grösse|Grösse|Mod\.|Material|Farbe|Luftmenge|Offerte)\b")

UNIT_MAP = {
	"Stk": "pc",
	"m": "m",
	"m2": "m2",
	"m²": "m2",
	"m3": "m3",
	"LS": "LS",
	"psch": "LS",
	"Std": "h",
	"h": "h",
}


@dataclass
class RawPosition:
	source_page: int
	system: str
	title: str
	context: list[str]
	label: str
	quantity_raw: str | None
	unit_raw: str
	quantity: float | None = None
	unit: str = ""
	lines: list[str] = field(default_factory=list)
	system_conflict: str = ""

	@property
	def text(self) -> str:
		return "\n".join([*self.context, self.label]).strip()


def parse_quantity(raw: str) -> float:
	return float(raw.replace("'", "").replace("`", "").replace("\u2019", "").replace(",", "."))


def page_system(text: str) -> tuple[str, str]:
	"""(system, conflict) of an LV page.

	The header names the system; the footer names the source document. When their section
	codes disagree (the tender has Turnhalle pages headed "244.03 Küche"), the footer wins
	and the conflict is returned so the estimator sees it.
	"""
	lines = [l.strip() for l in text.splitlines() if l.strip()]
	if not lines:
		return "", ""
	m = SYSTEM_HEADER.search(lines[0])
	header = re.sub(r"\s+", " ", m.group("system")) if m else ""
	f = FOOTER_SOURCE.search(lines[-1])
	footer = re.sub(r"\s+", " ", f.group("system")) if f else ""
	if header and footer:
		hc, fc = SECTION_CODE.match(header), SECTION_CODE.match(footer)
		if hc and fc and hc.group(1) != fc.group(1):
			return footer, f"Page header says '{header}', source document is '{footer}.docx'"
	return header or footer, ""


def _body_lines(text: str) -> tuple[str, list[str]]:
	lines = [l.strip() for l in text.splitlines() if l.strip()]
	system = ""
	if lines and SYSTEM_HEADER.search(lines[0]):
		system = re.sub(r"\s+", " ", SYSTEM_HEADER.search(lines[0]).group("system"))
	body = []
	for i, line in enumerate(lines):
		if i == 0 and (system or "Seite" in line):
			continue
		if line.startswith("Pos. Gegenstand") or line.startswith("Gattg. betrag"):
			continue
		if line.startswith("H:\\") or line.startswith("H:/"):
			continue
		body.append(TRAILING_DOTS.sub("", line).strip())
	return system, [l for l in body if l]


def segment(pages, title_picker=None) -> list[RawPosition]:
	"""`pages`: iterable of objects with `.number` and `.text`.

	`title_picker(block_lines) -> str` chooses the block title; defaults to the first line.
	State carries across pages because a description can start on the previous page.
	"""
	positions: list[RawPosition] = []
	block: list[str] = []
	after_qty = False
	last_title = ""
	system = ""

	for page in pages:
		_, lines = _body_lines(page.text)
		this_system, conflict = page_system(page.text)
		if this_system and this_system != system:
			system = this_system
			block, after_qty = [], False
		for line in lines:
			if SECTION_HEADING.match(line):
				block, after_qty = [], False
				continue
			if line.startswith(("Total ", "Zwischentotal")):
				# "Total aller ... (exkl. Montage)" closes a family; the next line opens a new block.
				after_qty = True
				continue
			m = QTY_LINE.match(line)
			unit_only = None if m else UNIT_ONLY_LINE.match(line)
			if m or unit_only:
				hit = m or unit_only
				context = block if block else []
				title = (title_picker(context) if title_picker else None) or (
					context[0] if context else last_title
				)
				unit_raw = hit.group("unit")
				qty_raw = hit.group("qty") if m else None
				positions.append(
					RawPosition(
						source_page=page.number,
						system=system,
						title=title,
						context=list(context),
						label=hit.group("label").strip(),
						quantity_raw=qty_raw,
						unit_raw=unit_raw,
						quantity=parse_quantity(qty_raw) if qty_raw else None,
						unit=UNIT_MAP.get(unit_raw, unit_raw),
						system_conflict=conflict,
					)
				)
				last_title = title
				after_qty = True
				continue
			if after_qty:
				# A block that opens with an attribute line continues the previous position family.
				block = [last_title, line] if ATTRIBUTE_PREFIX.match(line) and last_title else [line]
				after_qty = False
			else:
				block.append(line)
	return positions
