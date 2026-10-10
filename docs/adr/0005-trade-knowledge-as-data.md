# 0005 — Trade knowledge as master data

Status: Proposed (implemented 2026-10-11)

## Context
HVAC knowledge was spread over code (keyword rules, parsers, exceptions, a sports-hall factor).

## Decision
A trade is `data/trades/<trade>/` (trade.json, families.json, catalogue, productivity rules),
loaded into the `Trade` and `Product Family` DocTypes. Table parsers are plug-ins under
`equans_bid.trades.<trade>`, named in trade.json. Factor substitutions are trade data.

## Consequences
A new trade is onboarded without code changes — proven by the synthetic electrical sample. Known
limit: project parameters (project costs, factors) are still one record per site, not per tender.
