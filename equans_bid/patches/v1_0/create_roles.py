from equans_bid.setup.master_data import ensure_roles


def execute():
	"""Roles referenced by the DocType permissions must exist before the model sync."""
	ensure_roles()
