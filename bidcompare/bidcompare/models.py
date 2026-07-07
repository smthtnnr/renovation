"""Pydantic schemas for the Claude passes (extraction, mapping, exclusions).

Every extracted line carries a verbatim `quote` — its provenance. No quote, no
line; that rule is the defense against hallucinated scope. These schemas are the
JSON contract Claude is forced to fill.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---- extraction pass -----------------------------------------------------------------

class BidMeta(BaseModel):
    contractor: str = Field(description="General contractor / company name, verbatim if present, else ''")
    property_address: str = Field(default="", description="Property address if stated, else ''")
    bid_date: str = Field(default="", description="Date on the bid if stated, else ''")
    bid_total: Optional[float] = Field(
        default=None, description="Grand total dollar figure if the bid states one, else null"
    )


class BidLine(BaseModel):
    id: str = Field(description="Short stable id for this line, e.g. 'L1', 'L2'")
    description: str = Field(description="What the line covers, in the bid's own words")
    amount: Optional[float] = Field(
        default=None,
        description="Dollar amount for this line. Null if the line names scope but no price "
        "(e.g. a lump sum stated elsewhere, or 'included').",
    )
    quantity: Optional[float] = Field(default=None, description="Quantity if stated, else null")
    unit: Optional[str] = Field(default=None, description="Unit if stated (sqft, each, LF...), else null")
    unit_price: Optional[float] = Field(default=None, description="Per-unit price if stated, else null")
    is_lump_sum: bool = Field(
        default=False,
        description="True if this single amount visibly bundles multiple trades/items "
        "(e.g. 'Kitchen: $42,000' covering cabinets, counters, plumbing, electrical).",
    )
    quote: str = Field(
        description="VERBATIM text copied from the bid that this line is drawn from. "
        "Required — this is the provenance. If you cannot quote it, do not emit the line.",
    )
    page: Optional[int] = Field(default=None, description="1-indexed page the quote is on, if known")


class ExtractedBid(BaseModel):
    meta: BidMeta
    lines: list[BidLine]


# ---- exclusions / allowances registry ------------------------------------------------

ExclusionKind = Literal["exclusion", "allowance", "by_owner", "tbd"]


class ExclusionItem(BaseModel):
    kind: ExclusionKind = Field(
        description="exclusion = explicitly not included; allowance = capped budget line; "
        "by_owner = owner/others responsible; tbd = to be determined / not yet priced",
    )
    text: str = Field(description="Plain-language summary of what this exclusion/allowance covers")
    amount: Optional[float] = Field(default=None, description="Dollar amount for allowances, else null")
    quote: str = Field(description="VERBATIM text from the bid. Required.")
    page: Optional[int] = Field(default=None)


class ExclusionRegistry(BaseModel):
    items: list[ExclusionItem]


# ---- mapping pass --------------------------------------------------------------------

class MappedLine(BaseModel):
    bid_line_id: str
    taxonomy_id: str = Field(description="The taxonomy item id this bid line maps to")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high = unambiguous; medium = plausible but verify; low = weak/guess (human review)"
    )
    rationale: str = Field(description="One line: why this mapping")


class ExtraLine(BaseModel):
    bid_line_id: str
    reason: str = Field(description="Why this bid line has no home in the taxonomy (scope you don't carry)")


class UnallocatableLine(BaseModel):
    bid_line_id: str
    candidate_taxonomy_ids: list[str] = Field(
        description="The taxonomy items this lump sum appears to span"
    )
    reason: str = Field(description="Why it cannot be honestly split")
    clarification_question: str = Field(
        description="The exact question to send the GC to break out this lump sum"
    )


class Mapping(BaseModel):
    mapped: list[MappedLine]
    extra: list[ExtraLine]
    unallocatable: list[UnallocatableLine]
    # `missing` (taxonomy items no bid line covers) is computed in Python, not by Claude —
    # it is derived from what got mapped, so Claude can't hallucinate it away.
