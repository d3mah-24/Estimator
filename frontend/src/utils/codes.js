// Codes the backend stores and returns. Labels come from the locale files
// (status.<code>, unit.<code>, …); only presentation metadata lives here.

/** Tender Item statuses, in display order. `priced`: the position carries a price. */
export const STATUS = {
  calculated: { theme: 'green', priced: true },
  supplier_quote_required: { theme: 'orange', priced: true },
  assumption_applied: { theme: 'blue', priced: true },
  review_required: { theme: 'red', priced: false },
  insufficient_information: { theme: 'red', priced: false },
  out_of_scope: { theme: 'gray', priced: false },
  non_priceable: { theme: 'gray', priced: false },
}
export const STATUS_CODES = Object.keys(STATUS)

export const UNIT_CODES = ['pc', 'm', 'm2', 'm3', 'h', 'LS', 'system']

export const TENDER_STATUS = {
  Draft: { theme: 'gray' },
  Processing: { theme: 'blue' },
  Completed: { theme: 'green' },
  Failed: { theme: 'red' },
}

export const SCENARIO_CODES = ['Aggressive', 'Target', 'Conservative']

export const PRICE_SOURCE_CODES = ['catalog', 'supplier_package', 'supplier_quote']
