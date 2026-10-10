# Copyright (c) 2026, Ahmed Muhamed and contributors
# For license information, please see license.txt

import importlib
import json
import re

import frappe
from frappe import _
from frappe.model.document import Document


class Trade(Document):
	def validate(self):
		try:
			pattern = re.compile(self.system_header_pattern or "")
		except re.error as e:
			frappe.throw(_("System header pattern is not a valid regular expression: {0}").format(e))
		if self.system_header_pattern and "system" not in pattern.groupindex:
			frappe.throw(_("System header pattern needs a named group (?P<system>…)"))
		parsers = (
			json.loads(self.table_parsers)
			if isinstance(self.table_parsers, str) and self.table_parsers
			else []
		)
		for path in parsers or []:
			if not path.startswith("equans_bid.trades."):
				frappe.throw(_("Table parsers must live in equans_bid.trades: {0}").format(path))
			module = importlib.import_module(path)
			if not (hasattr(module, "is_table_page") and hasattr(module, "parse_page")):
				frappe.throw(_("Table parser {0} needs is_table_page() and parse_page()").format(path))
