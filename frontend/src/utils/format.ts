// Swiss formatting and German labels for the estimator UI.

export function chf(value: number | null | undefined, digits = 2): string {
  const n = Number(value || 0)
  return `CHF ${n.toLocaleString('de-CH', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('de-CH', { maximumFractionDigits: digits })
}

export function pct(value: number | null | undefined): string {
  return `${Math.round(Number(value || 0) * 100)} %`
}

type Theme = 'gray' | 'blue' | 'green' | 'orange' | 'red'

export const STATUS: Record<string, { label: string; theme: Theme; priced: boolean }> = {
  calculated: { label: 'Berechnet', theme: 'green', priced: true },
  supplier_quote_required: { label: 'Offerte nötig', theme: 'orange', priced: true },
  assumption_applied: { label: 'Annahme', theme: 'blue', priced: true },
  review_required: { label: 'Prüfung nötig', theme: 'red', priced: false },
  insufficient_information: { label: 'Angaben fehlen', theme: 'red', priced: false },
  out_of_scope: { label: 'Ausser Umfang', theme: 'gray', priced: false },
  non_priceable: { label: 'Nicht kalkulierbar', theme: 'gray', priced: false },
}

export const UNIT: Record<string, string> = { pc: 'Stk', m: 'm', m2: 'm²', m3: 'm³', h: 'Std', LS: 'psch', system: 'Anlage' }

export const TENDER_STATUS: Record<string, { label: string; theme: Theme }> = {
  Draft: { label: 'Entwurf', theme: 'gray' },
  Processing: { label: 'In Verarbeitung', theme: 'blue' },
  Completed: { label: 'Bereit zur Prüfung', theme: 'green' },
  Failed: { label: 'Fehlgeschlagen', theme: 'red' },
}

export const SCENARIO: Record<string, string> = {
  Aggressive: 'Aggressiv',
  Target: 'Zielmarge',
  Conservative: 'Konservativ',
}
