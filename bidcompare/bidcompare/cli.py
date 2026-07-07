"""bidcompare CLI.

Subcommands:
  export-taxonomy    Regenerate taxonomy.json from index.html (needs node).
  estimate-template  Write a blank estimate skeleton for a region.
  analyze            Full pipeline on a bid PDF (needs an Anthropic API key).
  variance           Offline: build the variance report + markdown from saved
                     extraction + mapping JSON (no API key).
  calibrate          Aggregate saved variance reports -> estimator recalibration.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .models import ExtractedBid, Mapping
from .taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    estimate_template,
    load_estimate,
    load_taxonomy,
)
from .variance import build_variance
from .report import render_markdown, render_calibration_markdown
from .feedback import calibrate, calibration_to_dicts

REPO_ROOT = Path(__file__).resolve().parents[1]


def _slug(name: str) -> str:
    s = "".join(c if c.isalnum() else "-" for c in (name or "bid").lower())
    return "-".join(filter(None, s.split("-"))) or "bid"


# ---- export-taxonomy -----------------------------------------------------------------

def cmd_export_taxonomy(args) -> int:
    script = REPO_ROOT / "taxonomy" / "export_taxonomy.mjs"
    out = Path(args.out or DEFAULT_TAXONOMY_PATH)
    cmd = ["node", str(script)]
    if args.index:
        cmd.append(str(args.index))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    out.write_text(result.stdout)
    print(f"wrote {out}")
    return 0


# ---- estimate-template ---------------------------------------------------------------

def cmd_estimate_template(args) -> int:
    tax = load_taxonomy(args.region, args.taxonomy)
    tmpl = estimate_template(tax, args.property or "")
    out = Path(args.out)
    out.write_text(json.dumps(tmpl, indent=2))
    print(f"wrote {out} — fill in each item's `amount` with your priced figure.")
    return 0


# ---- analyze (full pipeline) ---------------------------------------------------------

def cmd_analyze(args) -> int:
    from .extract import extract_bid
    from .exclusions import extract_exclusions
    from .mapping import map_bid

    estimate = load_estimate(args.estimate)
    region = args.region or estimate.region
    tax = load_taxonomy(region, args.taxonomy)

    pdf = args.pdf
    text = None
    if args.text:
        text = Path(args.text).read_text()

    print("· extracting line items (Claude)…", file=sys.stderr)
    bid = extract_bid(pdf=pdf, text=text, model=args.model)
    print(f"  {len(bid.lines)} lines, contractor={bid.meta.contractor!r}", file=sys.stderr)

    print("· extracting exclusions/allowances (Claude)…", file=sys.stderr)
    exclusions = extract_exclusions(pdf=pdf, text=text, model=args.model)

    print("· mapping to taxonomy (Claude)…", file=sys.stderr)
    mapping = map_bid(tax, bid, model=args.model)

    print("· building variance report (Python)…", file=sys.stderr)
    rep = build_variance(tax, estimate, bid, mapping)
    md = render_markdown(rep, exclusions)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug(bid.meta.contractor)
    (out_dir / f"{stem}.extracted.json").write_text(bid.model_dump_json(indent=2))
    (out_dir / f"{stem}.exclusions.json").write_text(exclusions.model_dump_json(indent=2))
    (out_dir / f"{stem}.mapping.json").write_text(mapping.model_dump_json(indent=2))
    (out_dir / f"{stem}.variance.json").write_text(json.dumps(rep.to_dict(), indent=2))
    (out_dir / f"{stem}.report.md").write_text(md)

    print(md)
    print(f"\n(written to {out_dir}/{stem}.*)", file=sys.stderr)
    return 0


# ---- variance (offline) --------------------------------------------------------------

def cmd_variance(args) -> int:
    estimate = load_estimate(args.estimate)
    tax = load_taxonomy(args.region or estimate.region, args.taxonomy)
    bid = ExtractedBid.model_validate_json(Path(args.extracted).read_text())
    mapping = Mapping.model_validate_json(Path(args.mapping).read_text())
    rep = build_variance(tax, estimate, bid, mapping)
    md = render_markdown(rep)
    if args.out:
        Path(args.out).write_text(md)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep.to_dict(), indent=2))
    print(md)
    return 0


# ---- calibrate -----------------------------------------------------------------------

def cmd_calibrate(args) -> int:
    reports = []
    for path in args.reports:
        reports.append(json.loads(Path(path).read_text()))
    findings = calibrate(reports, min_bids=args.min_bids)
    md = render_calibration_markdown(findings)
    if args.out:
        Path(args.out).write_text(md)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(calibration_to_dicts(findings), indent=2))
    print(md)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bidcompare", description=__doc__)
    p.add_argument("--taxonomy", help="path to taxonomy.json (default: bundled)")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export-taxonomy", help="regenerate taxonomy.json from index.html")
    e.add_argument("--index", help="path to index.html")
    e.add_argument("--out", help="output path")
    e.set_defaults(func=cmd_export_taxonomy)

    t = sub.add_parser("estimate-template", help="write a blank estimate skeleton")
    t.add_argument("--region", default="bayArea")
    t.add_argument("--property", help="property address/name")
    t.add_argument("--out", required=True)
    t.set_defaults(func=cmd_estimate_template)

    a = sub.add_parser("analyze", help="full pipeline on a bid PDF (needs API key)")
    a.add_argument("--estimate", required=True, help="your estimate.json for this property")
    a.add_argument("--pdf", help="path to the bid PDF")
    a.add_argument("--text", help="path to bid text (alternative to --pdf, for testing)")
    a.add_argument("--region", help="override region (default: from estimate)")
    a.add_argument("--model", help="Claude model id (default: claude-opus-4-8)")
    a.add_argument("--out-dir", default="bidcompare-out")
    a.set_defaults(func=cmd_analyze)

    v = sub.add_parser("variance", help="offline variance from saved extraction+mapping")
    v.add_argument("--estimate", required=True)
    v.add_argument("--extracted", required=True, help="*.extracted.json")
    v.add_argument("--mapping", required=True, help="*.mapping.json")
    v.add_argument("--region")
    v.add_argument("--out", help="write markdown here")
    v.add_argument("--json-out", help="write variance json here")
    v.set_defaults(func=cmd_variance)

    c = sub.add_parser("calibrate", help="aggregate variance reports -> recalibration")
    c.add_argument("reports", nargs="+", help="one or more *.variance.json")
    c.add_argument("--min-bids", type=int, default=3)
    c.add_argument("--out", help="write markdown here")
    c.add_argument("--json-out", help="write calibration json here")
    c.set_defaults(func=cmd_calibrate)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
