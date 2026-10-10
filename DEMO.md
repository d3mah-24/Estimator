# Demo script (5 minutes)

**Before going on stage**

1. `bench start` is running.
2. `bench --site equans.localhost execute equans_bid.commands.demo.reset` → must end with `14/14 checks passed`.
3. Browser logged in, at `http://equans.localhost:8000/estimator`, zoom 90 %.
4. Fallback if anything fails live: the demo tender is already processed; skip the upload and open it.

Rehearsed twice end to end in headless Chrome on 10 Oct 2026: no errors, every click < 1.3 s.

---

**0:00 — The problem (no screen)**
An estimator gets a 202-page tender. Today they hunt for positions, products and prices across files.
We let the tool do the groundwork; the expert makes the call.

**0:30 — Upload** (`Neue Ausschreibung`)
Upload `BKP_244_LV_Lueftung_260804.pdf`. ~20 s later: 439 positions, 6 systems, every one with a status.
*If short on time:* open the pre-processed tender instead.

**1:00 — One position, end to end** (search `LV0001`)
- Click the row: the PDF jumps to page 78 and highlights "Ø 10 cm … Stk 5".
- Detail panel: 5 Stk, matched to P-AIR-001 because family *and* DN100 agree.
- Breakdown: 5 × CHF 74.80 + 4 % waste = CHF 388.96; 4.35 h × CHF 96 = CHF 417.30; **CHF 806.26** —
  exactly the Equans reference. The LLM never touches money.

**2:00 — Human control** (search `LV0006`)
- Silencer is a supplier package: priced provisionally from the catalogue, flagged orange.
- Type the supplier quote `9000` → saved and repriced in ~100 ms; totals and bid cards move.
- Search `P079-02`: DN125 exhaust valve, the catalogue only has DN100 → "Prüfung nötig".
  The estimator decides to price it as P-AIR-003; the reason now says "Produkt durch Kalkulator gesetzt".

**3:00 — Honesty about uncertainty**
- KPI row: confirmed vs provisional vs 224 positions without a price — never silently CHF 0.
- Filter `Annahme`: rectangular ducts priced at the nearest catalogue size class, the class is named.
- Select a Turnhalle position (filter system 244.05): the tool found a **contradiction in the tender** —
  pages headed "244.03 Küche" are in the Turnhalle source document.

**3:45 — The bid decision** (`Kostenaufbau`, then `Annahmen`)
- Build-up: material, packages, labour, small material, reserve, project costs → overhead → baseline.
- Three scenarios with price, margin, win probability and expected contribution; Konservativ recommended.
- Set *Wettbewerb* to −15 Pp.: probabilities drop live — the trade-off is visible and editable.

**4:30 — Take it away**
`Export (CSV)` opens in Excel with every position, source page, reason, build-up and scenarios.
Scalability: new trade = new catalogue + productivity CSV + keyword families. Same UI, same engine.

**After the demo**: `demo.reset` again to clear the quote and the product change.
