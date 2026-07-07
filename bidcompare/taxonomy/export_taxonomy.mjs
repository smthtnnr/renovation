#!/usr/bin/env node
// Export the estimator's pricing model (the `REGIONS` object in ../../index.html)
// as the canonical bid-comparison taxonomy. This is the spine every bid is forced into.
//
//   node taxonomy/export_taxonomy.mjs [path/to/index.html] > taxonomy/taxonomy.json
//
// Keeping this as a mechanical export means the taxonomy can never silently drift
// from the calculator: re-run it whenever pricing changes.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const htmlPath = process.argv[2] || resolve(__dirname, "..", "..", "index.html");

// Human-readable unit for each `q` (quantity driver) in the pricing model.
// trade -> item -> UNIT -> unit cost is the master schema; this names the unit.
const UNITS = {
  flat: "each",
  sqft: "sqft",
  beds: "bedroom",
  baths: "bathroom",
  bedsBaths: "bed+bath",
  windows: "window",
  sliders: "slider",
  roofSquares: "roofing square",
  intDoors: "interior door",
  frontDoors: "front door",
  garageDoors: "garage door",
  garages: "garage",
  fenceLF: "linear ft",
  count: "each",
};

function extractRegions(html) {
  const start = html.indexOf("const REGIONS = {");
  if (start === -1) throw new Error("could not find `const REGIONS = {` in index.html");
  // REGIONS is immediately followed by `let currentRegion` in the source.
  const end = html.indexOf("let currentRegion", start);
  if (end === -1) throw new Error("could not find end of REGIONS block");
  let block = html.slice(start, end).trim();
  // Drop a trailing semicolon if present so we can eval as an expression.
  block = block.replace(/;?\s*$/, "");
  // `const REGIONS = {...}` -> evaluate to the object literal.
  const expr = block.replace(/^const\s+REGIONS\s*=\s*/, "");
  // eslint-disable-next-line no-eval
  return (0, eval)("(" + expr + ")");
}

function optionOf(o, pricingType, group) {
  return {
    id: o.id,
    label: o.label,
    unit: UNITS[o.q] || o.q || "each",
    unit_cost: typeof o.price === "number" ? o.price : null,
    q: o.q || null,
    default: !!o.def,
    ...(group ? { group } : {}),
    ...(pricingType === "pick" ? { exclusive: true } : {}),
  };
}

function itemOf(sys) {
  const options = [];
  let pricingType;
  if (sys.lineItems) pricingType = "line_items";
  else if (sys.picks) pricingType = "pick";
  else if (sys.addons) pricingType = "addon";
  else pricingType = "manual";

  (sys.addons || []).forEach((o) => options.push(optionOf(o, "addon")));
  (sys.picks || []).forEach((g) =>
    (g.opts || []).forEach((o) => options.push(optionOf(o, "pick", g.id)))
  );

  return {
    id: sys.amt, // PDF amount field is the stable unique id (names like "Miscellaneous" repeat)
    trade: sys.sec,
    item: sys.name,
    pricing_type: pricingType,
    pdf_field: sys.amt,
    // whether a bid omitting this item is a *scope gap* worth shouting about.
    // Major Systems are the ones that quietly sink a deal when missing.
    critical: sys.sec === "Major Systems",
    options,
  };
}

function main() {
  const html = readFileSync(htmlPath, "utf8");
  const regions = extractRegions(html);
  const out = {
    schema_version: 1,
    source: "index.html REGIONS",
    generated_at: new Date().toISOString(),
    units: UNITS,
    regions: {},
  };
  for (const [key, region] of Object.entries(regions)) {
    out.regions[key] = {
      label: region.label,
      items: region.systems.map(itemOf),
    };
  }
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
}

main();
