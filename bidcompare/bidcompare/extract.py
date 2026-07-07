"""Extraction pass (Claude): bid PDF -> structured line items, each with a verbatim quote.

The provenance rule is enforced twice: the prompt demands a verbatim quote per line,
and `extract_bid` drops any line that comes back without one. No quote, no line.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import llm
from .models import ExtractedBid

SYSTEM = """\
You are a construction-bid extractor for a renovation estimator. You read a general
contractor's bid (PDF or pasted text) and return a structured list of every priced or
scoped line item.

Hard rules:
- Every line MUST carry a `quote`: text copied VERBATIM from the bid. If you cannot copy
  the exact words the line is based on, DO NOT emit the line. Never invent scope.
- Do not merge distinct scope items into one line, and do not split a single stated
  amount across several lines.
- If one dollar amount visibly bundles multiple trades (e.g. "Kitchen — $42,000" covering
  cabinets, counters, plumbing, and electrical), emit it as ONE line and set
  `is_lump_sum: true`. Do not guess how to divide it.
- Capture quantities, units, and unit prices only when the bid states them.
- Do NOT capture exclusions, allowances, "by owner", or "TBD" items here — those are a
  separate pass. Only capture actual scope the contractor is pricing/performing.
- Pull the contractor name, property address, date, and grand total into `meta` when present.
"""

INSTRUCTION = (
    "Extract every priced/scoped line item from this bid. Remember: every line needs a "
    "verbatim quote, or it does not belong in the output."
)


def extract_bid(
    *,
    pdf: Optional[Path | str] = None,
    text: Optional[str] = None,
    model: Optional[str] = None,
) -> ExtractedBid:
    if not pdf and not text:
        raise ValueError("extract_bid needs either pdf= or text=")
    content: list[dict] = []
    if pdf:
        content.append(llm.pdf_block(pdf))
    if text:
        content.append(llm.text_block("BID TEXT:\n" + text))
    content.append(llm.text_block(INSTRUCTION))

    result = llm.structured(
        system=SYSTEM, content=content, schema=ExtractedBid, model=model
    )
    # Enforce provenance: strip any line whose quote is empty/whitespace.
    kept = [ln for ln in result.lines if ln.quote and ln.quote.strip()]
    result.lines = kept
    return result
