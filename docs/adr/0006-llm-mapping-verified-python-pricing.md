# 0006 — LLM reads and maps, Python verifies and prices

Status: Proposed (implemented 2026-10-10). Supersedes 0001.

## Context
The goal is: upload a tender PDF, get a priced Excel. The only inputs are the PDF and the
central catalogue in the database. With rules alone, 224 of 439 Oberglatt positions stayed
unpriced; the LLM was only a fallback and had never run live.

## Decision
- The trade is recognised from the PDF (LV page headers of every Trade in master data); the
  estimator may still set it.
- The LLM reads every LV position and maps it to the catalogue: one request per page, with a
  shortlist of catalogue items from the database (same unit, the rules' family first) as an enum
  in a strict JSON schema. Any OpenAI-compatible endpoint (`llm_api_key`, `llm_base_url`,
  `llm_model`); Groq `openai/gpt-oss-120b` is the current one.
- Every answer is checked in Python (`llm_mapper.check`): quantity on the page, item offered, the
  sizes read from the position agree with the item. Failures are dropped and recorded.
- Rules and LLM are combined (`pipeline.combine`): agreement → calculated; LLM only → assumption
  (priced, provisional); disagreement with a certain rules match, or another quantity → review.
- The LLM never computes money. Prices are computed in Python from the catalogue; the quantity
  priced is the one printed in the PDF.
- The result is exported as an Excel workbook.

## Consequences
22/22 verified rows with LLM + rules. The provider sees the tender text (data-privacy decision
for Equans, recorded per Tender). Answers are cached per model, prompt version and page content,
so reruns and demos are free and repeatable; tests run offline with fake clients. The free Groq
tier (8k tokens/min) needs about 20 minutes for a 200-page tender the first time.
