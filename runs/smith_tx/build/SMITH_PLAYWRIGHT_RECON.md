# Smith TX — Playwright recon notes (2026-05-25)

Operator authorized Playwright for the SPA / reCAPTCHA primary sources.
Chromium installed via `python -m playwright install chromium` (succeeded).
This file records what the recon probes found and why two production
adapters (Tyler Odyssey courts, publicsearch.us clerk) were punch-listed
rather than shipped in this turn.

## Tyler Odyssey — portal.smith-county.com (district courts)

- Probe URL: `https://portal.smith-county.com/Public/Home/Dashboard/29` (Smart Search)
- Page loads cleanly in headless chromium (title "Smart Search - Tyler Odyssey Portal").
- reCAPTCHA library present in HTML but no widget rendered on page load (invisible v3).
- Submitted a name search ("SMITH" / Last name) via Playwright form-fill:
  - 35 GETs to `portal.smith-county.com` captured — every one was a static
    asset (CSS, JS, images: `kendo.css`, `TylerUiCss`, `smartSearchPortlet.js`, etc.).
  - **Zero XHR / fetch responses to data endpoints** captured.
  - The page title transitioned to `Loading https://portal.smith-county.com/Public/SmartSearch/SmartSearch/SmartSearch`
    but the body did not render results within the probe window. Likely
    causes: (a) reCAPTCHA v3 bot-score gating the submit, (b) the portlet
    posts to a server-side handler that returns a redirect, (c) headless
    fingerprint failing Tyler's bot detection.

**Production-adapter requirements** (deferred, punch-list):
- `playwright-stealth` plugin or undetected fingerprint to pass reCAPTCHA v3 scoring.
- Probably operator-seeded session cookies (operator clears reCAPTCHA once
  in a real browser; framework replays cookies) — the framework's
  `use_seeded_session` strategy.
- Result parser for the Odyssey table layout.
- Pagination + retry strategy.

Endpoint candidate identified: `/Public/SmartSearch/SmartSearch/SmartSearch`
(POST). Validation requires the above-listed work.

## publicsearch.us (Smith County Clerk official records)

- Probe URL: `https://smith.tx.publicsearch.us/`
- Page loads (React SPA, "window.__data" SSR with empty `isLoading:true`
  state — confirmed earlier in Phase 3 ESC-002).
- Playwright form-fill attempted on `input[type=text],input[type=search]`
  → Locator timeout 5000ms (the search UI uses a different element /
  needs a click-to-open). 3 XHRs captured (Google Analytics, hyperscript
  asset, Bugsnag session) — no document-search API call.

**Production-adapter requirements** (deferred, punch-list):
- Identify the SPA's search-input element (likely a `<button>` opening a
  modal `<input>` or a non-standard custom element).
- Capture the `ko-search-api` XHR request signature after reCAPTCHA
  resolves — ESC-002 / HALT-002 documented the runtime-injected endpoint
  + Google reCAPTCHA gating.
- Either a CAPTCHA solver (cost-gated per §4.14) or an operator-seeded
  session per §4.14 E1.
- Doc-type discovery is already complete (10 groups, 190 types, saved at
  `runs/smith_tx/recon/clerk_doc_type_taxonomy.json`).

## What WAS built this turn (stdlib only)

- `scrapers/pbfcm_smith_tax_resale.py` — Tyler-ISD struck-off PDF
  (4 evergreen records, pure-stdlib zlib+regex parsing).
- `scrapers/county_excess_proceeds.py` — District Clerk Registry & Trust
  PDF (29 sheriff_sale_surplus rows with net > 0, party-name resolved to
  DF for §17 fallback).
- `scrapers/_pdf_text.py` — pure-stdlib PDF text extractor used by both.

## Status

Chromium binary is on disk and importable. The fingerprint / session
work to make the two SPA adapters production-grade is a real follow-on
ticket (each probably one focused session). Smith now ships:

    sources active:        3  (LGBS, PBFCM, county Excess Proceeds)
    lead types on board:   2  (Tax Foreclosure Notice, Sheriff Sale Surplus)
    lead_total:            63
    §20 verdict:           DEPLOY_OK
    Playwright adapters:   recon complete, deferred
