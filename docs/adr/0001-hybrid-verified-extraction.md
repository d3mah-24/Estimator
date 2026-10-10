# 0001 — Hybrid, verified extraction

Status: Proposed (implemented 2026-10-11)

## Context
Tenders have ~200 pages. An LLM can structure free text well but can also invent a quantity.

## Decision
Rules find candidate blocks and remain the reference for quantity, unit and page. An optional LLM
(`extraction/structurer.py`) structures each block into a fixed contract (family hint,
custom attributes as printed). `extraction/verify.py` checks every field against the source; a
failed check is recorded, never silently used. Responses are cached per model, prompt/schema
version and block text.

## Consequences
Deterministic numbers, offline operation without an API key, repeatable tests. A quantity the LLM
reads differently from the rules sends the position to review (`llm_conflict`).
