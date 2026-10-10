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
# Generic Swiss LV page header "<BKP code> <system> Seite n / m"; a trade may refine it
# (TradeConfig.system_header_pattern).
SYSTEM_HEADER = re.compile(r"(?P<system>\d{3}\.\d+\s+\S.*?)\s+Seite\s+\d+\s*/\s*\d+")
# Footer: "H:\\Projekt\\...\\02 L\\244.05 LA05 Turnhalle.docx 31.07.2026" (the source document).
FOOTER_SOURCE = re.compile(r"[\\/](?P<system>\d{3}\.\d+\s[^\\/]*?)\.docx")
SECTION_CODE = re.compile(r"^(\d{3}\.\d+)")
SECTION_HEADING = re.compile(r"^[A-Z]\s+[A-ZÄÖÜ][A-ZÄÖÜ ,/&-]+$")
TRAILING_DOTS = re.compile(r"[\s.…_]{3,}$")


def _prefix_pattern(labels: list[str]) -> re.Pattern | None:
	"""Lines starting with one of the trade's continuation labels continue the previous family."""
	# "\b" as before: a label ending in "." (e.g. "Mod.") then never matches, which is the
	# established behaviour the regression fixture pins.
	return re.compile(r"^(" + "|".join(re.escape(l) for l in labels) + r")\b") if labels else None


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
	system_conflict: dict = field(default_factory=dict)
	block_id: int = 0  # positions from one description block share it (variant lines)

	@property
	def text(self) -> str:
		return "\n".join([*self.context, self.label]).strip()


def parse_quantity(raw: str) -> float:
	return float(raw.replace("'", "").replace("`", "").replace("\u2019", "").replace(",", "."))


def page_system(text: str, header: re.Pattern = SYSTEM_HEADER) -> tuple[str, dict]:
	"""(system, conflict) of an LV page.

	The header names the system; the footer names the source document. When their section
	codes disagree (the tender has Turnhalle pages headed "244.03 Küche"), the footer wins
	and the conflict ({"header", "source"}, displayed as warning `header_conflict`) is returned
	so the estimator sees it.
	"""
	lines = [l.strip() for l in text.splitlines() if l.strip()]
	if not lines:
		return "", {}
	m = header.search(lines[0])
	head = re.sub(r"\s+", " ", m.group("system")) if m else ""
	f = FOOTER_SOURCE.search(lines[-1])
	footer = re.sub(r"\s+", " ", f.group("system")) if f else ""
	if head and footer:
		hc, fc = SECTION_CODE.match(head), SECTION_CODE.match(footer)
		if hc and fc and hc.group(1) != fc.group(1):
			return footer, {"header": head, "source": footer}
	return head or footer, {}


def _body_lines(text: str, header: re.Pattern = SYSTEM_HEADER) -> tuple[str, list[str]]:
	lines = [l.strip() for l in text.splitlines() if l.strip()]
	system = ""
	if lines and header.search(lines[0]):
		system = re.sub(r"\s+", " ", header.search(lines[0]).group("system"))
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


def segment(
	pages, title_picker=None, header: re.Pattern = SYSTEM_HEADER, continuation_labels: list[str] = ()
) -> list[RawPosition]:
	"""`pages`: iterable of objects with `.number` and `.text`.

	`title_picker(block_lines) -> str` chooses the block title; defaults to the first line.
	`header` and `continuation_labels` come from the trade config.
	State carries across pages because a description can start on the previous page.
	"""
	attribute_prefix = _prefix_pattern(list(continuation_labels))
	block_id = 0
	positions: list[RawPosition] = []
	block: list[str] = []
	after_qty = False
	last_title = ""
	system = ""

	for page in pages:
		_, lines = _body_lines(page.text, header)
		this_system, conflict = page_system(page.text, header)
		if this_system and this_system != system:
			system = this_system
			block, after_qty = [], False
			block_id += 1
		for line in lines:
			if SECTION_HEADING.match(line):
				block, after_qty = [], False
				block_id += 1
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
						block_id=block_id,
					)
				)
				last_title = title
				after_qty = True
				continue
			if after_qty:
				# A block that opens with an attribute line continues the previous position family.
				continues = attribute_prefix and attribute_prefix.match(line) and last_title
				block = [last_title, line] if continues else [line]
				block_id += 1
				after_qty = False
			else:
				block.append(line)
	return positions
