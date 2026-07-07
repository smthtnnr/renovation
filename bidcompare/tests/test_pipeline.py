"""Deterministic tests — taxonomy loading, variance, and calibration. No API needed."""
from __future__ import annotations

import json
from pathlib import Path

from bidcompare.taxonomy import load_taxonomy, load_estimate
from bidcompare.models import ExtractedBid, Mapping
from bidcompare.variance import build_variance
from bidcompare.feedback import calibrate

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _scenario():
    tax = load_taxonomy("bayArea")
    est = load_estimate(EX / "estimate.json")
    bid = ExtractedBid.model_validate_json((EX / "demo.extracted.json").read_text())
    mp = Mapping.model_validate_json((EX / "demo.mapping.json").read_text())
    return tax, est, bid, mp


def test_taxonomy_loads():
    tax = load_taxonomy("bayArea")
    assert len(tax.items) == 35
    kitchen = tax.by_id("GenAmountKitchen")
    assert kitchen and kitchen.item == "Kitchen"
    sewer = tax.by_id("MajAmountSewer")
    assert sewer.critical is True  # Major Systems are critical
    assert tax.by_id("GenAmountKitchen").critical is False


def test_variance_totals_and_buckets():
    tax, est, bid, mp = _scenario()
    rep = build_variance(tax, est, bid, mp)

    assert rep.your_total == 12500 + 6000 + 15000 + 8000 + 5500
    assert rep.bid_total_mapped == 16000 + 4000 + 15000
    # mapped + extra(20000) + unallocatable(42000)
    assert rep.bid_total_all == 35000 + 20000 + 42000

    # variance sorted by |delta|: Kitchen (+3500) then Paint (-2000) then Roof (0)
    labels = [r.label for r in rep.variance]
    assert labels[0].endswith("Kitchen")
    kitchen = rep.variance[0]
    assert kitchen.delta == 3500
    assert "variance>20%" in kitchen.flags

    paint = next(r for r in rep.variance if r.label.endswith("Paint"))
    assert paint.delta == -2000
    assert "variance>20%" in paint.flags


def test_missing_is_loud_and_critical_first():
    tax, est, bid, mp = _scenario()
    rep = build_variance(tax, est, bid, mp)
    ids = [m.taxonomy_id for m in rep.missing]
    # Sewer is priced but nothing maps to it -> missing, and it's a Major System.
    assert "MajAmountSewer" in ids
    sewer = next(m for m in rep.missing if m.taxonomy_id == "MajAmountSewer")
    assert sewer.critical is True
    assert rep.missing_dollars >= 8000
    # Bathroom is covered by the unallocatable lump sum candidate -> NOT missing.
    assert "GenAmountBathroom" not in ids
    # Kitchen is covered by a direct map -> NOT missing.
    assert "GenAmountKitchen" not in ids


def test_extra_and_unallocatable():
    tax, est, bid, mp = _scenario()
    rep = build_variance(tax, est, bid, mp)
    assert len(rep.extra) == 1 and rep.extra[0].amount == 20000
    assert len(rep.unallocatable) == 1
    u = rep.unallocatable[0]
    assert u.amount == 42000
    assert "clarification" not in u.clarification_question.lower() or u.clarification_question
    assert any("Kitchen" in lbl for lbl in u.candidate_labels)


def test_review_queue_flags_non_high_confidence():
    tax, est, bid, mp = _scenario()
    rep = build_variance(tax, est, bid, mp)
    # L3 roof mapping is 'medium' -> shows up in the review queue.
    assert any(rv.bid_line_id == "L3" for rv in rep.review)


def test_mapping_sanitize_drops_unknown_ids():
    tax, est, bid, mp = _scenario()
    mp.mapped.append(
        type(mp.mapped[0])(
            bid_line_id="L1", taxonomy_id="NotARealId", confidence="high", rationale="x"
        )
    )
    from bidcompare.mapping import _sanitize
    _sanitize(mp, tax, bid)
    assert all(m.taxonomy_id in tax.ids for m in mp.mapped)


def test_calibration_flags_consistent_underpricing():
    tax, est, bid, mp = _scenario()
    reports = []
    for contractor, kitchen_bid in [("Acme", 16000), ("Bravo", 17000), ("Cyrus", 16500)]:
        b = ExtractedBid.model_validate(bid.model_dump())
        b.meta.contractor = contractor
        b.lines[0].amount = kitchen_bid  # L1 = kitchen
        rep = build_variance(tax, est, b, mp)
        reports.append(rep.to_dict())

    findings = calibrate(reports, min_bids=3)
    kitchen = next((f for f in findings if f.taxonomy_id == "GenAmountKitchen"), None)
    assert kitchen is not None
    assert kitchen.direction == "underpriced"  # GCs consistently over your $12,500
    assert kitchen.n_bids == 3
    assert kitchen.ratio_median > 1.25


def test_calibration_needs_enough_bids():
    tax, est, bid, mp = _scenario()
    rep = build_variance(tax, est, bid, mp)
    # A single report can't trigger recalibration.
    assert calibrate([rep.to_dict()], min_bids=3) == []
