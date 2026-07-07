"""Calibration feedback loop (pure Python): make your pricing sheet truer over time.

Your estimate is a *model*, not market truth. If three independent GCs all come in 30%
over your paint number, the tool should flag YOUR estimator for recalibration — not the
three GCs for gouging. This aggregates variance across processed bids and surfaces the
line items where independent contractors systematically diverge from your price.

Input is a list of saved variance-report dicts (VarianceReport.to_dict()).
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Iterable

# A single GC can be noise; a chorus is signal.
DEFAULT_MIN_BIDS = 3
OVER_THRESHOLD = 1.25   # GCs median ≥ 125% of your price -> you're probably underpricing
UNDER_THRESHOLD = 0.80  # GCs median ≤ 80% of your price  -> you're probably overpricing
DIRECTION_AGREEMENT = 0.66  # fraction of bids that must agree on the direction


@dataclass
class CalibrationFinding:
    taxonomy_id: str
    label: str
    trade: str
    n_bids: int
    your_amount_median: float
    bid_amount_median: float
    ratio_median: float          # bid / your, median across contractors
    direction: str               # "underpriced" | "overpriced"
    agreement: float             # fraction of bids agreeing with the direction
    suggested_amount: float      # what re-centering on the GC median implies
    contractors: list[str] = field(default_factory=list)


def calibrate(
    reports: Iterable[dict],
    *,
    min_bids: int = DEFAULT_MIN_BIDS,
) -> list[CalibrationFinding]:
    # taxonomy_id -> list of (contractor, your_amount, bid_amount)
    obs: dict[str, list[tuple[str, float, float]]] = {}
    meta: dict[str, tuple[str, str]] = {}  # id -> (label, trade)

    for rep in reports:
        contractor = rep.get("contractor") or "(unnamed)"
        for row in rep.get("variance", []):
            your_amt = row.get("your_amount") or 0
            bid_amt = row.get("bid_amount") or 0
            if your_amt <= 0 or bid_amt <= 0:
                continue  # need both sides priced to compare
            tid = row["taxonomy_id"]
            obs.setdefault(tid, []).append((contractor, your_amt, bid_amt))
            meta[tid] = (row.get("label", tid), row.get("trade", ""))

    findings: list[CalibrationFinding] = []
    for tid, rows in obs.items():
        # De-dupe to one observation per contractor (a GC that appears twice isn't 2 votes).
        by_contractor: dict[str, tuple[float, float]] = {}
        for contractor, your_amt, bid_amt in rows:
            by_contractor.setdefault(contractor, (your_amt, bid_amt))
        if len(by_contractor) < min_bids:
            continue

        ratios = [b / y for (y, b) in by_contractor.values()]
        your_meds = [y for (y, _) in by_contractor.values()]
        bid_meds = [b for (_, b) in by_contractor.values()]
        ratio_med = statistics.median(ratios)

        if ratio_med >= OVER_THRESHOLD:
            direction = "underpriced"
            agree = sum(1 for r in ratios if r > 1) / len(ratios)
        elif ratio_med <= UNDER_THRESHOLD:
            direction = "overpriced"
            agree = sum(1 for r in ratios if r < 1) / len(ratios)
        else:
            continue  # your number sits inside the market band — no action

        if agree < DIRECTION_AGREEMENT:
            continue  # divergence isn't consistent enough to trust

        label, trade = meta[tid]
        findings.append(
            CalibrationFinding(
                taxonomy_id=tid,
                label=label,
                trade=trade,
                n_bids=len(by_contractor),
                your_amount_median=statistics.median(your_meds),
                bid_amount_median=statistics.median(bid_meds),
                ratio_median=ratio_med,
                direction=direction,
                agreement=agree,
                suggested_amount=statistics.median(bid_meds),
                contractors=sorted(by_contractor),
            )
        )

    # Largest miscalibration first (how far the market median is from your price).
    findings.sort(key=lambda f: abs(f.ratio_median - 1) * f.your_amount_median, reverse=True)
    return findings


def calibration_to_dicts(findings: list[CalibrationFinding]) -> list[dict]:
    return [asdict(f) for f in findings]
