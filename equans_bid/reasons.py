"""Status reasons and document warnings as codes.

A position stores `reason_code` + `reason_args` (JSON); nothing translated is ever saved.
Display translates the code: the UI with its locale files (`reason.<code>`, `warning.<code>`),
the export with Frappe's `_()` and `locale/*.po`. Product-family labels are master data
(Product Family `labels`), passed in as `family_label`. Templates are English
with named placeholders, the same names the frontend uses. No Frappe import here, so the
extraction modules stay plain Python.
"""


def N_(msg: str) -> str:
	"""Marks a string for the POT extractor without translating it (Frappe's convention)."""
	return msg


REASONS = {
	"family_unknown": N_("Product family not recognised"),
	"no_catalog_item": N_("No catalogue item for {family}: price manually or request a quote"),
	"unit_mismatch": N_("Unit {unit} differs from catalogue unit {catalog_unit}"),
	"several_fit": N_("{count} catalogue items fit; best text match chosen"),
	"exact_match": N_("Product family and size match the catalogue"),
	"priced_as": N_("Priced as {product}: {detail}"),
	"nearest_item": N_("Nearest item {product}: {detail}"),
	"nearest_size_class": N_("No exact size in catalogue; priced per m² at nearest size class {size} mm"),
	"dn_mismatch": N_("DN{dn} not found in the position"),
	"size_mismatch": N_("size {size} mm does not match"),
	"thickness_mismatch": N_("insulation thickness {thickness} mm does not match"),
	"weatherproof_mismatch": N_("weatherproof finish differs"),
	"angle_mismatch": N_("angle {angle}° instead of catalogue {catalog_angle}°"),
	"attributes_agree": N_("attributes agree"),
	"attribute_mismatch": N_("{attribute} is {found}, catalogue item has {expected}"),
	"llm_conflict": N_("The LLM read a different {fields} than the rules; please check the source"),
	"quantity_missing": N_("Quantity column is empty in the tender"),
	"supplier_package_provisional": N_(
		"Supplier package: catalogue price is provisional until a quote is entered"
	),
	"llm_classified": N_("Classified by LLM as {family}. {detail}"),
	"llm_matched": N_("Mapped by the LLM to {product}; please confirm"),
	"llm_confirmed": N_("LLM and rules both chose {product}"),
	"no_productivity_rule": N_("No productivity rule {install_code}"),
	"product_set_by_estimator": N_("Product set by estimator"),
	"status_set_by_estimator": N_("Status set by estimator"),
}

WARNINGS = {
	"header_conflict": N_("Page header says '{header}', source document is '{source}.docx'"),
}


def reason(code: str, **args) -> dict:
	assert code in REASONS, code
	return {"code": code, "args": args}


class _Keep(dict):
	def __missing__(self, key):
		return "{" + key + "}"


def render(code: str, args: dict | None = None, translate=lambda s: s, family_label=lambda code: code) -> str:
	"""Text for a reason or warning code. `translate` is Frappe's `_` in the export (identity for
	the stored English fallback); `family_label(code)` gives a product family's display label."""
	template = translate(REASONS.get(code) or WARNINGS.get(code) or code)
	values = dict(args or {})
	detail = values.get("detail")
	if isinstance(detail, dict) and "code" in detail:
		values["detail"] = render(detail["code"], detail.get("args"), translate, family_label)
	if "family" in values:
		values["family"] = family_label(values["family"])
	return template.format_map(_Keep(values))
