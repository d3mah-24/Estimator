# 0003 — Benchmark criteria for the verified positions

Status: Proposed (implemented 2026-10-11)

## Context
The tender prints no LV IDs; `LV0001`… exist only in `example_lv_positions.csv`. Golden
descriptions are English, the tender German, so description similarity cannot be used.

## Decision
A golden row is found by page + unit + quantity; ties are broken by the expected install code of
the position's family, then by sizes stated in the golden description. `require_product=True`
also checks the matched product and status. The golden `lv_id` is assigned, not extracted.

## Consequences
22/22 in both modes; the benchmark tests what the PDF actually prints.
