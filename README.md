# Reno Budget Estimator

A single-page, installable web app for property managers to build a renovation
budget on a phone or desktop and export it into the standard **Budget Template
PDF**. Works fully offline once installed.

- **`index.html`** — the entire app (UI + pricing model + PDF filling). The pricing
  `REGIONS` block is **generated** (between `PRICING:START`/`PRICING:END`) — don't hand-edit it.
- **`pricing/pricing.json`, `pricing/prices.csv`** — the pricing data (structure + prices).
- **`scripts/build-pricing.mjs`** — regenerates the `REGIONS` block from that data.
- **`.github/workflows/sync-pricing.yml`** — hourly sync from the Google Sheet → see [`docs/PRICING.md`](docs/PRICING.md).
- **`vendor/pdf-lib.min.js`** — bundled PDF library (so export works offline).
- **`manifest.webmanifest`, `sw.js`, `icons/`** — make it installable as an app.
- **`Budget_Template.pdf`** — the fillable PDF the app populates (embedded in `index.html` as base64; this copy is kept for reference).
- **`docs/*.xlsx`** — legacy reference pricing sheets (no longer wired to the app).

---

## Running / hosting

Because it uses a service worker, open it from a URL (not a `file://` path):

```bash
# local preview
python3 -m http.server 8080
# then visit http://localhost:8080/
```

To deploy, serve the folder from any static host (e.g. GitHub Pages, an
internal web server). On a phone, open the URL and choose **Add to Home Screen**
(iOS) or tap **Install** (Android/Chrome) — it then runs full-screen and offline.

---

## Updating prices

**Prices are edited in a Google Sheet, not in code.** An hourly GitHub Action pulls the
sheet, regenerates the app, and redeploys. See **[`docs/PRICING.md`](docs/PRICING.md)** for
the one-time setup and day-to-day flow.

- `pricing/pricing.json` — canonical pricing model (structure + prices).
- `pricing/prices.csv` — the flat price list mirrored from the Sheet.
- `scripts/build-pricing.mjs` — overlays the CSV prices and regenerates the `REGIONS`
  block in `index.html` (between the `PRICING:START` / `PRICING:END` markers). **Don't edit
  that block by hand — it's generated.**
- `.github/workflows/sync-pricing.yml` — the hourly / on-demand sync.

## Adding / changing options (structure)

Adding an option, renaming a label, or changing quantity/PDF wiring is a structural change:
edit `pricing/pricing.json`, then run `node scripts/build-pricing.mjs` to rebuild
`index.html`. Each system maps to one PDF amount field. The kinds of priced inputs:

| Field | Meaning | Example |
|------|---------|---------|
| `picks` | a "choose one" dropdown | Flooring: LVP / Carpet / Engineered |
| `addons` | independent checkboxes | Paint: Interior + Exterior + Texture |
| `lineItems: true` | free-form description + $ rows | Framing/Drywall |
| `manual: true` | a single free-form $ box | Foundation |

**Add an option:** copy a sibling entry in `pricing/pricing.json`. Key fields:

- `id` — unique within that system (any short string).
- `label` — what the user sees.
- `price` — dollars per unit.
- `q` — what to multiply by: `"flat"` (×1), `"sqft"`, `"beds"`, `"windows"`,
  `"sliders"`, `"roofSquares"`, `"intDoors"`, `"frontDoors"`, `"garageDoors"`,
  `"garages"`, or `"count"` (an inline qty box on the option itself).
- `def: true` — checked / selected by default (addons & picks).
- For inline-qty addons: add `inline:true, qlabel:"baths"`.

Then run `node scripts/build-pricing.mjs` to regenerate `index.html`, and
`node scripts/build-pricing.mjs --seed` to refresh `pricing/prices.csv` (re-import it into
the Sheet so the new option shows up there too).

> Quantities like `q:"sqft"` come from the **Property & Quantities** inputs at
> the top of the app, entered once per property.

> The `sw.js` cache name is stamped with the commit SHA at deploy time, so every release
> busts old caches automatically — no manual version bump needed.

---

## Adding a region (later)

Pricing is keyed by region. To add one, copy the entire `bayArea` block inside
`pricing/pricing.json`, give it a new key and `label`, adjust prices, then run
`node scripts/build-pricing.mjs`:

```json
{
  "bayArea":     { "label": "Bay Area",     "systems": [ ... ] },
  "sacramento":  { "label": "Sacramento",   "systems": [ ... ] }
}
```

The **Pricing region** dropdown at the top of the page lists every region
automatically — no other code changes needed.

---

## Legacy pricing spreadsheets

`docs/BAY_PRICING_SHEET.xlsx` and `docs/CENTRAL_VALLEY_PRICING_SHEET.xlsx` were the
original hand-maintained reference sheets. They are **no longer wired to the app** — the
live source is now the Google Sheet described in [`docs/PRICING.md`](docs/PRICING.md). They
are kept for historical reference only.

---

## Mapping to the PDF

Every system has `amt`/`cmt`/`ins`/`cert` keys that are the **exact AcroForm
field names** in `Budget_Template.pdf`. All options within a system roll up into
that system's single `amt` field; the chosen options are summarized into `cmt`.
Subtotals and the grand total fill `MajSubtotal`, `GenSubtotal`, `FinSubtotal`,
and `GrandTotal`.

---

## Future: embedding in an internal system

The app is self-contained and dependency-free (pdf-lib is vendored), so it can
be served as a standalone route or embedded in an `<iframe>`. The pricing model
(`REGIONS`) is plain data — if pricing should later come from a backend, that
object is the single integration point to swap for a fetched JSON payload.
