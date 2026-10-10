// Codes the backend stores and returns. Labels come from the locale files
// (status.<code>, unit.<code>, …); only presentation metadata lives here.

/** Tender Item statuses, in display order. `priced`: the position carries a price.
 *  `theme`/`icon`: StatusPill; `bar`: the coloured left edge of a table row. */
export const STATUS = {
	calculated: { theme: 'green', priced: true, icon: 'check-circle', bar: 'border-l-green-500' },
	supplier_quote_required: {
		theme: 'orange',
		priced: true,
		icon: 'inbox',
		bar: 'border-l-amber-500',
	},
	assumption_applied: {
		theme: 'blue',
		priced: true,
		icon: 'help-circle',
		bar: 'border-l-blue-500',
	},
	review_required: {
		theme: 'red',
		priced: false,
		icon: 'alert-triangle',
		bar: 'border-l-red-500',
	},
	insufficient_information: {
		theme: 'red',
		priced: false,
		icon: 'alert-octagon',
		bar: 'border-l-red-500',
	},
	out_of_scope: { theme: 'gray', priced: false, icon: 'slash', bar: 'border-l-gray-300' },
	non_priceable: { theme: 'gray', priced: false, icon: 'minus-circle', bar: 'border-l-gray-300' },
}

/** Quick filters over the table: groups of statuses the estimator works through. */
export const STATUS_GROUPS = [
	{
		key: 'open',
		statuses: ['review_required', 'insufficient_information'],
		theme: 'red',
		icon: 'alert-triangle',
	},
	{ key: 'quote', statuses: ['supplier_quote_required'], theme: 'orange', icon: 'inbox' },
	{ key: 'assumption', statuses: ['assumption_applied'], theme: 'blue', icon: 'help-circle' },
	{ key: 'calculated', statuses: ['calculated'], theme: 'green', icon: 'check-circle' },
	{ key: 'excluded', statuses: ['out_of_scope', 'non_priceable'], theme: 'gray', icon: 'slash' },
]
export const STATUS_CODES = Object.keys(STATUS)

export const UNIT_CODES = ['pc', 'm', 'm2', 'm3', 'h', 'LS', 'system']

export const TENDER_STATUS = {
	Draft: { theme: 'gray' },
	Processing: { theme: 'blue' },
	Completed: { theme: 'green' },
	Failed: { theme: 'red' },
}
export const TENDER_ICON = {
	Draft: 'edit-3',
	Processing: 'loader',
	Completed: 'check-circle',
	Failed: 'x-circle',
}

export const SCENARIO_CODES = ['Aggressive', 'Target', 'Conservative']

export const PRICE_SOURCE_CODES = ['catalog', 'supplier_package', 'supplier_quote']
