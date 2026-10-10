"""Verify an LLM extraction contract against the source block before any field is used.

A failed check never drops a position: the field is ignored and the failure is recorded
(reason codes on the position), so the estimator sees what the model claimed and why it was
not taken. The rules extraction stays the reference for quantity, unit and page.
"""

import re
from dataclasses import dataclass, field

UNIT_ALIASES = {"stk": "pc", "st": "pc", "stück": "pc", "m²": "m2", "m³": "m3", "std": "h", "psch": "LS"}
ALLOWED_UNITS = {"pc", "m", "m2", "m3", "h", "LS", "system"}


def _squash(s: str) -> str:
	return re.sub(r"\s+", "", str(s or "")).lower()


def _number_variants(value: float) -> set[str]:
	"""Ways a number may be printed: 5, 5.0, 12.5, 12,5, 1'600."""
	whole = int(value) if float(value).is_integer() else None
	out = {f"{value:g}", f"{value:g}".replace(".", ",")}
	if whole is not None:
		out |= {str(whole), f"{whole:,}".replace(",", "'"), f"{whole:,}".replace(",", "’")}
	return out


@dataclass
class Verified:
	family_hint: str | None = None
	custom_attributes: dict = field(default_factory=dict)
	position_ref: str | None = None
	failures: list[str] = field(default_factory=list)
	conflicts: dict = field(default_factory=dict)


def verify(contract: dict, block: dict, page_text: str, family_codes: set[str]) -> Verified:
	"""`block` carries the rules result: block_text, source_page, quantity, unit."""
	out = Verified()
	if not contract or contract.get("error"):
		out.failures.append("llm_error")
		return out
	text = block["block_text"]

	if contract.get("source_page") != block["source_page"]:
		out.failures.append("page_mismatch")

	qty = contract.get("quantity")
	if qty is not None:
		on_page = any(v in page_text for v in _number_variants(float(qty)))
		if not on_page:
			out.failures.append("quantity_not_on_page")
		elif block.get("quantity") is not None and float(qty) != float(block["quantity"]):
			out.conflicts["quantity"] = qty

	unit = contract.get("unit")
	if unit:
		unit = UNIT_ALIASES.get(str(unit).lower(), unit)
		if unit not in ALLOWED_UNITS:
			out.failures.append("unit_not_allowed")
		elif block.get("unit") and unit != block["unit"]:
			out.conflicts["unit"] = unit

	hint = contract.get("family_hint")
	if hint and hint != "other":
		if hint in family_codes:
			out.family_hint = hint
		else:
			out.failures.append("family_unknown_code")

	squashed = _squash(text)
	pairs = contract.get("custom_attributes") or []
	if isinstance(pairs, dict):
		pairs = [{"label": k, "value": v} for k, v in pairs.items()]
	for pair in pairs[:30]:
		label, value = str(pair.get("label") or "")[:80], str(pair.get("value") or "")[:200]
		if not label or not value:
			continue
		if _squash(value) in squashed:
			out.custom_attributes[label] = value
		else:
			out.failures.append("attribute_not_in_block")

	ref = contract.get("position_ref")
	if ref and _squash(ref) in squashed:
		out.position_ref = ref
	elif ref:
		out.failures.append("position_ref_not_in_block")
	return out
