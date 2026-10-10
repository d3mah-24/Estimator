// The one place that formats numbers, amounts, percentages and dates for display.
// All helpers use Intl with the current UI locale. Values stay numbers everywhere else;
// a missing value (null, undefined, '', NaN) shows MISSING, never 0.
import { ref } from 'vue'

export const MISSING = '—'

// Reactive, so computed values that format numbers re-run when the language changes.
const current = ref('de-CH')

export function setFormatLocale(locale) {
	current.value = locale
}

export function getFormatLocale() {
	return current.value
}

const cache = new Map()
function formatter(kind, options) {
	const key = `${current.value}|${kind}|${JSON.stringify(options)}`
	if (!cache.has(key)) {
		cache.set(
			key,
			kind === 'date'
				? new Intl.DateTimeFormat(current.value, options)
				: new Intl.NumberFormat(current.value, options)
		)
	}
	return cache.get(key)
}

function isMissing(value) {
	return value === null || value === undefined || value === '' || Number.isNaN(Number(value))
}

/** CHF amount, e.g. de-CH "CHF 414'489.12", fr-CH "414 489.12 CHF". */
export function formatCHF(value, { digits = 2 } = {}) {
	if (isMissing(value)) return MISSING
	return formatter('number', {
		style: 'currency',
		currency: 'CHF',
		minimumFractionDigits: digits,
		maximumFractionDigits: digits,
	}).format(Number(value))
}

/** Plain number with up to `maxDigits` decimals. */
export function formatNumber(value, { minDigits = 0, maxDigits = 2 } = {}) {
	if (isMissing(value)) return MISSING
	return formatter('number', {
		minimumFractionDigits: minDigits,
		maximumFractionDigits: maxDigits,
	}).format(Number(value))
}

/** Quantity from the tender (up to 3 decimals, e.g. 33.86 m or 6.964 m²). */
export function formatQuantity(value) {
	return formatNumber(value, { maxDigits: 3 })
}

/** A fraction as a percentage: 0.63 -> "63%" (Intl: same in de-CH, fr-CH and en). */
export function formatPercent(fraction, { maxDigits = 1 } = {}) {
	if (isMissing(fraction)) return MISSING
	return formatter('number', { style: 'percent', maximumFractionDigits: maxDigits }).format(
		Number(fraction)
	)
}

/** Date (string, number or Date), medium style by default. */
export function formatDate(value, options = { dateStyle: 'medium' }) {
	if (value === null || value === undefined || value === '') return MISSING
	const date =
		value instanceof Date
			? value
			: new Date(typeof value === 'string' ? value.replace(' ', 'T') : value)
	return Number.isNaN(date.getTime()) ? MISSING : formatter('date', options).format(date)
}
