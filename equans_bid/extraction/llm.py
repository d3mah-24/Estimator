"""GPT-4o fallback: classify a tender position the rules could not recognise.

The model returns a product family and size attributes only, never prices. Its output is
untrusted: it is validated against the schema and the known families before use.
Results are cached on disk, keyed by model + schema version + the position text, so a
re-run (or the demo) never waits on the API.
"""

import hashlib
import json
import os
from pathlib import Path

from equans_bid.extraction.classify import (
	CATALOG_FIELD_DEVICE_KINDS,
	CATALOG_KIND_BY_SUBCATEGORY,
	NO_CATALOG_LABELS,
	TENDER_KIND_RULES,
)

SCHEMA_VERSION = "1"
DEFAULT_MODEL = "gpt-4o"

KINDS = sorted(
	{k for k, _ in TENDER_KIND_RULES}
	| set(CATALOG_KIND_BY_SUBCATEGORY.values())
	| {k for k, _ in CATALOG_FIELD_DEVICE_KINDS}
	| set(NO_CATALOG_LABELS)
)

NULLABLE_INT = {"type": ["integer", "null"]}
SCHEMA = {
	"name": "tender_position",
	"strict": True,
	"schema": {
		"type": "object",
		"additionalProperties": False,
		"required": ["kind", "description_en", "attributes"],
		"properties": {
			"kind": {"type": "string", "enum": [*KINDS, "other"]},
			"description_en": {"type": "string"},
			"attributes": {
				"type": "object",
				"additionalProperties": False,
				"required": [
					"dn_mm",
					"width_mm",
					"height_mm",
					"length_mm",
					"thickness_mm",
					"angle",
					"weatherproof",
				],
				"properties": {
					"dn_mm": NULLABLE_INT,
					"width_mm": NULLABLE_INT,
					"height_mm": NULLABLE_INT,
					"length_mm": NULLABLE_INT,
					"thickness_mm": NULLABLE_INT,
					"angle": NULLABLE_INT,
					"weatherproof": {"type": ["boolean", "null"]},
				},
			},
		},
	},
}

SYSTEM_PROMPT = (
	"You classify one position from a Swiss ventilation tender (BKP 244, written in German). "
	"Return the product family as one of the given kinds, a short English description, and "
	"size attributes converted to millimetres (Ø 12.5 cm = DN 125). Use null for any value "
	"the text does not state. If no kind fits, return kind 'other'. "
	"Never return prices, costs or quantities."
)


def get_api_key() -> str | None:
	key = os.environ.get("OPENAI_API_KEY")
	if key:
		return key
	try:
		import frappe

		return frappe.conf.get("openai_api_key")
	except Exception:
		return None


class GPT4oClassifier:
	def __init__(
		self,
		cache_dir,
		api_key: str | None = None,
		model: str = DEFAULT_MODEL,
		timeout: float = 30,
	):
		self.cache_dir = Path(cache_dir)
		self.cache_dir.mkdir(parents=True, exist_ok=True)
		self.api_key = api_key or get_api_key()
		self.model = model
		self.timeout = timeout
		self.calls = self.cache_hits = self.errors = 0
		self._client = None

	@property
	def client(self):
		if self._client is None:
			from openai import OpenAI

			self._client = OpenAI(api_key=self.api_key, timeout=self.timeout, max_retries=1)
		return self._client

	def _key(self, text: str) -> str:
		return hashlib.sha256(f"{self.model}|{SCHEMA_VERSION}|{text}".encode()).hexdigest()

	def __call__(self, position: dict) -> dict | None:
		text = "\n".join(
			filter(
				None,
				[
					position.get("title"),
					position.get("description_original"),
					position.get("label"),
				],
			)
		)
		path = self.cache_dir / f"{self._key(text)}.json"
		if path.exists():
			self.cache_hits += 1
			return self._validate(json.loads(path.read_text()))
		try:
			self.calls += 1
			response = self.client.chat.completions.create(
				model=self.model,
				temperature=0,
				response_format={"type": "json_schema", "json_schema": SCHEMA},
				messages=[
					{"role": "system", "content": SYSTEM_PROMPT},
					{"role": "user", "content": text[:4000]},
				],
			)
			data = json.loads(response.choices[0].message.content)
		except Exception as e:
			# Kept on the position (not cached) so a later run can retry it.
			self.errors += 1
			return {
				"kind": None,
				"error": f"LLM classification failed: {type(e).__name__}: {e}"[:300],
			}
		path.write_text(json.dumps(data, ensure_ascii=False))
		return self._validate(data)

	@staticmethod
	def _validate(data: dict) -> dict:
		kind = data.get("kind")
		if kind not in KINDS:
			return {"kind": None, "description_en": data.get("description_en")}
		a = data.get("attributes") or {}

		def as_int(v):
			return (
				int(v) if isinstance(v, int | float) and not isinstance(v, bool) and 0 < v < 100000 else None
			)

		attrs = {}
		if as_int(a.get("dn_mm")):
			attrs["dn_mm"] = [as_int(a["dn_mm"])]
		dims = [as_int(a.get(k)) for k in ("width_mm", "height_mm", "length_mm")]
		dims = [d for d in dims if d]
		if len(dims) >= 2:
			attrs["dims_mm"] = dims
		for k in ("thickness_mm", "angle"):
			if as_int(a.get(k)):
				attrs[k] = as_int(a[k])
		if a.get("weatherproof") is True:
			attrs["weatherproof"] = True
		return {
			"kind": kind,
			"attributes": attrs,
			"description_en": (data.get("description_en") or "")[:200],
		}

	def stats(self) -> str:
		return f"{self.model}: {self.calls} API calls, {self.cache_hits} cached, {self.errors} errors"


def get_enricher(cache_dir) -> GPT4oClassifier | None:
	"""The GPT-4o fallback when an API key is configured, else None (rules only)."""
	return GPT4oClassifier(cache_dir) if get_api_key() else None
