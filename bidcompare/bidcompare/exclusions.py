"""Exclusions / allowances registry (Claude): a separate extraction target.

Every exclusion, allowance, "by owner", and "TBD" — pulled verbatim. This is where
change orders are born: the cheapest-looking bid is often the one that excluded the most.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import llm
from .models import ExclusionRegistry

SYSTEM = """\
You extract the EXCLUSIONS and ALLOWANCES registry from a general contractor's bid.
These are NOT the scope the contractor is performing — they are the gaps and caps that
become change orders. Capture every one, verbatim.

Classify each into `kind`:
- exclusion: explicitly not included / "excludes" / "not in contract"
- allowance: a capped budget line ("$5,000 allowance for tile") — capture the amount
- by_owner: owner, others, or a separate contractor is responsible ("by owner", "N.I.C.")
- tbd: to be determined / not yet priced / "TBD" / "pending selection"

Hard rules:
- Every item MUST carry a verbatim `quote` from the bid. No quote, no item.
- Do not capture normal priced scope here — only exclusions/allowances/by-owner/TBD.
- For allowances, pull the dollar amount into `amount`.
"""

INSTRUCTION = (
    "Extract every exclusion, allowance, by-owner, and TBD item. Each needs a verbatim quote."
)


def extract_exclusions(
    *,
    pdf: Optional[Path | str] = None,
    text: Optional[str] = None,
    model: Optional[str] = None,
) -> ExclusionRegistry:
    if not pdf and not text:
        raise ValueError("extract_exclusions needs either pdf= or text=")
    content: list[dict] = []
    if pdf:
        content.append(llm.pdf_block(pdf))
    if text:
        content.append(llm.text_block("BID TEXT:\n" + text))
    content.append(llm.text_block(INSTRUCTION))

    reg = llm.structured(
        system=SYSTEM, content=content, schema=ExclusionRegistry, model=model
    )
    reg.items = [it for it in reg.items if it.quote and it.quote.strip()]
    return reg
