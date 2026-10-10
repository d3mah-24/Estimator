import frappe


def execute():
	"""Tenders created before trades existed are ventilation (HVAC) tenders."""
	frappe.db.sql("update `tabTender` set trade = 'HVAC' where ifnull(trade, '') = ''")
