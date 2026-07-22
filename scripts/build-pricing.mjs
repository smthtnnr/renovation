#!/usr/bin/env node
// Regenerates the app's pricing from editable data.
//
//   Sources of truth
//     pricing/pricing.json  — the full pricing model (structure + prices). Structure
//                             (which systems/options exist, PDF field mappings, quantity
//                             types) is technical and lives here.
//     pricing/prices.csv    — one row per priced option, mirrored from the Google Sheet.
//                             This is what a human edits (via the Sheet). Only the `price`
//                             column is read back in; everything else is context.
//
//   What it does
//     1. Loads pricing.json.
//     2. If pricing/prices.csv exists, overlays its prices onto the model (the Sheet wins),
//        and writes the updated prices back into pricing.json so the JSON stays canonical.
//     3. Serializes the model into index.html between the PRICING:START/END markers.
//
//   Commands
//     node scripts/build-pricing.mjs           build index.html (+ overlay csv if present)
//     node scripts/build-pricing.mjs --seed     (re)write pricing/prices.csv from pricing.json
//     node scripts/build-pricing.mjs --check     verify the generated model matches pricing.json (no writes)
//
// Prices are the only thing the Sheet controls; adding/removing systems or options, or
// changing quantity/PDF wiring, is a structural change made in pricing.json (or via chat).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const P = (...a) => path.join(ROOT, ...a);
const JSON_PATH = P("pricing", "pricing.json");
const CSV_PATH = P("pricing", "prices.csv");
const HTML_PATH = P("index.html");
const START = "/* PRICING:START — generated from pricing/pricing.json by scripts/build-pricing.mjs. Edit prices in the Google Sheet, not here. */";
const END = "/* PRICING:END */";

// ---- key that ties a priced option to a CSV row (stable across label/price edits) ----
const optKey = (regionKey, sys, kind, groupId, optId) =>
  [regionKey, sys.amt, kind, groupId || "", optId].join("|");

// ---- walk every priced option in the model ----
function eachOption(regions, fn) {
  for (const regionKey of Object.keys(regions)) {
    const region = regions[regionKey];
    for (const sys of region.systems) {
      for (const g of sys.picks || [])
        for (const o of g.opts) fn({ regionKey, region, sys, kind: "pick", groupId: g.id, opt: o });
      for (const o of sys.addons || [])
        fn({ regionKey, region, sys, kind: "addon", groupId: "", opt: o });
    }
  }
}

// ---- minimal RFC-4180 CSV ----
function csvEscape(v) {
  const s = String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function csvParse(text) {
  const rows = [];
  let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false; }
      else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\r") { /* ignore */ }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.length && r.some(c => c !== ""));
}

function buildCsv(regions) {
  const lines = [["key", "region", "section", "system", "option", "unit", "price"].join(",")];
  eachOption(regions, ({ regionKey, region, sys, kind, groupId, opt }) => {
    lines.push([
      optKey(regionKey, sys, kind, groupId, opt.id),
      region.label, sys.sec, sys.name, opt.label, opt.q, opt.price,
    ].map(csvEscape).join(","));
  });
  return lines.join("\n") + "\n";
}

// ---- overlay CSV prices onto the model; returns {applied, unknown, missing} ----
function overlayPrices(regions, csvText) {
  const rows = csvParse(csvText);
  const header = rows.shift().map(h => h.trim().toLowerCase());
  const keyI = header.indexOf("key"), priceI = header.indexOf("price");
  if (keyI < 0 || priceI < 0) throw new Error("prices.csv must have 'key' and 'price' columns");
  const byKey = new Map();
  for (const r of rows) byKey.set(r[keyI], r[priceI]);
  const seen = new Set();
  let applied = 0, missing = 0;
  eachOption(regions, ({ regionKey, sys, kind, groupId, opt }) => {
    const k = optKey(regionKey, sys, kind, groupId, opt.id);
    if (byKey.has(k)) {
      const raw = String(byKey.get(k)).replace(/[$,\s]/g, "");
      const n = Number(raw);
      if (!Number.isFinite(n) || n < 0) throw new Error(`Invalid price for ${k}: "${byKey.get(k)}"`);
      if (n !== opt.price) applied++;
      opt.price = n;
      seen.add(k);
    } else missing++;
  });
  const unknown = [...byKey.keys()].filter(k => !seen.has(k));
  return { applied, missing, unknown };
}

// ---- serialize the model to readable, deterministic JS (functionally == pricing.json) ----
function js(v) {
  if (typeof v === "string") return JSON.stringify(v);
  if (typeof v === "boolean" || typeof v === "number") return String(v);
  if (Array.isArray(v)) return "[" + v.map(js).join(", ") + "]";
  if (v && typeof v === "object")
    return "{" + Object.entries(v).map(([k, x]) => `${k}:${js(x)}`).join(", ") + "}";
  return String(v);
}
function serializeSystem(s) {
  // stable key order; only emit keys that are present
  const head = {};
  for (const k of ["sec", "name", "amt", "cmt", "ins", "cert", "lineItems", "manual"])
    if (k in s) head[k] = s[k];
  let out = "{" + Object.entries(head).map(([k, v]) => `${k}:${js(v)}`).join(", ");
  if (s.picks) out += `, picks:${js(s.picks)}`;
  if (s.addons) out += `, addons:${js(s.addons)}`;
  return out + "}";
}
function serializeRegions(regions) {
  const parts = [];
  for (const regionKey of Object.keys(regions)) {
    const r = regions[regionKey];
    const bySec = {};
    for (const s of r.systems) (bySec[s.sec] ||= []).push(s);
    const secBlocks = Object.entries(bySec).map(([sec, list]) =>
      `   // ===== ${sec.toUpperCase()} =====\n` +
      list.map(s => "   " + serializeSystem(s) + ",").join("\n")
    );
    parts.push(` ${regionKey}: {\n  label: ${JSON.stringify(r.label)},\n  systems: [\n${secBlocks.join("\n\n")}\n  ]\n }`);
  }
  return "const REGIONS = {\n" + parts.join(",\n") + "\n};";
}

function replaceRegionsBlock(html, block) {
  const wrapped = START + "\n" + block + "\n" + END;
  const si = html.indexOf(START);
  if (si >= 0) {
    const ei = html.indexOf(END, si);
    if (ei < 0) throw new Error("PRICING:START without PRICING:END");
    return html.slice(0, si) + wrapped + html.slice(ei + END.length);
  }
  // first run: locate the raw `const REGIONS = { ... };` via brace matching
  const start = html.indexOf("const REGIONS");
  if (start < 0) throw new Error("could not find `const REGIONS` in index.html");
  const braceStart = html.indexOf("{", start);
  let depth = 0, inStr = null, end = -1;
  for (let i = braceStart; i < html.length; i++) {
    const c = html[i], p = html[i - 1];
    if (inStr) { if (c === inStr && p !== "\\") inStr = null; continue; }
    if (c === '"' || c === "'" || c === "`") { inStr = c; continue; }
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) { end = i; break; }
  }
  if (end < 0) throw new Error("could not brace-match REGIONS object");
  let after = end + 1;
  if (html[after] === ";") after++; // swallow the trailing semicolon
  return html.slice(0, start) + wrapped + html.slice(after);
}

// evaluate a serialized REGIONS block back into an object (for --check)
function evalRegions(block) {
  const m = block.replace(/^const REGIONS =/, "return ");
  return new Function(m + "\n")();
}

// ---- main ----
const mode = process.argv[2] || "";
const regions = JSON.parse(fs.readFileSync(JSON_PATH, "utf8"));

if (mode === "--seed") {
  fs.writeFileSync(CSV_PATH, buildCsv(regions));
  console.log(`Wrote ${path.relative(ROOT, CSV_PATH)} (${126} options).`);
  process.exit(0);
}

if (mode === "--check") {
  const block = serializeRegions(regions);
  const round = evalRegions(block);
  const same = JSON.stringify(round) === JSON.stringify(regions);
  console.log(same ? "OK: serialized model round-trips exactly." : "MISMATCH: serialization differs from pricing.json.");
  process.exit(same ? 0 : 1);
}

// default: build
if (fs.existsSync(CSV_PATH)) {
  const res = overlayPrices(regions, fs.readFileSync(CSV_PATH, "utf8"));
  fs.writeFileSync(JSON_PATH, JSON.stringify(regions, null, 2) + "\n");
  console.log(`Overlay: ${res.applied} price change(s) applied from prices.csv.`);
  if (res.unknown.length) console.log(`  note: ${res.unknown.length} CSV row(s) had keys not in the model (ignored).`);
  if (res.missing) console.log(`  note: ${res.missing} option(s) had no CSV row (kept existing price).`);
}
const block = serializeRegions(regions);
if (!(JSON.stringify(evalRegions(block)) === JSON.stringify(regions)))
  throw new Error("refusing to write: serialized model does not match data");
const html = fs.readFileSync(HTML_PATH, "utf8");
fs.writeFileSync(HTML_PATH, replaceRegionsBlock(html, block));
console.log("Wrote REGIONS block into index.html.");
