from equans_bid.commands.seed_data import seed_parameters


def execute():
	"""Sites that got the app without after_install (restored database, failed install) have no
	project parameters, and every price calculation stops. Fill them in; never overwrite."""
	seed_parameters(only_if_missing=True)
