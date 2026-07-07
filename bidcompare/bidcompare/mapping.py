"""Mapping pass (Claude): force each extracted bid line into the taxonomy.

Buckets: mapped (to a taxonomy item, with confidence), extra (bid has it, you don't),
unallocatable (lump sums that can't be honestly split — generates a GC clarification).
`missing` (you carry it, the bid doesn't) is computed in Python afterward so Claude
cannot hallucinate coverage that isn't there.
"""
from __future__ import annotations

import json
from typing import Optional

from . import llm
from .models import ExtractedBid, Mapping
from .taxonomy import Taxonomy, taxonomy_digest

SYSTEM = """\
You map a general contractor's extracted bid lines onto a fixed renovation taxonomy
(the estimator's own line items). You are given the taxonomy and the bid lines.

Put every bid line into exactly one bucket:
- mapped: the line clearly corresponds to a taxonomy item. Give a confidence:
    high   = unambiguous match
    medium = plausible but a human should confirm
    low    = weak/uncertain — route to human review
  Prefer `low` over a confident wrong guess. Never fabricate a match to avoid `extra`.
- extra: the bid includes scope that has NO home in the taxonomy (the estimate doesn't
  carry it). Say why.
- unallocatable: a single lump sum that visibly spans MULTIPLE taxonomy items and cannot
  be honestly divided (e.g. "Kitchen $42,000" covering cabinets, counters, plumbing,
  electrical). List the candidate taxonomy ids and write the exact clarification question
  to send the GC to break it out. DO NOT guess a split.

Rules:
- Map by scope, not by wording. A bid's "sewer lateral" maps to the taxonomy's Sewer Line.
- One bid line -> one bucket. Do not map the same line twice.
- Use only taxonomy `id` values shown. Never invent an id.
"""


def map_bid(
    tax: Taxonomy,
    bid: ExtractedBid,
    *,
    model: Optional[str] = None,
) -> Mapping:
    digest = taxonomy_digest(tax)
    lines = [
        {
            "id": ln.id,
            "description": ln.description,
            "amount": ln.amount,
            "is_lump_sum": ln.is_lump_sum,
            "quote": ln.quote,
        }
        for ln in bid.lines
    ]
    payload = (
        "TAXONOMY (map bid lines onto these ids):\n"
        + json.dumps(digest, indent=1)
        + "\n\nBID LINES:\n"
        + json.dumps(lines, indent=1)
        + "\n\nMap every bid line into mapped / extra / unallocatable."
    )
    mapping = llm.structured(
        system=SYSTEM,
        content=[llm.text_block(payload)],
        schema=Mapping,
        model=model,
    )
    _sanitize(mapping, tax, bid)
    return mapping


def _sanitize(mapping: Mapping, tax: Taxonomy, bid: ExtractedBid) -> None:
    """Drop any mapping that references an unknown taxonomy id or bid line id, so a
    stray hallucinated id can't corrupt the variance report downstream."""
    valid_tax = tax.ids
    valid_lines = {ln.id for ln in bid.lines}
    mapping.mapped = [
        m for m in mapping.mapped
        if m.taxonomy_id in valid_tax and m.bid_line_id in valid_lines
    ]
    mapping.extra = [e for e in mapping.extra if e.bid_line_id in valid_lines]
    for u in mapping.unallocatable:
        u.candidate_taxonomy_ids = [c for c in u.candidate_taxonomy_ids if c in valid_tax]


def missing_ids(tax: Taxonomy, mapping: Mapping, estimate) -> list[str]:
    """Taxonomy items the estimate prices but no bid line mapped to — the silent-scope-gap
    bucket. Only items the estimate actually carries (amount > 0) count as missing."""
    covered = {m.taxonomy_id for m in mapping.mapped}
    covered |= {c for u in mapping.unallocatable for c in u.candidate_taxonomy_ids}
    out = []
    for it in tax.items:
        if it.id in covered:
            continue
        if estimate.amount(it.id) > 0:
            out.append(it.id)
    return out
