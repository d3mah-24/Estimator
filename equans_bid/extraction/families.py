"""Recognise a position's product family from the trade's family data (no vocabulary in code).

Families are tried in priority order; each family's patterns are regular expressions on the
lower-cased title, then the quantity-line label, then the block text — the first hit wins.
"""

import re

from equans_bid.trades import TradeConfig


class FamilyClassifier:
	def __init__(self, trade: TradeConfig):
		self.rules = [
			(f.code, re.compile("|".join(f"(?:{p})" for p in f.patterns)))
			for f in sorted(trade.families, key=lambda f: (f.priority, f.code))
			if f.patterns
		]

	def classify(self, title: str, text: str, label: str = "") -> str | None:
		for haystack in (title.lower(), label.lower(), text.lower()):
			for code, pattern in self.rules:
				if pattern.search(haystack):
					return code
		return None

	def pick_title(self, block_lines: list[str]) -> str | None:
		"""The first block line that names a family, else None (the segmenter uses line 1)."""
		for line in block_lines:
			if self.classify(line, ""):
				return line
		return None
