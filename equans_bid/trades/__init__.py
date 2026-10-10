"""Trade configuration: everything trade-specific is data, loaded from files or from Frappe.

A trade (HVAC, Electrical, …) is described by
	data/trades/<trade>/trade.json      header pattern, attribute labels and rules, table
	                                    parsers, factor rules, catalogue/productivity files
	data/trades/<trade>/families.json   product families: labels, recognition patterns,
	                                    key/soft attributes, size strategy, catalogue mapping

The same structures are built from the `Trade` and `Product Family` DocTypes (`from_documents`),
so the pipeline runs identically from files (tests, benchmark) and from the database (app).
No module in this package names a product: that knowledge is in the data files.
"""

import csv
import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TRADES_DIR = Path(__file__).resolve().parent.parent / "data" / "trades"
_FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE}


def _flags(spec: str | None) -> int:
	out = 0
	for ch in spec or "":
		out |= _FLAGS.get(ch, 0)
	return out


@dataclass
class Family:
	code: str
	priority: int = 1000
	labels: dict = field(default_factory=dict)
	patterns: list = field(default_factory=list)
	key_attributes: list = field(default_factory=list)
	soft_attributes: list = field(default_factory=list)
	size_strategy: str = "exact"
	catalog_match: list = field(default_factory=list)

	def label(self, locale: str) -> str:
		return self.labels.get(locale) or self.labels.get("en") or self.code


@dataclass
class TradeConfig:
	code: str
	families: list[Family]
	labels: dict = field(default_factory=dict)
	system_header_pattern: str = r"(?P<system>\d{3}\.\d+\s+\S.*?)\s+Seite\s+\d+\s*/\s*\d+"
	continuation_labels: list = field(default_factory=list)
	attribute_labels: list = field(default_factory=list)
	attribute_rules: list = field(default_factory=list)
	catalog_attribute_rules: list = field(default_factory=list)
	table_parsers: list = field(default_factory=list)
	factor_rules: list = field(default_factory=list)
	catalog_file: Path | None = None
	productivity_file: Path | None = None

	@property
	def family_map(self) -> dict[str, Family]:
		return {f.code: f for f in self.families}

	@property
	def system_header(self) -> re.Pattern:
		return re.compile(self.system_header_pattern)

	def parsers(self) -> list:
		"""Table-parser plug-ins: modules with is_table_page(text) and parse_page(n, text, system)."""
		return [importlib.import_module(path) for path in self.table_parsers]


def _family(d: dict) -> Family:
	return Family(
		code=d["code"],
		priority=int(d.get("priority", 1000)),
		labels=d.get("labels") or {},
		patterns=list(d.get("patterns") or []),
		key_attributes=list(d.get("key_attributes") or []),
		soft_attributes=list(d.get("soft_attributes") or []),
		size_strategy=d.get("size_strategy") or "exact",
		catalog_match=list(d.get("catalog_match") or []),
	)


def _trade(d: dict, families: list[Family], base: Path | None = None) -> TradeConfig:
	def path(key):
		return (base / d[key]).resolve() if base and d.get(key) else None

	return TradeConfig(
		code=d["code"],
		families=sorted(families, key=lambda f: (f.priority, f.code)),
		labels=d.get("labels") or {},
		system_header_pattern=d.get("system_header_pattern") or TradeConfig.system_header_pattern,
		continuation_labels=list(d.get("continuation_labels") or []),
		attribute_labels=list(d.get("attribute_labels") or []),
		attribute_rules=list(d.get("attribute_rules") or []),
		catalog_attribute_rules=list(d.get("catalog_attribute_rules") or []),
		table_parsers=list(d.get("table_parsers") or []),
		factor_rules=list(d.get("factor_rules") or []),
		catalog_file=path("catalog"),
		productivity_file=path("productivity"),
	)


def available_trades() -> list[str]:
	return sorted(p.name for p in TRADES_DIR.iterdir() if (p / "trade.json").exists())


def load_trade(code: str = "HVAC") -> TradeConfig:
	"""Trade config from data/trades/<code>/ (folder name is the code in lower case)."""
	base = TRADES_DIR / code.lower()
	trade = json.loads((base / "trade.json").read_text())
	families = json.loads((base / "families.json").read_text())["families"]
	return _trade(trade, [_family(f) for f in families], base)


def from_documents(trade_doc, family_docs) -> TradeConfig:
	"""Trade config from Frappe docs (Trade + its Product Family rows)."""

	def js(value):
		if not value:
			return None
		return json.loads(value) if isinstance(value, str) else value

	families = [
		_family(
			{
				"code": f.family_code,
				"priority": f.priority,
				"labels": js(f.labels),
				"patterns": [p.pattern for p in (f.patterns or []) if p.pattern],
				"key_attributes": js(f.key_attributes),
				"soft_attributes": js(f.soft_attributes),
				"size_strategy": f.size_strategy,
				"catalog_match": js(f.catalog_match),
			}
		)
		for f in family_docs
	]
	data = {
		"code": trade_doc.trade_code,
		"labels": js(trade_doc.labels),
		"system_header_pattern": trade_doc.system_header_pattern,
		"continuation_labels": js(trade_doc.continuation_labels),
		"attribute_labels": js(trade_doc.attribute_labels),
		"attribute_rules": js(trade_doc.attribute_rules),
		"catalog_attribute_rules": js(trade_doc.catalog_attribute_rules),
		"table_parsers": js(trade_doc.table_parsers),
		"factor_rules": js(trade_doc.factor_rules),
	}
	return _trade(data, families)


def apply_rule(rule: dict, text: str):
	"""Value of one attribute rule on `text`: int/float from the first non-empty group, or True."""
	m = re.search(rule["pattern"], text, _flags(rule.get("flags")))
	if not m:
		return None
	kind = rule.get("type", "text")
	if kind == "flag":
		return True
	value = next((g for g in m.groups() if g), m.group(0))
	if kind == "int":
		return int(float(value.replace(",", ".")))
	if kind == "float":
		return float(value.replace(",", "."))
	return value.strip()


def catalog_family(row: dict, trade: TradeConfig) -> str | None:
	"""Family of a catalogue row: an explicit `family` column wins, else the families' catalog_match
	rules (specific rules with description_contains first)."""
	if row.get("family"):
		return row["family"]
	rules = [(f.code, r) for f in trade.families for r in f.catalog_match]
	rules.sort(key=lambda fr: 0 if fr[1].get("description_contains") else 1)
	for code, rule in rules:
		if rule.get("subcategory") and rule["subcategory"] != row.get("subcategory"):
			continue
		phrase = rule.get("description_contains")
		if phrase and phrase.lower() not in (row.get("description") or "").lower():
			continue
		return code
	return None


def read_catalog(trade: TradeConfig) -> list[dict]:
	with open(trade.catalog_file, newline="") as fh:
		rows = list(csv.DictReader(fh))
	for r in rows:
		r["supplier_quote_required"] = str(r.get("supplier_quote_required", "")).lower() in (
			"true",
			"1",
			"yes",
		)
	return rows


def read_productivity(trade: TradeConfig) -> list[dict]:
	with open(trade.productivity_file, newline="") as fh:
		return list(csv.DictReader(fh))
