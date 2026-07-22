# Editing pricing (via Google Sheet)

Prices live in a Google Sheet you control. A daily GitHub Action pulls the sheet,
rebuilds the app, and redeploys — so you change prices in a spreadsheet and never touch
code or this chat.

```
Google Sheet ──(daily / on demand)──▶ GitHub Action ──▶ regenerates index.html ──▶ Pages deploy
   you edit prices here                 scripts/build-pricing.mjs
```

The connected sheet's URL is baked into `.github/workflows/sync-pricing.yml`. To point at a
different sheet later, either edit that URL or set a repo variable `PRICING_SHEET_CSV_URL`
(the variable wins). The sheet must be shared **"anyone with the link can view"**.

## What you can change from the Sheet

- **Prices** — the `price` column. This is the whole point; edit freely.

Everything else (which systems/options exist, quantity units, how fields map to the PDF)
is structural and lives in `pricing/pricing.json`. Adding or removing an option, or adding a
region, is a code change — ask in chat. The Sheet's other columns (region/section/system/
option/unit) are there so you know what each row is; editing them has no effect, and you
must **not** touch the `key` column (it's how each row is matched to the app).

## One-time setup (already done for the connected sheet)

1. **Fill the sheet from the current prices.** In the repo, open `pricing/prices.csv`
   and download it (the **Raw** button on GitHub → Save As). In Google Sheets:
   *File → Import → Upload* that CSV → *Replace spreadsheet*. You now have every priced
   line item, one per row.
2. **Share it.** *Share → General access → Anyone with the link → Viewer.*
3. **Test it.** *Actions → Sync pricing from Google Sheet → Run workflow*. It will pull the
   sheet, and if any price differs it commits and the site redeploys a couple minutes later.

## Day-to-day

- Edit a price in the Sheet. Within a day the site updates automatically. To apply it
  immediately, go to **Actions → Sync pricing from Google Sheet → Run workflow**.
- Keep the `key` column intact and don't reorder/delete columns. If the download ever
  doesn't look like the expected CSV, the Action fails loudly and does **not** deploy, so a
  bad sheet can't take the live app down.

## How it works under the hood

- `pricing/pricing.json` — canonical pricing (structure + current prices).
- `pricing/prices.csv` — the flat price list mirrored from the Sheet.
- `scripts/build-pricing.mjs` — overlays the CSV prices onto the model and writes the
  `REGIONS` block into `index.html` (between the `PRICING:START` / `PRICING:END` markers).
- `.github/workflows/sync-pricing.yml` — the daily / on-demand sync.

To regenerate locally after editing `pricing/prices.csv` by hand:

```bash
node scripts/build-pricing.mjs          # overlay CSV + rebuild index.html
node scripts/build-pricing.mjs --seed   # rewrite prices.csv from pricing.json
node scripts/build-pricing.mjs --check  # verify the model round-trips
```
