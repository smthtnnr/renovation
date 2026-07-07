"""Variance report (pure Python): line-by-line delta of a bid vs your estimate.

Deterministic and API-free — this is the part you can test and trust. It consumes the
taxonomy, your estimate, the extracted bid, and the mapping, and produces:

  - missing:       taxonomy scope you carry that the bid omits   <- surfaced FIRST and loudest
  - variance:      per-item bid-vs-estimate delta, sorted by dollar impact, flagged
  - extra:         bid scope with no home in your estimate
  - unallocatable: lump sums that couldn't be split (+ the GC clarification question)
  - review:        low-confidence mappings a human must confirm
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .models import ExtractedBid, Mapping
from .taxonomy import Estimate, Taxonomy

VARIANCE_THRESHOLD = 0.20  # flag deltas beyond ±20%


@dataclass
class VarianceRow:
    taxonomy_id: str
    label: str
    trade: str
    your_amount: float
    bid_amount: float
    delta: float                 # bid - your (positive = bid is higher)
    pct: Optional[float]         # delta / your_amount; None if you priced it at 0
    critical: bool
    flags: list[str] = field(default_factory=list)
    bid_line_ids: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)


@dataclass
class MissingItem:
    taxonomy_id: str
    label: str
    trade: str
    your_amount: float
    critical: bool               # a missing Major System is a silent scope gap


@dataclass
class ExtraItem:
    bid_line_id: str
    description: str
    amount: Optional[float]
    reason: str
    quote: str


@dataclass
class UnallocatableItem:
    bid_line_id: str
    description: str
    amount: Optional[float]
    candidate_labels: list[str]
    reason: str
    clarification_question: str
    quote: str


@dataclass
class ReviewItem:
    bid_line_id: str
    taxonomy_label: str
    confidence: str
    rationale: str
    quote: str


@dataclass
class VarianceReport:
    contractor: str
    property_address: str
    region: str
    your_total: float
    bid_total_mapped: float      # what the bid prices against scope you also carry
    bid_total_all: float         # everything the bid prices (mapped + extra + unallocatable)
    bid_stated_total: Optional[float]
    missing: list[MissingItem]
    variance: list[VarianceRow]
    extra: list[ExtraItem]
    unallocatable: list[UnallocatableItem]
    review: list[ReviewItem]

    @property
    def missing_dollars(self) -> float:
        return sum(m.your_amount for m in self.missing)

    @property
    def extra_dollars(self) -> float:
        return sum(e.amount or 0 for e in self.extra)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["missing_dollars"] = self.missing_dollars
        d["extra_dollars"] = self.extra_dollars
        return d


def _is_round(x: float) -> bool:
    """A suspiciously round number — the fingerprint of a guessed lump figure."""
    return x >= 1000 and (x % 1000 == 0 or x % 2500 == 0)


def build_variance(
    tax: Taxonomy,
    estimate: Estimate,
    bid: ExtractedBid,
    mapping: Mapping,
) -> VarianceReport:
    line_by_id = {ln.id: ln for ln in bid.lines}

    # Aggregate mapped bid lines per taxonomy item.
    per_item: dict[str, list] = {}
    for m in mapping.mapped:
        per_item.setdefault(m.taxonomy_id, []).append(m)

    # ---- variance rows (items the bid actually mapped to) ----
    rows: list[VarianceRow] = []
    bid_total_mapped = 0.0
    for tid, maps in per_item.items():
        item = tax.by_id(tid)
        if item is None:
            continue
        your_amount = estimate.amount(tid)
        line_ids = [m.bid_line_id for m in maps]
        lines = [line_by_id[i] for i in line_ids if i in line_by_id]
        bid_amount = sum(ln.amount or 0 for ln in lines)
        bid_total_mapped += bid_amount
        delta = bid_amount - your_amount
        pct = (delta / your_amount) if your_amount else None

        flags: list[str] = []
        if pct is not None and abs(pct) > VARIANCE_THRESHOLD:
            flags.append("variance>20%")
        if your_amount == 0 and bid_amount > 0:
            flags.append("not-in-estimate")
        if _is_round(bid_amount):
            flags.append("round-number")
        if any(ln.is_lump_sum for ln in lines):
            flags.append("lump-sum")
        if len(lines) > 1:
            flags.append("multi-line")
        if any(ln.amount is None for ln in lines):
            flags.append("no-price")
        if any(m.confidence != "high" for m in maps):
            flags.append("low-confidence")

        rows.append(
            VarianceRow(
                taxonomy_id=tid,
                label=item.label,
                trade=item.trade,
                your_amount=your_amount,
                bid_amount=bid_amount,
                delta=delta,
                pct=pct,
                critical=item.critical,
                flags=flags,
                bid_line_ids=line_ids,
                quotes=[ln.quote for ln in lines],
            )
        )
    # Biggest dollar swings first — that's where the money and the risk are.
    rows.sort(key=lambda r: abs(r.delta), reverse=True)

    # ---- missing: you carry it, the bid doesn't. Loudest bucket. ----
    covered = set(per_item) | {
        c for u in mapping.unallocatable for c in u.candidate_taxonomy_ids
    }
    missing: list[MissingItem] = []
    for it in tax.items:
        if it.id in covered:
            continue
        your_amount = estimate.amount(it.id)
        if your_amount <= 0:
            continue
        missing.append(
            MissingItem(
                taxonomy_id=it.id,
                label=it.label,
                trade=it.trade,
                your_amount=your_amount,
                critical=it.critical,
            )
        )
    # Critical (Major System) gaps first, then by dollars carried.
    missing.sort(key=lambda m: (not m.critical, -m.your_amount))

    # ---- extra: bid scope with no home in your estimate ----
    extra = [
        ExtraItem(
            bid_line_id=e.bid_line_id,
            description=line_by_id[e.bid_line_id].description if e.bid_line_id in line_by_id else "",
            amount=line_by_id[e.bid_line_id].amount if e.bid_line_id in line_by_id else None,
            reason=e.reason,
            quote=line_by_id[e.bid_line_id].quote if e.bid_line_id in line_by_id else "",
        )
        for e in mapping.extra
    ]

    # ---- unallocatable lump sums ----
    unalloc = []
    for u in mapping.unallocatable:
        ln = line_by_id.get(u.bid_line_id)
        labels = [tax.by_id(c).label for c in u.candidate_taxonomy_ids if tax.by_id(c)]
        unalloc.append(
            UnallocatableItem(
                bid_line_id=u.bid_line_id,
                description=ln.description if ln else "",
                amount=ln.amount if ln else None,
                candidate_labels=labels,
                reason=u.reason,
                clarification_question=u.clarification_question,
                quote=ln.quote if ln else "",
            )
        )

    # ---- review queue: anything below high confidence ----
    review = [
        ReviewItem(
            bid_line_id=m.bid_line_id,
            taxonomy_label=tax.by_id(m.taxonomy_id).label if tax.by_id(m.taxonomy_id) else m.taxonomy_id,
            confidence=m.confidence,
            rationale=m.rationale,
            quote=line_by_id[m.bid_line_id].quote if m.bid_line_id in line_by_id else "",
        )
        for m in mapping.mapped
        if m.confidence != "high"
    ]

    bid_total_all = (
        bid_total_mapped
        + sum(e.amount or 0 for e in extra)
        + sum(u.amount or 0 for u in unalloc)
    )

    return VarianceReport(
        contractor=bid.meta.contractor,
        property_address=bid.meta.property_address or estimate.property,
        region=estimate.region,
        your_total=estimate.total,
        bid_total_mapped=bid_total_mapped,
        bid_total_all=bid_total_all,
        bid_stated_total=bid.meta.bid_total,
        missing=missing,
        variance=rows,
        extra=extra,
        unallocatable=unalloc,
        review=review,
    )
