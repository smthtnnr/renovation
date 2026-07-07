# bidcompare — force GC bids into your estimator's taxonomy

A Python CLI that takes a general contractor's renovation bid (PDF) and compares it,
line by line, against **your** estimate — the one the [Reno Budget Estimator](../README.md)
produces. It's built to answer the question a price total can't: *what did this bid
leave out?*

The estimator's pricing model (`REGIONS` in `../index.html`) is the **canonical
taxonomy** — the spine every bid is forced onto. Trade → item → unit → your unit cost.

## The pipeline

```
 index.html REGIONS ──(node)──▶ taxonomy.json          the spine (trade→item→unit→cost)
        bid.pdf ──(Claude)────▶ extracted lines         each with a VERBATIM quote (provenance)
                 ──(Claude)────▶ exclusions registry     exclusions / allowances / by-owner / TBD
 taxonomy + lines ─(Claude)────▶ mapping                 mapped · extra · unallocatable + confidence
 estimate + mapping ─(Python)──▶ variance report         missing-first, sorted by $ impact, flagged
   many reports ──(Python)─────▶ calibration             where independent GCs say YOU are mispriced
```

Claude does extraction and mapping (judgment); Python does variance and calibration
(deterministic, testable, no API key).

## Why it's built this way — the risks it defends against

- **Silent scope gaps.** A bid that maps "cleanly" but omits your sewer/roof/electrical
  line looks like a good bid. The **missing** bucket is rendered *first and loudest* in
  every report, and Major-System gaps are flagged 🔴. Missing is computed in Python from
  what actually mapped — Claude can't hallucinate coverage that isn't there.
- **Your pricing sheet isn't market truth.** If three independent GCs all come in 30%
  over your paint number, the tool flags **your estimator** for recalibration, not the
  GCs for gouging (`calibrate`). The sheet gets truer with every bid you process.
- **Lump-sum ambiguity.** "Kitchen: $42,000" spanning cabinets, counters, plumbing, and
  electrical can't be honestly decomposed. Claude doesn't guess a split — it marks the
  line **unallocatable** and generates the exact clarification question to send the GC.
- **Overconfident mapping.** Every mapping carries a confidence; anything below `high`
  is routed to a **human review** queue. Review everything for your first 10–15 bids —
  you're building the examples that make mapping reliable.
- **Hallucinated line items.** Every extracted line must carry a verbatim quote or it's
  dropped. No quote, no line — enforced in the prompt *and* in code.

## Install

```bash
pip install -r requirements.txt      # anthropic + pydantic
export ANTHROPIC_API_KEY=sk-ant-...  # for the extract/map/exclusions passes
# node is only needed to regenerate the taxonomy from index.html
```

## Use

**1. Regenerate the taxonomy** whenever `index.html` pricing changes (kept in sync,
never hand-edited):

```bash
python -m bidcompare export-taxonomy
```

**2. Capture your estimate** for a property. Start from a blank skeleton and fill in
each item's `amount` with your priced figure (or export it from the calculator):

```bash
python -m bidcompare estimate-template --region bayArea --property "123 Main St" --out estimate.json
```

**3. Analyze a bid** (runs the three Claude passes, then the Python variance):

```bash
python -m bidcompare analyze --estimate estimate.json --pdf acme-bid.pdf --out-dir out/
```

This writes, per bid: `*.extracted.json`, `*.exclusions.json`, `*.mapping.json`,
`*.variance.json`, and a human-readable `*.report.md` — and prints the Markdown report.

**4. Recalibrate** once you've processed several bids on comparable properties:

```bash
python -m bidcompare calibrate out/*.variance.json --out calibration.md
```

### Offline / no API key

The variance report is pure Python. Given saved extraction + mapping JSON, rebuild it
without touching the API — useful for testing, re-processing, or auditing a past run:

```bash
python -m bidcompare variance \
  --estimate examples/estimate.json \
  --extracted examples/demo.extracted.json \
  --mapping examples/demo.mapping.json
```

The `examples/` folder is a complete worked scenario (a bid that over-prices the
kitchen, under-prices paint, bundles a $42k lump sum, adds solar, and **silently omits
the sewer line**). Run the command above to see the report.

## Layout

| Path | What |
|---|---|
| `taxonomy/export_taxonomy.mjs` | Node exporter: `index.html` `REGIONS` → `taxonomy.json` |
| `taxonomy/taxonomy.json` | Generated canonical taxonomy (the spine) |
| `bidcompare/taxonomy.py` | Loads the taxonomy + your estimate |
| `bidcompare/models.py` | Pydantic schemas Claude is forced to fill (quotes required) |
| `bidcompare/llm.py` | Anthropic wrapper (PDF blocks, typed structured output) |
| `bidcompare/extract.py` | Claude: bid → line items with verbatim quotes |
| `bidcompare/exclusions.py` | Claude: exclusions / allowances / by-owner / TBD |
| `bidcompare/mapping.py` | Claude: lines → mapped / extra / unallocatable |
| `bidcompare/variance.py` | Python: line-by-line delta, missing-first, flagged |
| `bidcompare/feedback.py` | Python: cross-bid estimator recalibration |
| `bidcompare/report.py` | Markdown renderer |
| `bidcompare/cli.py` | `export-taxonomy · estimate-template · analyze · variance · calibrate` |
| `tests/` | Deterministic tests (no API key) |

## Model

Defaults to `claude-opus-4-8` for extraction/mapping (provenance and mapping
correctness matter more than token cost). Override with `--model` or `ANTHROPIC_MODEL`.
Tune reasoning depth with `BIDCOMPARE_EFFORT` (default `high`).

## Notes & next steps

- The first 10–15 bids: review every mapping. The `*.mapping.json` files you correct are
  the examples that make future mapping reliable — a natural place to add few-shot
  examples to the mapping prompt later.
- `analyze` runs extraction and exclusions as two passes over the same PDF for clarity;
  they can be merged into one call if token cost matters at volume.
- The variance/calibration output is plain data (`*.variance.json`) — easy to feed into a
  dashboard or back into the calculator later.
```
