### Equans Bid — AI tender pricing assistant

Upload a tender PDF, get a priced Excel workbook. The trade is recognised from the PDF, an LLM
reads every position and maps it to the central catalogue in the database, the rules cross-check
it, and every franc is computed **deterministically in Python** from the catalogue prices. The
estimator reviews and decides in the review UI (de-CH, fr-CH, en) and exports the result to Excel.

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

LLM (any OpenAI-compatible API; without a key the rules run alone):

```bash
bench --site equans.localhost set-config llm_api_key <key>
bench --site equans.localhost set-config llm_base_url https://api.groq.com/openai/v1   # omit for OpenAI
bench --site equans.localhost set-config llm_model openai/gpt-oss-120b                 # default: gpt-4o on OpenAI
```

The same can be given as `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` in the environment (used by the
benchmark CLI). The provider sees the tender text; it is recorded on every Tender (`processing_info`).
Tests never call the LLM.

#### The flow

1. **Upload** the tender PDF ("Neue Ausschreibung"). Leave the trade on "Automatisch erkennen".
2. **Trade**: recognised from the LV page headers (`244.01 LA01 … Seite 3/20` → HVAC).
3. **Positions**: the segmenter cuts the LV pages into positions (text + quantity column).
4. **LLM**, one request per page: quantity, unit, family and the catalogue item for each position,
   chosen from a shortlist of the catalogue in the database. Cached, so a rerun costs nothing.
5. **Checks** (Python): the quantity is on the page, the item was offered, its sizes (DN, W×H,
   thickness, angle) agree with the position. What fails is dropped and recorded.
6. **Decision**: LLM and rules agree → calculated; only the LLM finds an item → priced as an
   assumption; they disagree or the LLM read another quantity → review. The quantity priced is
   always the one printed in the PDF.
7. **Pricing** (Python, never the LLM): material = qty × net × (1 + waste); labour = qty × hours ×
   factors × rate; build-up, overhead, margin, bid range.
8. **Review** in `/estimator`, then **Excel export**: sheets Positions, Summary, Bid range, Open
   points, Assumptions, in the estimator's language.

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
| Trade detection | `extraction/pipeline.py` `detect_trade` | LV page headers of every Trade in master data |
| LLM mapping | `extraction/llm_mapper.py`, `verify.py` | one request per page, catalogue shortlist, strict JSON, verified, cached, never prices |
| Matching (rules) | `extraction/matcher.py` | family key attributes must agree; similarity only ranks |
| Rules + LLM | `extraction/pipeline.py` `combine` | agree → calculated; LLM only → assumption; disagree → review |
| Pricing | `pricing/engine.py` | material = qty × net × (1 + waste); hours = qty × base × factors |
| Project price | `pricing/project.py` | build-up, overhead, margin, Recommended Bid Range |
| API | `api.py` | process, edit, price snapshot + refresh, summary, assumptions, PDF, Excel/CSV export |
| Excel | `export.py` `build_xlsx` | amounts as numbers with CHF format, "—" for a missing price, translated sheets |
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

#### Generating synthetic tender packages

`equans_bid/tools/tender_package.py` builds a complete package in the format of the Equans starter
package (tender PDF, catalogue, productivity rules, project parameters, verified positions,
expected output, README, manifest) from a scenario JSON:

```bash
env/bin/python -m equans_bid.tools.tender_package \
  apps/equans_bid/equans_bid/data/scenarios/talacker_hvac.json <output folder>
```

A scenario lists systems (BKP code, LA, name) and positions: description lines, and per
variant the quantity line, unit, catalogue product and, for verified rows, the English golden
description. Page numbers come from the generator's own layout; golden values from the pricing
engine. Packages are labelled SYNTHETIC on every page; `tests/test_tender_package.py` checks the
format against the starter files and that the app finds and prices every verified row.

**Automatic generation.** `equans_bid/tools/scenario_generator.py` writes the scenarios itself
from the wording templates in `data/scenarios/templates/hvac.json` (one entry per product family:
LV text, quantity-line format, catalogue products, quantity range, golden description):

```bash
env/bin/python -m equans_bid.tools.scenario_generator --seed 1 --count 10 --systems 3 --out <folder>
```

Each seed is one reproducible tender (fictional school, systems, positions, distractors without
catalogue items, CAD duct list). Every package is self-checked: the rendered PDF must have the
planned pages, and the real pipeline must find and price every verified position, else the run
fails. Without `--out` the scenario is printed. More product families = more template entries.

#### Central catalogue and price snapshots

`Catalog Item` is one global master for all tenders (upserted by `product_id`, never duplicated).
Each priced position keeps a snapshot of net cost, hours, rate, factors and price version, so a
catalogue change does not move an existing tender. "Preise aktualisieren" previews the difference
(`preview_price_refresh`) and applies it on confirmation (`apply_price_refresh`).

#### Benchmark

```bash
cd apps/equans_bid && ../../env/bin/python -m equans_bid.extraction.benchmark [--all] [--strict] [--llm]
```

With `--llm` (key from `LLM_API_KEY`), the 22 verified rows are found with LLM and rules
combined: 22/22 strict with `openai/gpt-oss-120b` on Groq (10 requests, about 3 minutes on the
free tier; cached afterwards in `data/llm_cache/`).

`validate_extraction_against_benchmark()` finds each of the 22 verified rows by page, unit and
quantity (ties: expected install code, then sizes in the description). The PDF prints no LV IDs,
so `LV0001`… are assigned, not extracted. `--strict` also checks product and status.

#### License

MIT
