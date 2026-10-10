# Copyright (c) 2026, Ahmed Muhamed and contributors
# For license information, please see license.txt

import json
import re

import frappe
from frappe import _
from frappe.model.document import Document


def _list(value, field):
	data = json.loads(value) if isinstance(value, str) and value else (value or [])
	if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
		frappe.throw(_("{0} must be a list of attribute keys").format(field))
	return data


class ProductFamily(Document):
	def validate(self):
		for row in self.patterns or []:
			try:
				re.compile(row.pattern)
			except re.error as e:
				frappe.throw(_("Pattern {0} is not a valid regular expression: {1}").format(row.pattern, e))
		key = _list(self.key_attributes, "Key attributes")
		soft = _list(self.soft_attributes, "Soft attributes")
		if set(soft) - set(key):
			frappe.throw(_("Soft attributes must also be key attributes"))
		labels = (
			json.loads(self.labels) if isinstance(self.labels, str) and self.labels else (self.labels or {})
		)
		if not isinstance(labels, dict) or not labels.get("en"):
			frappe.throw(_("Labels need at least an English label"))
