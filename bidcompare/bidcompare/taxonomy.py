"""Load the canonical taxonomy exported from the estimator (taxonomy/taxonomy.json).

The taxonomy is the spine: trade -> item -> unit -> your unit cost. Every bid line
is forced into one of its items. This module also loads *your estimate* for a specific
property (the dollar figures a bid is compared against).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY_PATH = REPO_ROOT / "taxonomy" / "taxonomy.json"


@dataclass(frozen=True)
class TaxonomyOption:
    id: str
    label: str
    unit: str
    unit_cost: Optional[float]
    default: bool = False
    group: Optional[str] = None


@dataclass(frozen=True)
class TaxonomyItem:
    id: str            # stable unique id (the estimator's PDF amount field)
    trade: str         # "Major Systems" | "General Rehab" | "Finishes"
    item: str          # display name, e.g. "Sewer Line"
    pricing_type: str  # addon | pick | line_items | manual
    critical: bool     # a bid omitting this is a *silent scope gap* (Major Systems)
    options: list[TaxonomyOption] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.trade} / {self.item}"


@dataclass
class Taxonomy:
    region_key: str
    region_label: str
    items: list[TaxonomyItem]

    def by_id(self, item_id: str) -> Optional[TaxonomyItem]:
        return self._index.get(item_id)

    def __post_init__(self) -> None:
        self._index = {it.id: it for it in self.items}

    @property
    def ids(self) -> set[str]:
        return set(self._index)


def load_taxonomy(region: str = "bayArea", path: Path | str | None = None) -> Taxonomy:
    data = json.loads(Path(path or DEFAULT_TAXONOMY_PATH).read_text())
    regions = data["regions"]
    if region not in regions:
        raise KeyError(
            f"region {region!r} not in taxonomy; available: {', '.join(regions)}"
        )
    r = regions[region]
    items = [
        TaxonomyItem(
            id=it["id"],
            trade=it["trade"],
            item=it["item"],
            pricing_type=it["pricing_type"],
            critical=it.get("critical", False),
            options=[
                TaxonomyOption(
                    id=o["id"],
                    label=o["label"],
                    unit=o.get("unit", "each"),
                    unit_cost=o.get("unit_cost"),
                    default=o.get("default", False),
                    group=o.get("group"),
                )
                for o in it.get("options", [])
            ],
        )
        for it in r["items"]
    ]
    return Taxonomy(region_key=region, region_label=r["label"], items=items)


def taxonomy_digest(tax: Taxonomy) -> list[dict]:
    """Compact view handed to Claude for the mapping pass — enough to map against,
    small enough to keep the prompt cheap."""
    out = []
    for it in tax.items:
        out.append(
            {
                "id": it.id,
                "trade": it.trade,
                "item": it.item,
                "critical": it.critical,
                "example_scope": [o.label for o in it.options][:8],
            }
        )
    return out


# ---- your estimate for a specific property -------------------------------------------

@dataclass
class EstimateLine:
    taxonomy_id: str
    amount: float
    scope: str = ""


@dataclass
class Estimate:
    property: str
    region: str
    lines: dict[str, EstimateLine]  # taxonomy_id -> line

    def amount(self, taxonomy_id: str) -> float:
        line = self.lines.get(taxonomy_id)
        return line.amount if line else 0.0

    @property
    def total(self) -> float:
        return sum(l.amount for l in self.lines.values())


def load_estimate(path: Path | str) -> Estimate:
    data = json.loads(Path(path).read_text())
    lines: dict[str, EstimateLine] = {}
    for tid, v in data.get("items", {}).items():
        if isinstance(v, (int, float)):
            lines[tid] = EstimateLine(taxonomy_id=tid, amount=float(v))
        else:
            lines[tid] = EstimateLine(
                taxonomy_id=tid,
                amount=float(v.get("amount", 0) or 0),
                scope=v.get("scope", ""),
            )
    return Estimate(
        property=data.get("property", ""),
        region=data.get("region", "bayArea"),
        lines=lines,
    )


def estimate_template(tax: Taxonomy, property_name: str = "") -> dict:
    """A blank estimate skeleton for a region — fill in `amount` per item you're pricing.
    Priced against a bid, any item left at 0 shows up as *missing scope you carry*."""
    return {
        "property": property_name,
        "region": tax.region_key,
        "items": {
            it.id: {"amount": 0, "scope": it.item, "_trade": it.trade}
            for it in tax.items
        },
    }
