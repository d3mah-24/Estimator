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
| PDF text | `extraction/pdf_text.py` | pdfplumber, 1-based `source_page` |
| LV positions | `extraction/segmenter.py` | quantity lines (`Stk 5`), system from page header; footer wins on conflicts |
| Ductwork | `extraction/componentlist.py` | CAD lists ("Bauteilliste"): lengths → m, rectangular area = perimeter × length |
| Family + size | `extraction/classify.py` | German keyword rules, sizes in mm |
| LLM fallback | `extraction/llm.py` | GPT-4o strict JSON schema, family + sizes only, cached, never prices |
| Matching | `extraction/matcher.py` | size must agree; similarity only ranks agreeing items |
| Pricing | `pricing/engine.py` | material = qty × net × (1 + waste); hours = qty × base × factors |
| Project price | `pricing/project.py` | build-up, overhead, margin, Recommended Bid Range |
| API | `api.py` | process, edit one row, summary, assumptions, PDF, CSV export |
| UI | `frontend/` | Vue 3 + frappe-ui, served at `/estimator` |

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

#### Extending to another trade

Swap `data/starter/catalog.csv`, `productivity.csv` and `project_parameters.json`, add the trade's
keyword families in `extraction/classify.py`, run `commands.seed_data.run`. Pricing, review UI,
bid range and export are trade-neutral.

#### License

MIT
