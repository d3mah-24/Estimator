# Copyright (c) 2026, Ahmed Muhamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

MAX_PDF_BYTES = 50 * 1024 * 1024


class Tender(Document):
	def validate(self):
		if self.tender_file and (self.is_new() or self.has_value_changed("tender_file")):
			self.validate_tender_file()

	def validate_tender_file(self):
		"""Server-side check (the browser check can be bypassed): a real PDF, size-limited."""
		name = frappe.db.get_value("File", {"file_url": self.tender_file})
		if not name:
			frappe.throw(_("Tender file {0} not found").format(self.tender_file))
		path = frappe.get_doc("File", name).get_full_path()
		with open(path, "rb") as fh:
			head = fh.read(5)
			fh.seek(0, 2)
			size = fh.tell()
		if head != b"%PDF-":
			frappe.throw(_("The tender file must be a PDF"))
		if size > MAX_PDF_BYTES:
			frappe.throw(_("The tender file is larger than {0} MB").format(MAX_PDF_BYTES // (1024 * 1024)))
