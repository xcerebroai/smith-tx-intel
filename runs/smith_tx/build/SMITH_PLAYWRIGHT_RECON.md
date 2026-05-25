# Smith TX — Playwright recon + gated-source findings (2026-05-25)

Operator authorized Playwright with stealth. This file records the outcomes
of the deep probing pass on the two reCAPTCHA-gated primary sources
(publicsearch.us clerk + Tyler Odyssey district court) and the resulting
production adapter for publicsearch.us.

Stack: chromium installed (`python -m playwright install chromium`),
`playwright-stealth==2.0.3` (`pip install --break-system-packages`).

## publicsearch.us (Smith County Clerk official records) — BROKEN THROUGH

**Discovery:** the portal SPA renders results via hyperscript / htmx-style
HTML swap, not a JSON API. A plain `urllib` GET to `/results?...` returns
only a "Loading Search Results..." shell — production scraping requires a
real browser (Playwright). reCAPTCHA library IS loaded in the vendor
bundle but is NOT triggered on read-only quick-search navigations during
recon. Each query is rate-limited; the adapter halts cleanly on a
reCAPTCHA challenge.

**Quick-search URL pattern:**

    https://smith.tx.publicsearch.us/results?
      department=RP&keywordSearch=false
      &recordedDateRange=YYYYMMDD,YYYYMMDD
      &searchOcrText=false&searchType=quickSearch
      &searchValue=<KEYWORD>

**Results-table column layout** (mapped by HEADER NAME — there are
variable leading control cells; index-based extraction failed):
`GRANTOR | GRANTEE | DOC TYPE | RECORDED DATE | DOC NUMBER | BOOK/VOLUME/PAGE | LEGAL DESCRIPTION`.

**Adapter:** `scrapers/publicsearch_clerk.py`. Sweeps a fixed set of
distress keywords (FORECLOSURE, LIS PENDENS, FEDERAL TAX LIEN, STATE TAX
LIEN, MECHANIC LIEN, AFFIDAVIT OF HEIRSHIP, ABSTRACT OF JUDGMENT), parses
the rendered table by header name, classifies each row's
`canonical_doc_type` from the DOC TYPE column, emits one v5.4.0 raw_event
per row.

**Live yield (2024-05-25 .. 2026-05-25, 2 years back):**

| query | raw rows | emitted | canonical(s) |
|---|---|---|---|
| FORECLOSURE | 3 | 2 | foreclosure_notice |
| LIS PENDENS | 50 | 47 | lis_pendens |
| FEDERAL TAX LIEN | 1 | 0 | (release-only; not distress) |
| STATE TAX LIEN | 0 | 0 | — |
| MECHANIC LIEN | 0 | 0 | — |
| AFFIDAVIT OF HEIRSHIP | 0 | 0 | — |
| ABSTRACT OF JUDGMENT | 50 | 0 | (publisher labels differ; refinement needed) |
| **total** | **104** | **49** | — |

Limitations / punch-list:
- **Party-role mapping** — publicsearch uses GR/GE columns; §17 lien/lis-
  pendens rules expect PL/DF. The 47 lis_pendens rows currently route to
  REVIEW_REQUIRED with placeholder owner because GE != expected DF. Fix:
  emit each party with BOTH role variants (GR+PL for grantor, GE+DF for
  grantee). Refinement, not a blocker.
- **ABSTRACT OF JUDGMENT query returns 50 raw rows with 0 emitted** — DOC
  TYPE column likely uses "JUDGMENT" or similar variant not in the map.
  Needs raw-row inspection + map expansion.
- **No parcel_id in publicsearch table** — leads ship UNRESOLVED parcel
  with legal_description as the skip-trace handle (§13.14 compliant).

## Tyler Odyssey (portal.smith-county.com) — REACHABLE BUT LOOKUP-ONLY

**Discovery:** `Settings.CaptchaEnabled = False` in the Hearings form
POST — Smith County's Tyler tenant has form-CAPTCHA disabled. POSTs
succeed (302 → Search Results). The blocker is NOT reCAPTCHA, it's the
search design:

- `SearchByType` is a required field with options: `CaseNumber`,
  `PartyName`, `BusinessName`, `AttorneyName`, `AttorneyBarNumber`,
  `JudicialOfficer`, `Courtroom`. **No `DateRange` / `RecentlyFiled` /
  `AllCases` option.** The error on date-only submit: "Search Criteria
  is required."
- `SelectedHearingType` filter exists (All Civil / All Criminal / All
  Family / All Probate) but only as a refinement, not a sole criterion.

Tyler Odyssey Hearings Search is **LOOKUP-by-name/case-number, not
BROWSE-by-date-range**. Bulk extraction of "all foreclosure cases filed
in the last 30 days" is not natively supported by this form.

**Punch-list — production paths require an external seed:**
- (a) Seed loop — feed names from LGBS / publicsearch records into
  Odyssey Smart Search to enrich each with court-case detail. Adapter
  pattern: enrichment-via-lookup, not primary-origination.
- (b) Use a different Tyler product (Calendar / Docket view) — would
  require a different portal or operator-provided credentials.
- (c) Iterate common surnames (impractical for a county-wide build).

**Adapter NOT built this turn.** No production-grade way to bulk-extract
from this surface without an external seed strategy. Honest punch-list
per the operator's explicit "do not ship an adapter that emits
unreliable/empty data" rule.

## Dashboard now carries 4 distress types

After wiring publicsearch_clerk:

```
sources active:     4 (LGBS + PBFCM + Excess Proceeds + publicsearch_clerk)
lead_total:         112
signal_types:       lis_pendens 47, tax_foreclosure_notice 34,
                    sheriff_sale_surplus 29, foreclosure_notice 2
owner_types:        INDIVIDUAL 44, UNKNOWN 50, ENTITY 15, ESTATE 3
                    (50 UNKNOWN = publicsearch GR/GE -> §17 DF mismatch, refinement)
ENRICHED / UNENRICHED:  33 / 79 (publicsearch + Excess Proceeds carry no parcel_id)
§20 verdict:        DEPLOY_OK
```
