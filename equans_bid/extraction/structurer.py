"""LLM block structuring: one tender block -> the extraction contract, never a price.

Contract (per block), prompt and keys in English:
	position_ref       LV number when the tender prints one, else null
	description        wording from the block
	quantity, unit     as printed (unit normalised to pc, m, m2, m3, h, LS, system)
	source_page        the page the block came from
	family_hint        one of the trade's family codes (from master data) or "other"
	custom_attributes  {label as printed: value as printed}

The output is untrusted: `verify.py` checks it against the source before anything is used.
Responses are cached by model + prompt/schema version + block text, so reruns, tests and
demos are deterministic and offline; failures are returned (not cached) so a rerun retries.
"""

import hashlib
import json
import os
from pathlib import Path

PROMPT_VERSION = "2"
DEFAULT_MODEL = "gpt-4o"
UNITS = ["pc", "m", "m2", "m3", "h", "LS", "system"]

SYSTEM_PROMPT = (
	"You structure one position of a Swiss construction tender (Leistungsverzeichnis, usually in "
	"German). Copy wording and values exactly as printed; do not translate or paraphrase. "
	"Return the quantity and unit of the position, the product family as one of the given codes "
	"(or 'other'), and every other printed property as custom_attributes, keyed by the label as "
	"printed (e.g. dimensions, manufacturer, type, voltage, DN). Use null when the block does not "
	"state a value. Never return prices or costs."
)


def schema(family_codes: list[str]) -> dict:
	return {
		"name": "tender_position",
		"strict": True,
		"schema": {
			"type": "object",
			"additionalProperties": False,
			"required": [
				"position_ref",
				"description",
				"quantity",
				"unit",
				"source_page",
				"family_hint",
				"custom_attributes",
			],
			"properties": {
				"position_ref": {"type": ["string", "null"]},
				"description": {"type": "string"},
				"quantity": {"type": ["number", "null"]},
				"unit": {"type": ["string", "null"], "enum": [*UNITS, None]},
				"source_page": {"type": "integer"},
				"family_hint": {"type": "string", "enum": [*sorted(family_codes), "other"]},
				"custom_attributes": {
					"type": "array",
					"items": {
						"type": "object",
						"additionalProperties": False,
						"required": ["label", "value"],
						"properties": {"label": {"type": "string"}, "value": {"type": "string"}},
					},
				},
			},
		},
	}


def get_api_key() -> str | None:
	key = os.environ.get("OPENAI_API_KEY")
	if key:
		return key
	try:
		import frappe

		return frappe.conf.get("openai_api_key")
	except Exception:
		return None


class BlockStructurer:
	def __init__(
		self,
		family_codes: list[str],
		cache_dir,
		api_key: str | None = None,
		model: str = DEFAULT_MODEL,
		timeout: float = 30,
	):
		self.family_codes = sorted(family_codes)
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

	def _key(self, text: str, page: int) -> str:
		schema_hash = hashlib.sha256(
			json.dumps(schema(self.family_codes), sort_keys=True).encode()
		).hexdigest()[:12]
		return hashlib.sha256(
			f"{self.model}|{PROMPT_VERSION}|{schema_hash}|{page}|{text}".encode()
		).hexdigest()

	def __call__(self, block: dict) -> dict:
		text = block["block_text"]
		path = self.cache_dir / f"{self._key(text, block['source_page'])}.json"
		if path.exists():
			self.cache_hits += 1
			return json.loads(path.read_text())
		try:
			self.calls += 1
			response = self.client.chat.completions.create(
				model=self.model,
				temperature=0,
				response_format={"type": "json_schema", "json_schema": schema(self.family_codes)},
				messages=[
					{"role": "system", "content": SYSTEM_PROMPT},
					{"role": "user", "content": f"Page {block['source_page']}:\n{text[:6000]}"},
				],
			)
			data = json.loads(response.choices[0].message.content)
		except Exception as e:
			self.errors += 1
			return {"error": f"LLM structuring failed: {type(e).__name__}: {e}"[:300]}
		path.write_text(json.dumps(data, ensure_ascii=False))
		return data

	def info(self) -> dict:
		return {"model": self.model, "calls": self.calls, "cached": self.cache_hits, "errors": self.errors}

	def stats(self) -> str:
		return f"LLM {self.model}: {self.calls} API calls, {self.cache_hits} cached, {self.errors} errors"


def get_structurer(family_codes: list[str], cache_dir) -> BlockStructurer | None:
	"""A structurer when an API key is configured, else None (rules only)."""
	return BlockStructurer(family_codes, cache_dir) if get_api_key() else None
