# 0002 — Data-driven matching with an attribute guard

Status: Proposed (implemented 2026-10-11)

## Context
Pure semantic similarity barely separates DN100 from DN125; a wrong size is a wrong price.

## Decision
The family comes from master data (Product Family patterns, or the LLM hint limited to those
codes). Every key attribute of the family must agree with the catalogue item; soft attributes and
size strategies are family data. Similarity (`Similarity` protocol, lexical by default) only ranks
candidates that already agree.

## Consequences
No product vocabulary in `extraction/` or `pricing/` (enforced by a deny-list test). An embedding
backend can be plugged in later without changing the guard.
