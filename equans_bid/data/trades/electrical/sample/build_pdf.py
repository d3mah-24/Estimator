"""Build the SYNTHETIC electrical tender PDF (sample/BKP_231_LV_Elektro_SAMPLE.pdf).

	cd frappe-bench && env/bin/python apps/equans_bid/equans_bid/data/trades/electrical/sample/build_pdf.py

Laid out like a Swiss LV page: header "<BKP> <system> Seite n / m", a quantity column (unit +
amount at the end of the line) and the source-document footer. All content is invented.
"""

from pathlib import Path

from weasyprint import HTML

HERE = Path(__file__).resolve().parent
SYSTEM = "231.01 EL01 Allgemeininstallation"

PAGES = [
	[
		("Installationskabel NYM-J", None, None),
		("Fabrikat z.B. DemoCable", None, None),
		("Querschnitt 3x1.5 mm²", "m", "240"),
		("3x2.5 mm²", "m", "180"),
		("5x2.5 mm²", "m", "95"),
		("5x10 mm²", "m", "20"),
		("Steckdose Typ 13 Unterputz", None, None),
		("Fabrikat z.B. DemoSwitch", None, None),
		("Schutzart IP20", "Stk", "42"),
		("Steckdose Typ 13 Aufputz, Nassraum", None, None),
		("Schutzart IP55", "Stk", "8"),
	],
	[
		("Lichtschalter 1-polig Unterputz", None, None),
		("Ausführung weiss", "Stk", "30"),
		("LED-Panel 600 x 600 mm", None, None),
		("Schutzart IP40", "Stk", "64"),
		("Unterverteilung UV-EG", None, None),
		("Bestückung 24 Module", "Stk", "1"),
		("Notleuchte mit Einzelbatterie", None, None),
		("Ausführung Deckenmontage", "Stk", "12"),
	],
]


def page_html(n: int, rows) -> str:
	body = "".join(
		f"<tr><td class='d'>{text}</td><td class='u'>{unit or ''}</td><td class='q'>{qty or ''}</td></tr>"
		for text, unit, qty in rows
	)
	return (
		f"<section><p class='h'>SH Musterschule (SYNTHETIC SAMPLE) {SYSTEM} Seite {n} / {len(PAGES)}</p>"
		"<p class='h'>Pos. Gegenstand Mass- Mass- Einheits- Betrag</p>"
		f"<table>{body}</table>"
		f"<p class='f'>H:\\Projekt\\Muster\\02 L\\{SYSTEM}.docx 01.10.2026</p></section>"
	)


CSS = """
@page { size: A4; margin: 18mm }
body { font-family: sans-serif; font-size: 10pt }
section { page-break-after: always; position: relative; height: 255mm }
table { width: 100%; border-collapse: collapse; margin-top: 8mm }
td { padding: 1.2mm 0 }
td.d { width: 70% } td.u { width: 12% } td.q { width: 18% }
p.f { position: absolute; bottom: 0; font-size: 8pt }
"""

html = f"<html><head><style>{CSS}</style></head><body>{''.join(page_html(i + 1, r) for i, r in enumerate(PAGES))}</body></html>"
out = HERE / "BKP_231_LV_Elektro_SAMPLE.pdf"
HTML(string=html).write_pdf(out)
print(out)
