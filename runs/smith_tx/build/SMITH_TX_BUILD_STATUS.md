# Smith County, TX — Build Status

County: Smith County, Texas (`smith_tx`) — FIPS 48423 — county seat Tyler
Framework: recon/config under v5.3.0; Phases 1–2 verified under v5.3.1;
v5.4.0 staged pipeline (commit 266d445) — first run 2026-05-23 returned
§20 DEPLOY_BLOCKED (correct — only enrichment data was available);
v5.4.0 re-run 2026-05-25 with the first PRIMARY_EVENT_SOURCE adapter — **DEPLOYED**.
Status: **DEPLOYED (partial build) — 31 lead rows, §20 DEPLOY_OK**
Empirical primary-source hunt 2026-05-25 found Linebarger's `taxsales.lgbs.com`
JSON API is stdlib-reachable (HTTP 200, JSON, no auth, no CAPTCHA, 31 current
Smith records with property attachment proven for every row). Built
`scrapers/lgbs_smith_tax_sales.py` (stdlib only), wired into
`config/counties/smith_tx.json`, ran §17→§20 end-to-end — §20 = DEPLOY_OK —
dashboard built at `dashboard/data.json`. The clerk, district court,
RealAuction, tax portal, and Tyler-code primary sources are still
ESC-002-blocked (browser + reCAPTCHA required).
Status date: 2026-05-25 (first PRIMARY source live; dashboard deployed)

---

## Summary

This run delivered a verified recon dossier, a green synthetic harness, and a
built-and-tested parcel-master ENRICHMENT adapter for Smith County, TX. Build
Mode then halted at Phase 3 — the first PRIMARY EVENT SOURCE — because the
County Clerk records portal is a reCAPTCHA-gated React SPA whose document API
is runtime-injected, which requires browser-grade tooling this execution
environment does not provide. The framework halted per Build Mode Protocol
§02.9 — it did not fabricate lead rows or a dashboard. The operator has since
completed a wide manual recon (36 candidate sources), captured as unverified
input. The Smith County build is **ON HOLD — parked pending the v5.4.0 pipeline
engine**: a temporary hold, not a final delivery. Phases 0–2 carry over
unchanged; at the post-v5.4.0 resume a wide Phase 0 re-recon runs first, then
Build Mode continues.

---

## Phase 0 — County Source Recon — COMPLETE

Build Eligibility verdict: **READY_TO_BUILD**.

- Source-of-Record Matrix for all 27 canonical lead types
  (`runs/smith_tx/recon/source_of_record_matrix.json` / `.md`).
- 6 sources verified through the five-layer gate.
- 14 recon artifacts + 6 per-source fingerprints; schema-validated
  `config/counties/smith_tx.json`.
- `REVIEW_GATE_1` signed (`proceed_full`).

## Phase 0 — Wide-Recon Input Captured (2026-05-21)

The operator completed a wide manual recon of Smith County / Tyler — **36
candidate lead sources** across tax-foreclosure auctions, clerk records, court
portals, tax-sale law-firm and struck-off resale portals, legal-notice
publication portals, third-party auction/REO aggregators, parcel/CAD, the
county excess-proceeds report, and City of Tyler code-enforcement portals.

Captured verbatim, as **UNVERIFIED INPUT**, to
`runs/smith_tx/recon/operator_source_dossier_2026-05-21.md`. This supersedes
the original shallow Phase 0 (6 verified sources). It has NOT been probed,
NOT §13-classified, NOT written into `config/counties/smith_tx.json`, and the
§16 matrix has NOT been rebuilt from it. A full wide Phase 0 re-recon —
empirical probe (HTTP status, access class, stdlib reachability) plus §13
classification of every source, then a §16 matrix rebuild — is scheduled for
the post-v5.4.0 resume. See `runs/smith_tx/recon/RECON_REOPEN_PENDING.md`.

## Phase 1 — Synthetic Data Harness — VERIFIED

- Universal pipeline run end-to-end on the framework synthetic fixtures with
  `config/counties/smith_tx.json`.
- Phase 1 verifier: **110/110 assertions PASS** (framework v5.3.1).
- Framework gate suite `run_all.py`: PASS (4/4).
- Detail: `runs/smith_tx/build/phase1_synthetic_report.md`.

## Phase 2 — Enrichment Foundation Adapter — BUILT

Per the corrected build sequencing, Phase 2 builds the ENRICHMENT FOUNDATION
first (not a lead source). Per §13, parcel data decorates leads — it never
originates one. This phase produced zero signals and zero lead rows.

- **Source discovered:** Smith County GIS open ArcGIS REST "Tax Parcels"
  layer — `Gallery/TaxParcelQuery/MapServer/1`, 141,692 parcels, no auth,
  no CAPTCHA. (Supersedes the Phase 0 esearch guess.)
- **Adapter built:** `scrapers/parcel_master.py` — emits §4.32 wrapped raw
  records via the framework ArcGIS helper; stale Bexar scrapers deleted.
- **Verified:** `scrapers/test_scrapers.py` 8-scenario fixture harness —
  33 assertions pass. Live full-layer coverage: ACCOUNT 99%, owner 98%,
  situs address 96%. Framework gate green (4/4).
- Committed to branch `smith-tx-phase0-phase1-delivery`
  (commit "Phase 2 ENRICHMENT FOUNDATION only — no lead origination").
- A dashboard is NOT buildable from this output — enrichment cannot
  originate lead rows.

## Phase 3 — First Primary Event Source — BLOCKED (ESC-002)

Target: `clerk_recordings` — the Smith County Clerk Official Public Records
(`https://smith.tx.publicsearch.us/`). This is the real lead-origination
test; lead rows must originate from a primary event source, not enrichment.

**What Phase 3 discovered** (genuine hidden-API discovery from the
now-network-capable build runtime):

- Backend is **`ko-search-api`** (Kofile / GovOS Cloud Search), a React SPA.
- Tenant config server-rendered: `tenantId 48423`, Smith County, clerk Phillips.
- The **clerk document-type taxonomy was fully enumerated** — 10 groups,
  190 doc types — saved to `runs/smith_tx/recon/clerk_doc_type_taxonomy.json`.
  Lead-bearing groups: `[FC] Foreclosures`, `[RP] Land Records` (87 types),
  `[GVRN]`, `[CCM]`, `[MISC]`.
- `/results` server-renders only an empty `isLoading` shell — document
  records load via a client-side XHR.
- The document-search XHR endpoint base is **runtime-injected** (not a static
  literal in any JS bundle) — capturing it needs browser network inspection.
- The vendor bundle loads **Google reCAPTCHA** — the search is reCAPTCHA-gated.
  (This corrects the Phase 0 `captcha NONE` classification; the
  `clerk_recordings` config block and fingerprint are updated to match.)

**Blocker.** Two compounding blockers: (1) the `ko-search-api` endpoint is
runtime-injected → needs Playwright/DevTools network capture; (2) the search
is reCAPTCHA-gated → needs an operator-approved solver or a seeded session
(§4.14, operator-gated). Both require tooling/authorization this environment
lacks. Guessing the contract is prohibited by §7. Halted per §02.9 —
`runs/smith_tx/build/halt_log.md` (HALT-002),
`runs/smith_tx/build/escalations/ESC-002-clerk-primary-source.md`. No lead
output was fabricated.

## This is a source-reality / environment blocker — NOT a framework defect

The framework behaved as designed: it fingerprinted the SPA during recon,
entered Build Mode through the gates, built the enrichment foundation,
attempted the primary source with real discovery, and halted cleanly per
§02.9 rather than fabricate lead rows from enrichment (the §4 / §13 product
rule). The blocker is the reality of the source (a reCAPTCHA-gated SPA with a
runtime-injected API) meeting the reality of this environment (no browser
tooling). The County Clerk source is buildable — by a properly-provisioned
Claude Code instance with Playwright — and this run got far enough to hand
that instance the doc-type taxonomy, tenant id, and backend identity.

---

## Infrastructure required to resume Build Mode (Phase 3 onward)

- **Playwright + Chromium** — to capture the `ko-search-api` document-search
  XHR, render the clerk and Tyler Odyssey SPAs, run the RealAuction
  `use_playwright` strategy, and perform the Phase 6 live-verification gate.
- **A reCAPTCHA path for the clerk source** — an operator-approved CAPTCHA
  solver (§4.14 `use_captcha_solver`, cost-gated) or an operator-seeded
  session (§4.14 E1 `use_seeded_session`).
- **A Python environment with the scraping dependencies** — `requests`,
  `httpx`, `playwright`, `beautifulsoup4`/`lxml`, `pdfplumber`/`PyMuPDF`,
  `openpyxl` (per `engineering/01_python_environment.md`, `02_scraping_libraries.md`).
- **GitHub authentication + a private repo** — for the Phase 8 GitHub Pages
  deploy. `deployment.github_org` is still the `{{GITHUB_ORG}}` placeholder.
- Network egress to the county portals.

Note: per v5.3.x VERSION_NOTES (§4.27, §4.39), the production live-browser
verifier, watchdog, and semantic verifier ship as contract-surface/stubs —
Phase 6 production verification is a per-county responsibility on that
infrastructure.

When re-entered on provisioned infrastructure, Phases 0–2 carry over unchanged.

---

## Carry-over assets (reusable as-is)

- `config/counties/smith_tx.json` — schema-validated config, 6 sources,
  27-type SoR matrix; `parcel_master` and `clerk_recordings` blocks updated
  with Build-Mode discoveries.
- `runs/smith_tx/recon/` — recon artifacts, 6 fingerprints, and
  `clerk_doc_type_taxonomy.json` (the enumerated clerk doc-type taxonomy).
- `scrapers/parcel_master.py` + `scrapers/test_scrapers.py` +
  `scrapers/fixtures/parcel_master/` — the built, fixture-verified
  enrichment adapter.
- `runs/smith_tx/gates/` — REVIEW_GATE_1..6 signoffs.
- `runs/smith_tx/build/` — Phase 1 report, findings (FIND-001 resolved,
  FIND-002), halt log (HALT-001/002), ESC-001/002, this status report.
- `runs/smith_tx/operator_notes.md` — operator build-scope decisions.

## v5.4.0 Staged Pipeline Run (2026-05-23) — §20 DEPLOY_BLOCKED

v5.4.0 (commit 266d445) shipped on this branch. The staged pipeline was run
end-to-end by `runs/smith_tx/build/run_staged_v5_4_0.py` against the only raw
data available — `data/raw/parcel_master.jsonl` (300 ENRICHMENT records). The
driver bridged the §4.32 wrapped shape into the v5.4.0 `raw_event_record`
schema at the call site (county-scoped data adaptation, no `scaffold/` edit).

Pipeline outcome:

    §17 debtor_party_engine  300 raw -> 300 debtor_resolved  (all REVIEW_REQUIRED)
    §18 leads_base writer    parcel_master_leads_base.json   (300 base records)
    §19 aggregator           300 -> 36 matched_leads          (collapsed by §18 key)
    §20 semantic verify      DEPLOY_BLOCKED                   (HALT)
    seam / scoring           NOT RUN  (gated by §20)
    dashboard                NOT BUILT (gated by §20)

The §20 INVALID check is **Check 4 (Enrichment status decoupling integrity)**:
"36 enrichment-only row(s) with no PRIMARY_EVENT_SOURCE signal (No False
Dashboard, §13.5)." This is correct framework behavior — the §13.5 rule blocks
deploy because every candidate row originates from enrichment, not from a
primary event source. The framework prevented the Bexar mistake from
happening on Smith. **The halt is success, not regression.**

Full detail: `runs/smith_tx/build/staged_v5_4_0/V5_4_0_RUN_REPORT.md`,
`semantic_verify_report.json`, `matched_leads.json`, `punch_list.json`
(12 items: 4 BLOCKING / 2 MAJOR / 1 MINOR / 5 INFO).

## v5.4.0 Re-Run (2026-05-25) with the first PRIMARY EVENT SOURCE — DEPLOY_OK

Empirical primary-source hunt (18 dossier candidates probed; full report at
`runs/smith_tx/build/SMITH_PRIMARY_SOURCE_HUNT.md`) found the Linebarger
(LGBS) JSON API at `taxsales.lgbs.com/api/property_sales/` is stdlib-
reachable: HTTP 200, JSON, no auth, no CAPTCHA, 31 current Smith County
records, 100% with `account_nbr + prop_address_one + cause_nbr` — property
attachment proven for every row (Duval JUDGMENT standard met).

Adapter built: `scrapers/lgbs_smith_tax_sales.py` (stdlib only). Wired the
`lgbs_smith_tax_sales` source into `config/counties/smith_tx.json`. Ran
the v5.4.0 staged pipeline:

    raw_events:        31 (LGBS PRIMARY_EVENT_SOURCE — parcel_master intentionally
                          NOT fed to §17 per operator stage-boundary rule)
    §17 debtor_resolved: 31  (all REVIEW_REQUIRED — LGBS API has NO party names;
                              §17.D missing_debtor_behavior fires; correct)
    §18 leads_base:      31
    §19 matched_leads:   31
    §20 verdict:         DEPLOY_OK
    seam scored_leads:   31  (all UNENRICHED — no enrichment_provider wired;
                              correctly scored "Workable" tier on the tax pattern)
    dashboard:           dashboard/data.json — 31 lead rows, build_label PARTIAL_BUILD
                         pattern_counts: {"tax": 31}
                         score_tier_distribution: {"Workable": 31}
                         deal_path_distribution: {"wholesale": 31}

Doc-type fix (2026-05-25): the initial run mapped LGBS sale_type to the
unregistered string `TAX_FORECLOSURE_SALE` (fell through §17's F-5 default →
empty pattern_counts, all "Archive" tier). Verified §17 / canonical_doc_types.json
/ doc_type_bridge.py registrations and remapped both `SALE` and `STRUCK OFF`
to the registered canonical **`tax_foreclosure_notice`** (lowercase per §17
rule keys; bridges to §16 lead type "Tax Lien Foreclosure", lead_pattern "tax").
Adapter + config `doc_type_synonyms` updated; pipeline re-run; pattern_counts
now correctly emits the tax pattern for every row.

Other stdlib-reachable primary sources discovered but deferred:
`pbfcm_smith_tax_resale.pdf` (4 Tyler-ISD struck-off; pure-stdlib zlib+regex
parseable) and the county Excess Proceeds PDF (Surplus lead type;
operator-scoped-out earlier).

## Session outcome

Smith County, TX is **DEPLOYED (partial build)** — `dashboard/data.json`
carries 31 real Smith County tax-foreclosure lead rows from the LGBS
primary event source. All 31 are correctly flagged `REVIEW_REQUIRED`
because the LGBS API does not carry party names (the §17 placeholder owner
reads `"TAX_FORECLOSURE_SALE against unidentified party"`); owner-name
enrichment is a downstream attachment from `parcel_master` via the
`account_nbr` / `parcel_id` join, not a §17 input — per the operator's
stage-boundary rule.

What remains (punch-list):
- Add `scrapers/pbfcm_smith_tax_resale.py` (stdlib PDF adapter) as a second
  primary source for Tyler-ISD tax-sale coverage.
- Wire the `parcel_master` enrichment_provider into the seam so owner /
  situs / value display on the rendered dashboard rows.
- The clerk (`publicsearch.us`), district court (Tyler Odyssey),
  RealAuction, tax portal, and Tyler code-enforcement primaries still need
  Playwright + a reCAPTCHA path — ESC-002 unchanged.
