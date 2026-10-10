import { createI18n } from 'vue-i18n'
import deCH from './locales/de-CH.json'
import en from './locales/en.json'
import frCH from './locales/fr-CH.json'
import { setFormatLocale } from './utils/format.js'

// To add a language: add src/locales/<code>.json with every key of de-CH.json, list it here
// and in FRAPPE_LANG, and add equans_bid/locale/<lang>.po for the backend (see README).
export const LOCALES = [
  { code: 'de-CH', label: 'Deutsch' },
  { code: 'fr-CH', label: 'Français' },
  { code: 'en', label: 'English' },
]
export const DEFAULT_LOCALE = 'de-CH'

// UI locale -> Frappe language (sent as _lang so API messages match the UI).
const FRAPPE_LANG = { 'de-CH': 'de', 'fr-CH': 'fr', en: 'en' }
const STORAGE_KEY = 'equans_bid.locale'

function storedLocale() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return LOCALES.some((l) => l.code === value) ? value : null
  } catch {
    return null // private mode, blocked storage
  }
}

const initial = storedLocale() || DEFAULT_LOCALE

export const i18n = createI18n({
  legacy: false,
  locale: initial,
  fallbackLocale: 'en',
  messages: { 'de-CH': deCH, 'fr-CH': frCH, en },
})

function apply(code) {
  setFormatLocale(code)
  document.documentElement.lang = code
}
apply(initial)

export function setLocale(code) {
  if (!LOCALES.some((l) => l.code === code)) return
  i18n.global.locale.value = code
  apply(code)
  try {
    window.localStorage.setItem(STORAGE_KEY, code)
  } catch {
    // not persisted; the choice still applies for this visit
  }
}

export function currentLocale() {
  return i18n.global.locale.value
}

export function frappeLang() {
  return FRAPPE_LANG[i18n.global.locale.value] || 'en'
}
