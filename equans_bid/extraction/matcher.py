"""Match a tender position to a catalogue item, driven only by the trade's family data.

1. Candidates: catalogue items of the position's family (and unit of measure).
2. Hard guard: every key attribute of the family must agree with the item; this keeps a
   DN125 position off a DN100 item, or a 5x2.5 mm² cable off a 3x1.5 mm² one.
3. Soft attributes (family data) may differ: priced as the nearest item, status assumption.
4. size_strategy "nearest_class": the nearest catalogue size class by perimeter, ties larger.
5. Similarity only ranks candidates that already agree. It is pluggable (`Similarity`);
   the default is lexical, an embedding backend can be configured.
"""

from dataclasses import dataclass, field
from typing import Protocol

from rapidfuzz import fuzz

from equans_bid.extraction.attributes import KEY_TYPES
from equans_bid.reasons import reason, render
from equans_bid.trades import Family

CONFIDENT = 0.92  # same value the golden file reports for verified matches
ASSUMED = 0.75
PROPOSED = 0.5

# Reason code when a key attribute differs; other keys use the generic "attribute_mismatch".
MISMATCH_REASONS = {
	"dn_mm": lambda cat, pos: reason("dn_mismatch", dn=cat),
	"dims_mm": lambda cat, pos: reason("size_mismatch", size="x".join(map(str, cat))),
	"thickness_mm": lambda cat, pos: reason("thickness_mismatch", thickness=cat),
	"weatherproof": lambda cat, pos: reason("weatherproof_mismatch"),
	"angle": lambda cat, pos: reason("angle_mismatch", angle=pos, catalog_angle=cat),
}


class Similarity(Protocol):
	def score(self, text: str, candidate: str) -> float: ...


class LexicalSimilarity:
	"""Token-set similarity in [0, 1]; deterministic and dependency-free."""

	def score(self, text: str, candidate: str) -> float:
		return fuzz.token_set_ratio(text, candidate) / 100


@dataclass(frozen=True)
class Match:
	product_id: str | None
	confidence: float
	reason_code: str
	reason_args: dict = field(default_factory=dict)

	@property
	def reason(self) -> str:
		"""English text of the reason (stored as `status_reason`, for logs); display translates the code."""
		return render(self.reason_code, self.reason_args)


def index_catalog(rows: list[dict]) -> list[dict]:
	"""Rows with `family` and `attributes` already set (see equans_bid.trades / seed)."""
	return [{**r, "kind": r.get("family"), "attrs": r.get("attributes") or {}} for r in rows]


def _dims_agree(pos_dims: list[int], cat_dims: list[int]) -> bool:
	n = len(cat_dims)
	if len(pos_dims) < n:
		return False
	# Width and height may be written either way round; length (3rd) must match in place.
	if sorted(pos_dims[:2]) != sorted(cat_dims[:2]):
		return False
	return n < 3 or pos_dims[2] == cat_dims[2]


def _agrees(key: str, pos_value, cat_value) -> bool:
	kind = KEY_TYPES.get(key)
	if kind == "flag":
		return bool(pos_value) == bool(cat_value)
	if kind == "dims":
		return _dims_agree(pos_value or [], cat_value)
	if kind == "candidates":
		return cat_value in (pos_value or [])
	return pos_value == cat_value


def attributes_agree(pos: dict, cat: dict, keys: list[str], soft: tuple = ()) -> tuple[bool, dict]:
	"""(agree, detail): every key attribute the item carries must agree with the position.
	A soft attribute only counts when the position states it."""
	for key in keys:
		cat_value = cat.get(key)
		if KEY_TYPES.get(key) != "flag" and cat_value is None:
			continue  # the item does not constrain this attribute
		if key in soft and key not in pos:
			continue
		if not _agrees(key, pos.get(key), cat_value):
			make = MISMATCH_REASONS.get(key)
			detail = (
				make(cat_value, pos.get(key))
				if make
				else reason("attribute_mismatch", attribute=key, expected=cat_value, found=pos.get(key))
			)
			return False, detail
	return True, reason("attributes_agree")


def _perimeter(dims: list[int]) -> int:
	return 2 * sum(dims[:2]) if len(dims) >= 2 else 0


def match(
	family_code: str | None,
	attrs: dict,
	text: str,
	catalog: list[dict],
	families: dict[str, Family],
	unit: str = "",
	similarity: Similarity | None = None,
) -> Match:
	sim = similarity or LexicalSimilarity()
	if not family_code:
		return Match(None, 0.0, "family_unknown")
	candidates = [c for c in catalog if c["kind"] == family_code]
	if not candidates:
		return Match(None, 0.0, "no_catalog_item", {"family": family_code})

	family = families.get(family_code) or Family(code=family_code)
	keys = family.key_attributes or sorted({k for c in candidates for k in c["attrs"]})
	soft = tuple(family.soft_attributes)

	agreeing = [c for c in candidates if attributes_agree(attrs, c["attrs"], keys, soft)[0]]
	if unit:
		same_unit = [c for c in agreeing if c["unit"] == unit]
		if agreeing and not same_unit:
			best = agreeing[0]
			return Match(
				best["product_id"], PROPOSED, "unit_mismatch", {"unit": unit, "catalog_unit": best["unit"]}
			)
		agreeing = same_unit

	if agreeing:
		best = max(agreeing, key=lambda c: sim.score(text, c["description"]))
		if len(agreeing) > 1:
			return Match(best["product_id"], ASSUMED, "several_fit", {"count": len(agreeing)})
		return Match(best["product_id"], CONFIDENT, "exact_match")

	# Soft attributes: same family and key attributes, a soft one differs -> priced as that item.
	if soft and any(k in attrs for k in soft):
		hard = [k for k in keys if k not in soft]
		near = [
			c
			for c in candidates
			if (c["unit"] == unit or not unit) and attributes_agree(attrs, c["attrs"], hard)[0]
		]
		if near:
			first = soft[0]
			best = min(near, key=lambda c: abs((c["attrs"].get(first) or 0) - (attrs.get(first) or 0)))
			_, why = attributes_agree(attrs, best["attrs"], keys, soft)
			return Match(
				best["product_id"], ASSUMED, "priced_as", {"product": best["product_id"], "detail": why}
			)

	if family.size_strategy == "nearest_class" and attrs.get("dims_mm"):
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
		return Match(best["product_id"], ASSUMED, "nearest_size_class", {"size": size})

	best = max(candidates, key=lambda c: sim.score(text, c["description"]))
	_, why = attributes_agree(attrs, best["attrs"], keys, soft)
	return Match(best["product_id"], PROPOSED, "nearest_item", {"product": best["product_id"], "detail": why})
