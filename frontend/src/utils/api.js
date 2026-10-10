import { call } from 'frappe-ui'
import { frappeLang } from '@/i18n'

/** Whitelisted method call that asks the backend to answer in the UI language (_lang). */
export function api(method, params = {}) {
	return call(method, { ...params, _lang: frappeLang() })
}

/** Text of an API error, already translated by the backend when it can be. */
export function errorText(e, fallback) {
	return e?.messages?.join(', ') || e?.message || fallback
}
