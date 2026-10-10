"""Match a tender position to a catalogue item.

Technical attributes beat similarity: a candidate is only accepted when every size attribute
it carries (DN, dimensions, insulation thickness, weatherproof) agrees with the position.
Text similarity only ranks candidates that already agree.
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

from equans_bid.extraction.classify import NO_CATALOG_LABELS, catalog_attributes, catalog_kind

CONFIDENT = 0.92  # same value the golden file reports for verified matches
ASSUMED = 0.75
PROPOSED = 0.5
SOFT_ATTRIBUTES = {"angle"}  # a bend at another angle is priced like the catalogue bend
NEAREST_SIZE_KINDS = {"duct_rect"}  # catalogue has size classes, the tender has exact sizes


@dataclass(frozen=True)
class Match:
	product_id: str | None
	confidence: float
	reason: str


def index_catalog(rows: list[dict]) -> list[dict]:
	"""Rows from catalog.csv or Catalog Item; adds `kind` and parsed `attrs`."""
	return [
		{
			**r,
			"kind": catalog_kind(r["subcategory"], r.get("category", ""), r["description"]),
			"attrs": catalog_attributes(r["description"], r["subcategory"]),
		}
		for r in rows
	]


def _dims_agree(pos_dims: list[int], cat_dims: list[int]) -> bool:
	n = len(cat_dims)
	if len(pos_dims) < n:
		return False
	# Width and height may be written either way round; length (3rd) must match in place.
	if sorted(pos_dims[:2]) != sorted(cat_dims[:2]):
		return False
	return n < 3 or pos_dims[2] == cat_dims[2]


def attributes_agree(pos: dict, cat: dict) -> tuple[bool, str]:
	if "dn_mm" in cat:
		if cat["dn_mm"] not in pos.get("dn_mm", []):
			return False, f"DN{cat['dn_mm']} not found in position"
	if "dims_mm" in cat:
		if not _dims_agree(pos.get("dims_mm", []), cat["dims_mm"]):
			return False, f"size {'x'.join(map(str, cat['dims_mm']))} mm does not match"
	if "thickness_mm" in cat and pos.get("thickness_mm") != cat["thickness_mm"]:
		return False, f"thickness {cat['thickness_mm']} mm does not match"
	if bool(cat.get("weatherproof")) != bool(pos.get("weatherproof")):
		return False, "weatherproof finish differs"
	if "angle" in cat and "angle" in pos and pos["angle"] != cat["angle"]:
		return False, f"angle {pos['angle']}° differs from catalogue {cat['angle']}°"
	return True, "attributes agree"


def _without(attrs: dict, keys: set) -> dict:
	return {k: v for k, v in attrs.items() if k not in keys}


def _perimeter(dims: list[int]) -> int:
	return 2 * sum(dims[:2]) if len(dims) >= 2 else 0


def match(kind: str | None, attrs: dict, text: str, catalog: list[dict], unit: str = "") -> Match:
	if not kind:
		return Match(None, 0.0, "Product family not recognised")
	candidates = [c for c in catalog if c["kind"] == kind]
	if not candidates:
		label = NO_CATALOG_LABELS.get(kind, kind)
		return Match(None, 0.0, f"No catalogue item for {label}: price manually or request a quote")

	agreeing = [c for c in candidates if attributes_agree(attrs, c["attrs"])[0]]
	if unit:
		same_unit = [c for c in agreeing if c["unit"] == unit]
		if agreeing and not same_unit:
			best = agreeing[0]
			return Match(
				best["product_id"], PROPOSED, f"Unit {unit} differs from catalogue unit {best['unit']}"
			)
		agreeing = same_unit

	if agreeing:
		best = max(agreeing, key=lambda c: fuzz.token_set_ratio(text, c["description"]))
		if len(agreeing) > 1:
			return Match(
				best["product_id"], ASSUMED, f"{len(agreeing)} catalogue items fit; best text match chosen"
			)
		return Match(best["product_id"], CONFIDENT, "Family and size match the catalogue")

	# Soft attributes: same family and size, different angle -> priced as the catalogue item.
	soft = [c for c in candidates if c["unit"] == unit or not unit]
	soft = [
		c
		for c in soft
		if attributes_agree(_without(attrs, SOFT_ATTRIBUTES), _without(c["attrs"], SOFT_ATTRIBUTES))[0]
	]
	if soft and any(k in attrs for k in SOFT_ATTRIBUTES):
		best = min(soft, key=lambda c: abs(c["attrs"].get("angle", 0) - attrs.get("angle", 0)))
		_, why = attributes_agree(attrs, best["attrs"])
		return Match(best["product_id"], ASSUMED, f"Priced as {best['product_id']}: {why}")

	if kind in NEAREST_SIZE_KINDS and attrs.get("dims_mm"):
		target = _perimeter(attrs["dims_mm"])
		# On a tie between two size classes take the larger one: conservative for a price.
		best = min(
			candidates,
			key=lambda c: (
				abs(_perimeter(c["attrs"].get("dims_mm", [])) - target),
				-_perimeter(c["attrs"].get("dims_mm", [])),
			),
		)
		size = "x".join(map(str, best["attrs"]["dims_mm"]))
		return Match(
			best["product_id"],
			ASSUMED,
			f"No exact size in catalogue; priced per m2 as nearest size class {size} mm",
		)

	best = max(candidates, key=lambda c: fuzz.token_set_ratio(text, c["description"]))
	_, why = attributes_agree(attrs, best["attrs"])
	return Match(best["product_id"], PROPOSED, f"Nearest item {best['product_id']}: {why}")
