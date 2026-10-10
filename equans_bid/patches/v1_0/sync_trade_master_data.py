from equans_bid.setup.master_data import sync_all


def execute():
	"""Trades and product families from data/trades/; catalogue family and attributes backfilled."""
	sync_all()
