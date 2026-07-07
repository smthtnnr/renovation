"""Render a variance report as Markdown. Missing scope is shown FIRST and loudest —
a bid that maps cleanly but omits your sewer/roof/electrical line looks cheap until
you see what it left out."""
from __future__ import annotations

from typing import Optional

from .models import ExclusionRegistry
from .variance import VarianceReport


def _money(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"${x:,.0f}"


def _pct(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return f"{p * 100:+.0f}%"


def render_markdown(
    rep: VarianceReport,
    exclusions: Optional[ExclusionRegistry] = None,
) -> str:
    out: list[str] = []
    title = rep.contractor or "Bid"
    out.append(f"# Bid comparison — {title}")
    if rep.property_address:
        out.append(f"**Property:** {rep.property_address}  ")
    out.append(f"**Region:** {rep.region}\n")

    # ---- headline numbers ----
    out.append("## Bottom line\n")
    out.append("| | Amount |")
    out.append("|---|---:|")
    out.append(f"| Your estimate | {_money(rep.your_total)} |")
    out.append(f"| Bid — priced against your scope | {_money(rep.bid_total_mapped)} |")
    out.append(f"| Bid — everything it prices | {_money(rep.bid_total_all)} |")
    if rep.bid_stated_total is not None:
        out.append(f"| Bid — grand total it states | {_money(rep.bid_stated_total)} |")
    out.append(f"| **Missing scope you carry** | **{_money(rep.missing_dollars)}** |")
    out.append(f"| Extra scope the bid adds | {_money(rep.extra_dollars)} |")
    out.append("")

    # ---- MISSING first and loud ----
    out.append("## ⚠️ Missing scope — the bid omits work your estimate carries\n")
    if not rep.missing:
        out.append("_None — the bid covers every priced line in your estimate._\n")
    else:
        out.append(
            f"**{len(rep.missing)} item(s), {_money(rep.missing_dollars)} of scope you priced "
            "that this bid does not.** A low bid that skips these isn't cheap — it's incomplete.\n"
        )
        out.append("| ! | Item | Trade | You priced |")
        out.append("|---|---|---|---:|")
        for m in rep.missing:
            bang = "🔴" if m.critical else "•"
            out.append(f"| {bang} | {m.label} | {m.trade} | {_money(m.your_amount)} |")
        out.append("\n🔴 = Major System — a silent scope gap that can sink the deal.\n")

    # ---- unallocatable lump sums ----
    if rep.unallocatable:
        out.append("## 🧩 Unallocatable lump sums — send these back to the GC\n")
        out.append(
            "These bundle multiple trades into one number and can't be honestly compared "
            "line-by-line. Ask the GC to break them out:\n"
        )
        for u in rep.unallocatable:
            out.append(f"- **{u.description or u.bid_line_id}** — {_money(u.amount)}")
            if u.candidate_labels:
                out.append(f"  - Appears to span: {', '.join(u.candidate_labels)}")
            out.append(f"  - _Quote:_ “{u.quote.strip()}”")
            out.append(f"  - **Ask:** {u.clarification_question}")
        out.append("")

    # ---- line-by-line variance ----
    out.append("## Line-by-line variance (sorted by dollar impact)\n")
    if not rep.variance:
        out.append("_No overlapping line items were mapped._\n")
    else:
        out.append("| Item | You | Bid | Δ $ | Δ % | Flags |")
        out.append("|---|---:|---:|---:|---:|---|")
        for r in rep.variance:
            flags = " ".join(f"`{f}`" for f in r.flags)
            out.append(
                f"| {r.label} | {_money(r.your_amount)} | {_money(r.bid_amount)} "
                f"| {_money(r.delta)} | {_pct(r.pct)} | {flags} |"
            )
        out.append("")

    # ---- extra scope ----
    if rep.extra:
        out.append("## Extra scope the bid includes (not in your estimate)\n")
        out.append("| Item | Amount | Why it's extra |")
        out.append("|---|---:|---|")
        for e in rep.extra:
            out.append(f"| {e.description or e.bid_line_id} | {_money(e.amount)} | {e.reason} |")
        out.append("")

    # ---- human review queue ----
    if rep.review:
        out.append("## 👀 Human review — low-confidence mappings\n")
        out.append("| Bid line | Mapped to | Confidence | Why |")
        out.append("|---|---|---|---|")
        for rv in rep.review:
            out.append(
                f"| “{rv.quote.strip()[:60]}” | {rv.taxonomy_label} | {rv.confidence} | {rv.rationale} |"
            )
        out.append("")

    # ---- exclusions / allowances registry ----
    if exclusions and exclusions.items:
        out.append("## Exclusions & allowances registry (where change orders are born)\n")
        out.append("| Kind | Item | Amount | Quote |")
        out.append("|---|---|---:|---|")
        for it in exclusions.items:
            out.append(
                f"| {it.kind} | {it.text} | {_money(it.amount)} | “{it.quote.strip()[:70]}” |"
            )
        out.append("")

    return "\n".join(out)


def render_calibration_markdown(findings: list) -> str:
    """findings: list[CalibrationFinding]"""
    out = ["# Estimator calibration — recalibrate your pricing sheet\n"]
    if not findings:
        out.append(
            "_No line items show consistent divergence across enough independent bids yet. "
            "Keep processing bids — the signal builds over time._\n"
        )
        return "\n".join(out)
    out.append(
        "These line items are where independent GCs systematically disagree with your "
        "price. That's a signal to recalibrate the estimator, not to distrust the GCs.\n"
    )
    out.append("| Item | Trade | Bids | Your median | GC median | GC/You | Verdict | Agreement | Suggested |")
    out.append("|---|---|---:|---:|---:|---:|---|---:|---:|")
    for f in findings:
        verdict = "you're **low**" if f.direction == "underpriced" else "you're **high**"
        out.append(
            f"| {f.label} | {f.trade} | {f.n_bids} | {_money(f.your_amount_median)} "
            f"| {_money(f.bid_amount_median)} | {f.ratio_median:.2f}× | {verdict} "
            f"| {f.agreement*100:.0f}% | {_money(f.suggested_amount)} |"
        )
    out.append("")
    return "\n".join(out)
