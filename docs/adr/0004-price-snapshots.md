# 0004 — Central catalogue with price snapshots per tender

Status: Proposed (implemented 2026-10-11)

## Context
`Catalog Item` is one global master. An offer must not change silently when a catalogue price
changes.

## Decision
When a position is first priced (or its product changes) its net cost, hours, rate, factors and
price version are copied onto the Tender Item. Recalculation uses the snapshot.
`preview_price_refresh` shows the difference to today's catalogue; `apply_price_refresh` applies it.

## Consequences
Old tenders are stable; a refresh is explicit and auditable (`catalog_priced_at`, `price_version`).
