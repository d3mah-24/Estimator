"""Display-time localization for the backend (exports, messages).

Codes (statuses, units, scenarios, price sources, reasons) are stored and returned by the API
unchanged; this module turns them into text for one locale. Amounts stay numbers until they
are formatted here. Every label carries a gettext context so the app's catalogue can never
override Frappe's own translation of a generic word ("Target", "h").

UI locale -> Frappe language (locale/<lang>.po) -> babel locale:
	de-CH -> de -> de_CH   ·   fr-CH -> fr -> fr_CH   ·   en -> en -> en
"""

from babel.dates import format_datetime
from babel.numbers import format_currency, format_decimal, format_percent

from equans_bid.reasons import render

UI_LOCALES = {"de-CH": ("de", "de_CH"), "fr-CH": ("fr", "fr_CH"), "en": ("en", "en")}
DEFAULT_UI_LOCALE = "de-CH"
MISSING = "—"  # shown for a missing price in every locale, never 0

CTX_STATUS = "Tender Item status"
CTX_UNIT = "Unit of measure"
CTX_SCENARIO = "Bid scenario"
CTX_PRICE_SOURCE = "Price source"
CTX_EXPORT = "Tender export"
CTX_FAMILY = "Product family"

STATUS_LABELS = {
	"calculated": "Calculated",
	"supplier_quote_required": "Supplier quote required",
	"assumption_applied": "Assumption applied",
	"review_required": "Review required",
	"insufficient_information": "Insufficient information",
	"out_of_scope": "Out of scope",
	"non_priceable": "Not priceable",
}
UNIT_LABELS = {"pc": "pc", "m": "m", "m2": "m²", "m3": "m³", "h": "h", "LS": "LS", "system": "system"}
SCENARIO_LABELS = {"Aggressive": "Aggressive", "Target": "Target", "Conservative": "Conservative"}
PRICE_SOURCE_LABELS = {
	"catalog": "Catalogue",
	"supplier_package": "Supplier package",
	"supplier_quote": "Supplier quote",
}


def resolve(ui_locale: str | None) -> tuple[str, str, str]:
	"""(ui_locale, frappe_lang, babel_locale); unknown or empty -> the default de-CH."""
	ui = ui_locale if ui_locale in UI_LOCALES else DEFAULT_UI_LOCALE
	lang, babel_locale = UI_LOCALES[ui]
	return ui, lang, babel_locale


class Localizer:
	"""Translate codes and format numbers for one locale. `translate(msg, lang, context)`
	defaults to Frappe's `_`; tests may pass their own."""

	def __init__(self, ui_locale: str | None = None, translate=None):
		self.ui, self.lang, self.babel = resolve(ui_locale)
		if translate is None:
			from frappe import _ as translate
		self._translate = translate

	def t(self, msg: str, context: str | None = None) -> str:
		return self._translate(msg, lang=self.lang, context=context)

	def status(self, code: str | None) -> str:
		return self.t(STATUS_LABELS[code], CTX_STATUS) if code in STATUS_LABELS else (code or "")

	def unit(self, code: str | None) -> str:
		return self.t(UNIT_LABELS[code], CTX_UNIT) if code in UNIT_LABELS else (code or "")

	def scenario(self, code: str) -> str:
		return self.t(SCENARIO_LABELS.get(code, code), CTX_SCENARIO)

	def price_source(self, code: str | None) -> str:
		return self.t(PRICE_SOURCE_LABELS[code], CTX_PRICE_SOURCE) if code in PRICE_SOURCE_LABELS else ""

	def reason(self, code: str | None, args: dict | None = None) -> str:
		if not code:
			return ""
		return render(code, args, lambda s, ctx=None: self.t(s, CTX_FAMILY if ctx == "family" else None))

	# Formatting: amounts stay numbers until here.
	def chf(self, value) -> str:
		return MISSING if value is None else format_currency(value, "CHF", locale=self.babel)

	def number(self, value, digits: int = 3) -> str:
		if value is None:
			return ""
		return format_decimal(value, format=f"#,##0.{'#' * digits}" if digits else "#,##0", locale=self.babel)

	def percent(self, fraction) -> str:
		return "" if fraction is None else format_percent(fraction, format="#,##0.#%", locale=self.babel)

	def datetime(self, value) -> str:
		return format_datetime(value, "medium", locale=self.babel)
