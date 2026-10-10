"""LLM reading and catalogue mapping, one request per LV page. Never a price.

For every position on a page the model gets the position text (as segmented from the PDF) and a
shortlist of catalogue items from the database, and returns:

	index              the position on the page
	quantity, unit     as printed (unit normalised to pc, m, m2, m3, h, LS, system)
	family             one of the trade's family codes (master data) or "other"
	product_id         one of the shortlisted catalogue items, or null when none fits
	fit                exact | close | none
	note               one short English sentence: why this product
	custom_attributes  [{label, value}] as printed

The answer is untrusted: `check()` verifies it against the page text and the catalogue (the
quantity is on the page, the product was offered, its key attributes such as DN agree with the
position) before the pipeline uses it. Money is computed later, in Python, from the catalogue.

Any OpenAI-compatible endpoint works (OpenAI, Groq, Azure OpenAI, a local server): key, base
URL and model come from the site config (`llm_api_key`, `llm_base_url`, `llm_model`) or the
environment (`LLM_API_KEY` / `OPENAI_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`). Answers are cached
by model + prompt/schema version + page content, so reruns, tests and demos are deterministic
and offline; failures are returned (not cached) so a rerun retries.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from equans_bid.extraction.matcher import attributes_agree
from equans_bid.extraction.verify import _squash, verify

PROMPT_VERSION = "4"
SHORTLIST = 40  # catalogue items offered per position (the page lists their union)
UNITS = ["pc", "m", "m2", "m3", "h", "LS", "system"]
FITS = ["exact", "close", "none"]

SYSTEM_PROMPT = (
	"You are an estimator's assistant for Swiss construction tenders (Leistungsverzeichnis, "
	"usually in German). You get the positions of one tender page and a list of candidate "
	"catalogue items. For every position: copy quantity and unit from the quantity column, "
	"given as [quantity column: …] (e.g. 'Stk 6' -> 6 pc); counts inside the description "
	"(e.g. 'Anzahl Kulissen 2Stk') are properties, not the quantity. Choose the "
	"product family from the given codes (or 'other'); choose the catalogue item that is the same "
	"product with the same size (DN, width x height, thickness, angle) or null when none is; set "
	"fit to 'exact' (same product and size), 'close' (same product, size or type differs) or "
	"'none'. Sizes in the tender may be in cm (Ø 12.5 cm = DN125). Put every other printed "
	"property in custom_attributes, label and value as printed. note: one short English sentence "
	"on the choice. last_line: the position's last text line, copied exactly (it identifies the "
	"position). A product of another kind (e.g. a temperature sensor for a dial thermometer) is "
	"not a fit. Never return prices or costs, never invent values."
)


def schema(family_codes: list[str], product_ids: list[str]) -> dict:
	position = {
		"type": "object",
		"additionalProperties": False,
		"required": [
			"index",
			"last_line",
			"quantity",
			"unit",
			"family",
			"product_id",
			"fit",
			"note",
			"custom_attributes",
		],
		"properties": {
			"index": {"type": "integer"},
			"last_line": {"type": "string"},
			"quantity": {"type": ["number", "null"]},
			"unit": {"type": ["string", "null"], "enum": [*UNITS, None]},
			"family": {"type": "string", "enum": [*sorted(family_codes), "other"]},
			"product_id": {"type": ["string", "null"], "enum": [*sorted(product_ids), None]},
			"fit": {"type": "string", "enum": FITS},
			"note": {"type": "string"},
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
	}
	return {
		"name": "tender_page",
		"strict": True,
		"schema": {
			"type": "object",
			"additionalProperties": False,
			"required": ["positions"],
			"properties": {"positions": {"type": "array", "items": position}},
		},
	}


def get_config() -> dict | None:
	"""{api_key, base_url, model} from the site config or the environment; None without a key."""
	conf = {}
	try:
		import frappe

		if frappe.flags.in_test:
			return None  # tests stay offline and deterministic (fake clients only)
		conf = frappe.conf or {}
	except Exception:
		pass
	key = (
		os.environ.get("LLM_API_KEY")
		or os.environ.get("OPENAI_API_KEY")
		or conf.get("llm_api_key")
		or conf.get("openai_api_key")
	)
	if not key:
		return None
	base_url = os.environ.get("LLM_BASE_URL") or conf.get("llm_base_url") or None
	default_model = "openai/gpt-oss-120b" if base_url and "groq" in base_url else "gpt-4o"
	model = os.environ.get("LLM_MODEL") or conf.get("llm_model") or default_model
	return {"api_key": key, "base_url": base_url, "model": model}


def provider(base_url: str | None) -> str:
	"""Who sees the tender text (recorded on the Tender)."""
	if not base_url:
		return "openai.com"
	return base_url.split("//")[-1].split("/")[0]


@dataclass
class Checked:
	"""A verified answer for one position; `failures` lists what was not taken and why."""

	quantity: float | None = None
	unit: str | None = None
	family: str | None = None
	product_id: str | None = None
	fit: str = "none"
	note: str = ""
	custom_attributes: dict = field(default_factory=dict)
	failures: list[str] = field(default_factory=list)
	conflicts: dict = field(default_factory=dict)


class PageMapper:
	"""`mapper(page, page_text, positions, catalog) -> [Checked, …]` aligned to `positions`.

	`positions`: the pipeline's candidates (block_text, source_page, quantity, unit, kind, attrs).
	`catalog`: indexed catalogue rows (product_id, description, unit, kind, attrs).
	"""

	def __init__(self, family_codes: list[str], cache_dir, config: dict, timeout: float = 120):
		self.family_codes = sorted(family_codes)
		self.cache_dir = Path(cache_dir)
		self.cache_dir.mkdir(parents=True, exist_ok=True)
		self.config = config
		self.model = config["model"]
		self.timeout = timeout
		self.calls = self.cache_hits = self.errors = 0
		self.last_error = None
		self._client = None

	@property
	def client(self):
		if self._client is None:
			from openai import OpenAI

			# max_retries: the client waits as the provider's rate limit asks (429 Retry-After).
			self._client = OpenAI(
				api_key=self.config["api_key"],
				base_url=self.config.get("base_url"),
				timeout=self.timeout,
				max_retries=6,
			)
		return self._client

	@staticmethod
	def shortlist(position: dict, catalog: list[dict]) -> list[dict]:
		"""Catalogue items worth offering: same unit, the rules' family first, then by text."""
		unit = position.get("unit")
		pool = [c for c in catalog if not unit or c["unit"] == unit] or catalog
		text = position["block_text"]
		kind = position.get("kind")
		ranked = sorted(
			pool,
			# product_id last: the same list whatever order the catalogue was loaded in (cache hits).
			key=lambda c: (c["kind"] != kind, -fuzz.token_set_ratio(text, c["description"]), c["product_id"]),
		)
		return ranked[:SHORTLIST]

	@classmethod
	def page_items(cls, positions: list[dict], catalog: list[dict]) -> list[dict]:
		"""The page's catalogue list: every position's shortlist, each item once."""
		seen, out = set(), []
		for p in positions:
			for c in cls.shortlist(p, catalog):
				if c["product_id"] not in seen:
					seen.add(c["product_id"])
					out.append(c)
		return sorted(out, key=lambda c: c["product_id"])

	def _messages(self, page: int, positions: list[dict], items: list[dict]) -> list[dict]:
		catalogue = "\n".join(f"- {c['product_id']} | {c['description']} | {c['unit']}" for c in items)
		parts = [
			f"Tender page {page}. Family codes: {', '.join(self.family_codes)}, other.",
			f"Catalogue items (id | description | unit):\n{catalogue}",
		]
		for i, p in enumerate(positions):
			# The quantity column sits right of the text; the segmenter keeps it apart from block_text.
			column = f"{p.get('quantity_raw') or ''} {p.get('unit_raw') or ''}".strip() or "(empty)"
			parts.append(f"Position {i}:\n{p['block_text'][:3000]}\n[quantity column: {column}]")
		return [
			{"role": "system", "content": SYSTEM_PROMPT},
			{"role": "user", "content": "\n\n".join(parts)},
		]

	def _key(self, page: int, messages: list[dict], ids: list[str]) -> str:
		body = json.dumps(
			[self.model, PROMPT_VERSION, page, messages, schema(self.family_codes, ids)], sort_keys=True
		)
		return hashlib.sha256(body.encode()).hexdigest()

	def __call__(
		self, page: int, page_text: str, positions: list[dict], catalog: list[dict]
	) -> list[Checked]:
		if not positions:
			return []
		items = self.page_items(positions, catalog)
		ids = sorted(c["product_id"] for c in items)
		messages = self._messages(page, positions, items)
		path = self.cache_dir / f"{self._key(page, messages, ids)}.json"
		if path.exists():
			self.cache_hits += 1
			data = json.loads(path.read_text())
		else:
			try:
				self.calls += 1
				extra = {"reasoning_effort": "low"} if "gpt-oss" in self.model else {}
				response = self.client.chat.completions.create(
					model=self.model,
					temperature=0,
					response_format={"type": "json_schema", "json_schema": schema(self.family_codes, ids)},
					messages=messages,
					**extra,
				)
				data = json.loads(response.choices[0].message.content)
				path.write_text(json.dumps(data, ensure_ascii=False))
			except Exception as e:
				self.errors += 1
				self.last_error = f"{type(e).__name__}: {e}"[:300]
				data = {}  # not cached: the next run retries; the rules result stands
		answers = {a.get("index"): a for a in data.get("positions") or [] if isinstance(a, dict)}
		return [
			check(answers.get(i), p, page_text, items, set(self.family_codes))
			for i, p in enumerate(positions)
		]

	def info(self) -> dict:
		return {
			"model": self.model,
			"provider": provider(self.config.get("base_url")),
			"calls": self.calls,
			"cached": self.cache_hits,
			"errors": self.errors,
		}

	def stats(self) -> str:
		line = (
			f"LLM {self.model} ({provider(self.config.get('base_url'))}): {self.calls} API calls, "
			f"{self.cache_hits} cached, {self.errors} errors"
		)
		return line + (f" (last: {self.last_error})" if self.last_error else "")


def check(answer: dict | None, position: dict, page_text: str, offered: list[dict], family_codes) -> Checked:
	"""Verify one answer against the page and the catalogue; keep only what holds."""
	out = Checked()
	if not answer:
		out.failures.append("llm_error")
		return out
	# The answer must be about this position: an answer filed under the wrong index is dropped.
	lines = [line for line in position["block_text"].splitlines() if line.strip()]
	echoed = _squash(answer.get("last_line"))
	if not echoed or not lines or echoed != _squash(lines[-1]):
		out.failures.append("position_mismatch")
		return out
	contract = {
		"source_page": position["source_page"],
		"quantity": answer.get("quantity"),
		"unit": answer.get("unit"),
		"family_hint": answer.get("family"),
		"custom_attributes": answer.get("custom_attributes"),
	}
	v = verify(contract, position, page_text, family_codes)
	out.failures, out.conflicts = list(v.failures), dict(v.conflicts)
	out.family, out.custom_attributes = v.family_hint, v.custom_attributes
	if "quantity_not_on_page" not in v.failures:
		out.quantity = answer.get("quantity")
	out.unit = answer.get("unit") if "unit_not_allowed" not in v.failures else None
	out.note = str(answer.get("note") or "")[:300]
	out.fit = answer.get("fit") if answer.get("fit") in FITS else "none"

	pid = answer.get("product_id")
	if not pid or out.fit == "none":
		return out
	item = next((c for c in offered if c["product_id"] == pid), None)
	if item is None:
		out.failures.append("product_not_offered")
		return out
	if position.get("unit") and item["unit"] != position["unit"]:
		out.failures.append("product_unit_differs")
		return out
	# The model must not overrule the sizes printed in the tender: every attribute the rules
	# read from the position (DN, W x H, thickness, angle…) has to agree with the item.
	keys = sorted(item["attrs"])
	agree, _ = attributes_agree(position.get("attrs") or {}, item["attrs"], keys, soft=tuple(keys))
	if not agree and out.fit == "exact":
		out.failures.append("product_attributes_disagree")
		return out
	out.product_id = pid
	if out.family is None:
		out.family = item["kind"]
	return out


def get_mapper(family_codes: list[str], cache_dir) -> PageMapper | None:
	"""A mapper when an LLM is configured, else None (rules only)."""
	config = get_config()
	return PageMapper(family_codes, cache_dir, config) if config else None
