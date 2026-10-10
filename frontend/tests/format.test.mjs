// node --test tests/   (expected strings checked against Node's Intl, ICU 78)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  MISSING,
  formatCHF,
  formatDate,
  formatNumber,
  formatPercent,
  formatQuantity,
  setFormatLocale,
} from '../src/utils/format.js'

const NBSP = '\u00a0'
const NNBSP = '\u202f' // narrow no-break space (fr-CH thousands separator)

const CASES = {
  'de-CH': { chf: `CHF${NBSP}414'489.12`, quantity: '6.964', percent: '63%', date: '10.10.2026' },
  'fr-CH': {
    chf: `414${NNBSP}489.12${NBSP}CHF`,
    quantity: '6,964',
    percent: '63%',
    date: '10 oct. 2026',
  },
  en: { chf: `CHF${NBSP}414,489.12`, quantity: '6.964', percent: '63%', date: 'Oct 10, 2026' },
}

for (const [locale, expected] of Object.entries(CASES)) {
  test(`formats 414489.12 CHF in ${locale}`, () => {
    setFormatLocale(locale)
    assert.equal(formatCHF(414489.12), expected.chf)
    assert.equal(formatQuantity(6.964), expected.quantity)
    assert.equal(formatPercent(0.63, { maxDigits: 0 }), expected.percent)
    assert.equal(formatDate('2026-10-10 12:00:00'), expected.date)
  })

  test(`a missing price is "—", never 0, in ${locale}`, () => {
    setFormatLocale(locale)
    for (const missing of [null, undefined, '', Number.NaN]) {
      assert.equal(formatCHF(missing), MISSING)
      assert.equal(formatNumber(missing), MISSING)
    }
    assert.notEqual(formatCHF(0), MISSING) // a real zero is still shown as an amount
  })
}

test('formatting never changes the value', () => {
  const golden = 806.26
  for (const locale of Object.keys(CASES)) {
    setFormatLocale(locale)
    const digits = formatCHF(golden).replace(/[^0-9]/g, '')
    assert.equal(digits, '80626', locale)
  }
  assert.equal(golden, 806.26)
})
