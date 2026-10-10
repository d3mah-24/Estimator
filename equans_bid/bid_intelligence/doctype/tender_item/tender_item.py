# Copyright (c) 2026, Ahmed Muhamed and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

MAX_CUSTOM_KEYS = 30
MAX_VALUE_LENGTH = 200


class TenderItem(Document):
	def validate(self):
		self.validate_custom_attributes()

	def validate_custom_attributes(self):
		"""Contract: {"<label as printed>": "<value as printed>"}, at most 30 keys of 200 chars."""
		if not self.custom_attributes:
			return
		value = self.custom_attributes
		data = json.loads(value) if isinstance(value, str) else value
		if not isinstance(data, dict):
			frappe.throw(_("Custom attributes must be an object of label: value"))
		if len(data) > MAX_CUSTOM_KEYS:
			frappe.throw(_("At most {0} custom attributes per position").format(MAX_CUSTOM_KEYS))
		clean = {}
		for label, text in data.items():
			if not isinstance(label, str) or not isinstance(text, str | int | float):
				frappe.throw(_("Custom attribute {0} must be text").format(label))
			clean[label[:80]] = str(text)[:MAX_VALUE_LENGTH]
		self.custom_attributes = json.dumps(clean, ensure_ascii=False)
