// Master data the UI labels with: product families and trades. Labels come from the
// database (Product Family / Trade `labels`), in the current UI locale, English as fallback.
import { createListResource, createResource } from 'frappe-ui'
import { currentLocale } from '@/i18n'

export const familyLabels = createResource({
	url: 'equans_bid.api.family_labels',
	cache: 'equans_bid.family_labels',
	auto: true,
})

export const trades = createListResource({
	doctype: 'Trade',
	fields: ['name', 'labels'],
	orderBy: 'name asc',
	cache: 'equans_bid.trades',
	auto: true,
})

function pick(labels, fallback) {
	let value = labels
	if (typeof value === 'string') {
		try {
			value = JSON.parse(value)
		} catch {
			value = {}
		}
	}
	return value?.[currentLocale()] || value?.en || fallback || ''
}

export function familyLabel(code) {
	return code ? pick(familyLabels.data?.[code], code) : ''
}

export function tradeLabel(code) {
	const row = (trades.data || []).find((t) => t.name === code)
	return pick(row?.labels, code)
}
