import frappe


def after_install():
	"""Fresh site: roles, trades, families, catalogue and productivity rules from data/trades/."""
	from equans_bid.commands.seed_data import seed_parameters
	from equans_bid.setup.master_data import sync_all

	sync_all()
	seed_parameters()
	frappe.db.commit()
