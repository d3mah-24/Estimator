// node --test tests/
// Fails when a locale misses a key, a code has no label, placeholders or plural forms differ,
// a message does not compile, or code formats numbers outside src/utils/format.js.
import { baseCompile } from '@intlify/message-compiler'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import { STATUS_CODES, UNIT_CODES, SCENARIO_CODES, PRICE_SOURCE_CODES, TENDER_STATUS } from '../src/utils/codes.js'

const root = new URL('..', import.meta.url).pathname
const load = (code) => JSON.parse(readFileSync(join(root, 'src/locales', `${code}.json`), 'utf8'))
const REFERENCE = 'de-CH'
const OTHERS = ['fr-CH', 'en']
const locales = Object.fromEntries([REFERENCE, ...OTHERS].map((c) => [c, load(c)]))

function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object') flatten(v, key, out)
    else out[key] = v
  }
  return out
}
const flat = Object.fromEntries(Object.entries(locales).map(([c, m]) => [c, flatten(m)]))
const placeholders = (msg) => [...new Set([...String(msg).matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort()
const pluralForms = (msg) => String(msg).split(' | ').length

for (const code of OTHERS) {
  test(`${code} has every key of ${REFERENCE}, and no extra keys`, () => {
    const missing = Object.keys(flat[REFERENCE]).filter((k) => !(k in flat[code]))
    const extra = Object.keys(flat[code]).filter((k) => !(k in flat[REFERENCE]))
    assert.deepEqual(missing, [], `missing in ${code}`)
    assert.deepEqual(extra, [], `extra in ${code}`)
  })

  test(`${code} keeps the placeholders and plural forms of ${REFERENCE}`, () => {
    for (const [key, ref] of Object.entries(flat[REFERENCE])) {
      assert.deepEqual(placeholders(flat[code][key]), placeholders(ref), `${code} ${key}`)
      assert.equal(pluralForms(flat[code][key]), pluralForms(ref), `${code} ${key} plural forms`)
    }
  })
}

test('every message compiles (no stray braces, @ or |)', () => {
  for (const [code, messages] of Object.entries(flat)) {
    for (const [key, msg] of Object.entries(messages)) {
      const errors = []
      baseCompile(String(msg), { onError: (e) => errors.push(e.message) })
      assert.deepEqual(errors, [], `${code} ${key}`)
      assert.ok(!String(msg).includes('@'), `${code} ${key}: '@' starts a linked message in vue-i18n`)
    }
  }
})

test('every status, unit, scenario, price source and tender status code has a label', () => {
  const groups = {
    status: STATUS_CODES,
    unit: UNIT_CODES,
    scenario: SCENARIO_CODES,
    priceSource: PRICE_SOURCE_CODES,
    tenderStatus: Object.keys(TENDER_STATUS),
  }
  for (const [code, messages] of Object.entries(locales)) {
    for (const [group, codes] of Object.entries(groups)) {
      for (const c of codes) assert.ok(messages[group]?.[c], `${code}: ${group}.${c}`)
    }
  }
})

test('frontend codes match the backend (doctype options, reasons, families)', () => {
  const app = join(root, '..', 'equans_bid')
  const doctype = JSON.parse(readFileSync(join(app, 'bid_intelligence/doctype/tender_item/tender_item.json'), 'utf8'))
  const statusOptions = doctype.fields.find((f) => f.fieldname === 'status').options.split('\n')
  assert.deepEqual([...statusOptions].sort(), [...STATUS_CODES].sort())
  const tenderDoctype = JSON.parse(readFileSync(join(app, 'bid_intelligence/doctype/tender/tender.json'), 'utf8'))
  const tenderOptions = tenderDoctype.fields.find((f) => f.fieldname === 'status').options.split('\n')
  assert.deepEqual([...tenderOptions].sort(), Object.keys(TENDER_STATUS).sort())

  const reasons = readFileSync(join(app, 'reasons.py'), 'utf8')
  const block = (name) => reasons.slice(reasons.indexOf(`${name} = {`), reasons.indexOf('\n}', reasons.indexOf(`${name} = {`)))
  const keysOf = (name) => [...block(name).matchAll(/^\t"(\w+)":/gm)].map((m) => m[1])
  for (const [name, group] of [['REASONS', 'reason'], ['WARNINGS', 'warning'], ['FAMILIES', 'family']]) {
    const backend = keysOf(name)
    assert.ok(backend.length > 0, name)
    assert.deepEqual(backend.sort(), Object.keys(locales[REFERENCE][group]).sort(), `${name} vs ${group}.*`)
  }
})

test('no number formatting outside src/utils/format.js', () => {
  const offenders = []
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name)
      if (statSync(path).isDirectory()) walk(path)
      else if (/\.(vue|js|ts)$/.test(name) && !path.endsWith(join('utils', 'format.js'))) {
        const src = readFileSync(path, 'utf8')
        if (/toLocaleString\(|new Intl\./.test(src)) offenders.push(path)
      }
    }
  }
  walk(join(root, 'src'))
  assert.deepEqual(offenders, [])
})
