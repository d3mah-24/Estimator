### Equans Bid — AI tender pricing assistant

Turns a ventilation tender (BKP 244, Schulhaus Oberglatt) into a traceable, reviewable first price.
The rules and the LLM only **extract**; every franc is computed **deterministically in Python**;
the estimator reviews and decides in a German review UI.

#### Run it

```bash
cd frappe-bench
bench start                                                    # web :8000, worker, redis
bench --site equans.localhost execute equans_bid.commands.demo.reset   # seed + demo tender + smoke check
```

Open `http://equans.localhost:8000/estimator` (log in to Frappe first).

Frontend development (hot reload on `:8080`):

```bash
bench --site equans.localhost set-config ignore_csrf 1   # dev server only, turn off again afterwards
cd apps/equans_bid/frontend && yarn dev                   # http://equans.localhost:8080/estimator
yarn build                                                # production build used on :8000
```

Optional GPT-4o fallback for positions the rules cannot classify:
`export OPENAI_API_KEY=...` or `bench --site equans.localhost set-config openai_api_key ...`.

#### Check it

```bash
bench --site equans.localhost run-tests --app equans_bid                   # golden + e2e tests
bench --site equans.localhost execute equans_bid.commands.demo.smoke       # pre-demo checklist
cd apps/equans_bid && ../../env/bin/python -m equans_bid.extraction.benchmark --all
uvx ruff@0.14.10 check equans_bid && uvx ruff@0.14.10 format --check equans_bid
```

#### How it works

| Step | Module | Notes |
| --- | --- | --- |
| Trade data | `trades/__init__.py`, `data/trades/<trade>/` | header pattern, families, attribute rules, plug-ins, factor rules |
| PDF text | `extraction/pdf_text.py` | pdfplumber, 1-based `source_page` |
| LV positions | `extraction/segmenter.py` | quantity lines (`Stk 5`), system from page header; footer wins on conflicts |
| Table plug-ins | `trades/hvac/component_list.py` | HVAC CAD lists ("Bauteilliste"); registered in trade.json |
| Family | `extraction/families.py` | Product Family patterns from master data, in priority order |
| Attributes | `extraction/attributes.py` | generic notation (Ø, DN, W×H) + trade rules; `custom_attributes` as printed |
| LLM (optional) | `extraction/structurer.py`, `verify.py` | strict contract, verified against the page, cached, never prices |
| Matching | `extraction/matcher.py` | family key attributes must agree; similarity only ranks |
| Pricing | `pricing/engine.py` | material = qty × net × (1 + waste); hours = qty × base × factors |
| Project price | `pricing/project.py` | build-up, overhead, margin, Recommended Bid Range |
| API | `api.py` | process, edit, price snapshot + refresh, summary, assumptions, PDF, CSV export |
| UI | `frontend/` | Vue 3 + frappe-ui, served at `/estimator` |

Design decisions are recorded in `docs/adr/`.

Golden reference: `data/starter/expected_output_example.json` (LV0001 = 806.26 CHF; subset baseline
414,489.12 CHF; scenarios 426k / 432k / 444k CHF) — all reproduced by `tests/test_pricing.py`.

Statuses: calculated, supplier_quote_required, assumption_applied, review_required,
insufficient_information, out_of_scope, non_priceable. A missing price never counts as CHF 0:
unpriced positions are counted and shown separately.

#### Localization (de-CH default, fr-CH, en fallback)

Rules: the database and API keep **codes** (statuses, units, scenarios, `reason_code` +
`reason_args`); text is produced only for display. Amounts stay numbers until formatted. Tender
text extracted from the PDF is never translated. The LLM prompt and schema stay English.

| Where | What |
| --- | --- |
| `frontend/src/locales/<locale>.json` | UI strings, plus labels for every code (`status.*`, `unit.*`, `reason.*`, `family.*`, …) |
| `frontend/src/utils/format.js` | the only place that formats numbers, CHF, percentages, dates (`Intl`); `—` for missing |
| `frontend/src/i18n.js` | vue-i18n setup, language switcher persistence (`localStorage`), `_lang` sent to the API |
| `equans_bid/reasons.py` | reason, warning and product-family codes with English templates |
| `equans_bid/localization.py` | backend labels (gettext contexts), babel formatting for exports |
| `equans_bid/locale/{de,fr}.po` | Frappe (gettext) translations; English is the source language |

Run `cd frontend && yarn test` to check that all locales have the same keys, placeholders and plural
forms, that every code has a label, and that no component formats numbers itself.

**Add a language** (example: Italian, `it-CH`):

1. `frontend/src/locales/it-CH.json`: copy `de-CH.json`, translate every value, keep placeholders
   like `{count}` and the ` | ` plural separators.
2. `frontend/src/i18n.js`: import it, add `{ code: 'it-CH', label: 'Italiano' }` to `LOCALES` and
   `'it-CH': 'it'` to `FRAPPE_LANG`; add `'it-CH'` to `OTHERS` in `frontend/tests/locales.test.mjs`.
3. `equans_bid/localization.py`: add `"it-CH": ("it", "it_CH")` to `UI_LOCALES`.
4. `equans_bid/locale/it.po`: copy `de.po`, set `Language: it`, translate every `msgstr`
   (keep each `msgctxt`); add `"it"` to the loop in `tests/test_localization.py`.
5. `bench compile-po-to-mo --app equans_bid && bench --site equans.localhost clear-cache`,
   `cd frontend && yarn test && yarn build`, `bench run-tests --app equans_bid`.

#### Adding a trade (no code changes)

1. Create `equans_bid/data/trades/<trade>/` with
   - `trade.json`: code, labels, LV page header regex (named group `system`), attribute labels
     (printed column labels kept as `custom_attributes`), attribute rules (text → canonical keys),
     optional table-parser plug-ins and factor rules, and the catalogue/productivity file names;
   - `families.json`: families with labels in de-CH / fr-CH / en, recognition patterns, key and
     soft attributes, size strategy;
   - `catalog.csv` (with `family` and `attributes` columns) and `productivity.csv`.
2. `bench --site equans.localhost execute equans_bid.commands.seed_data.run` (idempotent upsert).
3. Create a tender with that trade and upload its PDF.

`data/trades/electrical/` is a complete, **synthetic** example (rebuild its PDF with
`sample/build_pdf.py`); `tests/test_trades.py` proves it is priced with no code change.

#### Central catalogue and price snapshots

`Catalog Item` is one global master for all tenders (upserted by `product_id`, never duplicated).
Each priced position keeps a snapshot of net cost, hours, rate, factors and price version, so a
catalogue change does not move an existing tender. "Preise aktualisieren" previews the difference
(`preview_price_refresh`) and applies it on confirmation (`apply_price_refresh`).

#### Benchmark

```bash
cd apps/equans_bid && ../../env/bin/python -m equans_bid.extraction.benchmark [--all] [--strict] [--llm]
```

`validate_extraction_against_benchmark()` finds each of the 22 verified rows by page, unit and
quantity (ties: expected install code, then sizes in the description). The PDF prints no LV IDs,
so `LV0001`… are assigned, not extracted. `--strict` also checks product and status.

#### License

MIT
