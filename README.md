# Reno Budget Estimator

A single-page, installable web app for property managers to build a renovation
budget on a phone or desktop and export it into the standard **Budget Template
PDF**. Works fully offline once installed.

- **`index.html`** — the entire app (UI + pricing model + PDF filling).
- **`vendor/pdf-lib.min.js`** — bundled PDF library (so export works offline).
- **`manifest.webmanifest`, `sw.js`, `icons/`** — make it installable as an app.
- **`Budget_Template.pdf`** — the fillable PDF the app populates (embedded in `index.html` as base64; this copy is kept for reference).
- **`docs/BAY_PRICING_SHEET.xlsx`** — the source-of-truth pricing sheet.

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

## Updating prices / adding options

All pricing lives in one place in `index.html`: the **`REGIONS`** object
(search for `const REGIONS = {`). Each system is one row that maps to one PDF
amount field. The three kinds of priced inputs:

| Field | Meaning | Example |
|------|---------|---------|
| `picks` | a "choose one" dropdown | Flooring: LVP / Carpet / Engineered |
| `addons` | independent checkboxes | Paint: Interior + Exterior + Texture |
| `lineItems: true` | free-form description + $ rows | Framing/Drywall |
| `manual: true` | a single free-form $ box | Foundation |

**Change a price:** edit the `price:` value on that option.

```js
{id:"tearoff", label:"Tearoff", price:750, q:"roofSquares"},
//                                    ^^^ edit this
```

**Add an option:** copy a sibling line and edit it. Key fields:

- `id` — unique within that system (any short string).
- `label` — what the user sees.
- `price` — dollars per unit.
- `q` — what to multiply by: `"flat"` (×1), `"sqft"`, `"beds"`, `"windows"`,
  `"sliders"`, `"roofSquares"`, `"intDoors"`, `"frontDoors"`, `"garageDoors"`,
  `"garages"`, or `"count"` (an inline qty box on the option itself).
- `def: true` — checked / selected by default (addons & picks).
- For inline-qty addons: add `inline:true, qlabel:"baths"`.

> Quantities like `q:"sqft"` come from the **Property & Quantities** inputs at
> the top of the app, entered once per property.

After editing pricing assets, bump the cache version in `sw.js`
(`reno-budget-v1` → `-v2`) so installed apps pull the update.

---

## Adding a region (later)

Pricing is keyed by region. To add one, copy the entire `bayArea` block inside
`REGIONS`, give it a new key and `label`, and adjust prices:

```js
const REGIONS = {
  bayArea:  { label: "Bay Area",  systems: [ /* ... */ ] },
  sacramento:{ label: "Sacramento", systems: [ /* ... */ ] }   // new
};
```

The **Pricing region** dropdown at the top of the page lists every region in
`REGIONS` automatically — no other code changes needed.

---

## Keeping pricing in sync with the spreadsheet

`docs/BAY_PRICING_SHEET.xlsx` (tab **Sheet2**) is the authoritative pricing.
The app's `REGIONS.bayArea` mirrors it. When the sheet changes, update the
matching `price:`/options in `index.html` and bump the `sw.js` cache version.

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
