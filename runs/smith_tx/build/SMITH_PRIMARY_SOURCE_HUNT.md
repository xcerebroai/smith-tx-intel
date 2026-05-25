# Smith County, TX — Primary-Event-Source Hunt Report

Run: 2026-05-25 — branch `smith-tx-phase0-phase1-delivery` — framework v5.4.0
Method: empirical probing (HTTP fetch from build runtime, header + body
fingerprint, SurplusIQ recon protocol — event data must be in raw HTML/JSON/
PDF before recommending an adapter; no claims from the dossier accepted
unverified).

## Result

**STDLIB-REACHABLE PRIMARY EVENT SOURCE FOUND.**

Selected: **`lgbs_smith_tax_sales`** — Linebarger's Smith County tax-sale
JSON API at `https://taxsales.lgbs.com/api/property_sales/?county=SMITH+COUNTY&state=TX`.
Officially-linked from `https://www.smith-county.com/358/Delinquent-Tax-Sales`
(the county tax page names Linebarger as the delinquent-tax attorney for
Smith County and most taxing units). Probe 2026-05-25: HTTP 200, JSON, no
auth, no CAPTCHA, no SPA gating, 31 current Smith County records, 100%
with `account_nbr + prop_address_one + cause_nbr` — property attachment
proven for every row (Duval JUDGMENT standard met).

## Candidates probed (18) — empirical results

    label                       url                                                   status  classification          notes
    --------------------------  ----------------------------------------------------  ------  ----------------------  -----
    county_foreclosures_298     smith-county.com/298/Foreclosures                     200     HTML_INFO_ONLY (kw=3)   instructional only; directs to publicsearch
    county_foreclosures_459     smith-county.com/459/Foreclosure-Sale-Notices         200     HTML_INFO_ONLY          dossier-alt URL of same info page
    county_delinquent_358       smith-county.com/358/Delinquent-Tax-Sales             200     HTML_INFO_ONLY          confirms LGBS handles general + Tyler-ISD via PBFCM
    county_delinquent_458       smith-county.com/458/Delinquent-Tax-Sale-Notices      200     HTML_INFO_ONLY          dossier-alt URL of same page
    county_sheriff_354          smith-county.com/354/Sheriff-Sale-Auctions            200     HTML_INFO_ONLY          instructional; points at RealAuction
    realauction_smith           smith.texas.sheriffsaleauctions.com/                  200     LOGIN_WALL              prior 403 was UA-driven; with real UA returns a login shell, NOT listings (event keywords were chrome / nav text, not data)
    excess_proceeds_pdf         smith-county.com/DocumentCenter/View/2032             200     PDF_OK                  PARSEABLE (pure-stdlib zlib+regex): District Clerk Sep 2025 Registry & Trust — case nbrs + party names + balances. STDLIB-REACHABLE primary source for SURPLUS lead type (operator scoped out earlier).
    odyssey_smart_search        portal.smith-county.com/Public/Home/Dashboard/29      200     RECAPTCHA_GATED         confirms Phase 3 ESC-002 — Google reCAPTCHA on Tyler Odyssey SPA
    odyssey_hearings            portal.smith-county.com/Public/Home/Dashboard/26      200     RECAPTCHA_GATED         same
    county_probate              smith-county.com/290/Probate                          200     HTML_INFO_ONLY          links out to Odyssey portal
    pbfcm_taxsale               pbfcm.com/taxsale.html                                200     HTML_INFO_ONLY          links to monthly Smith PDFs but current month was 404 (sale past)
    pbfcm_taxresale             pbfcm.com/taxresale.html                              200     HTML_INFO_ONLY          links to evergreen Smith struck-off PDF
    pbfcm_smith_resale_pdf      pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf 200   PDF_OK                  PARSEABLE: 4 Tyler-ISD struck-off properties (Account / Legal / Address / Cause / Bid / Sale Date / Value). STDLIB-REACHABLE PRIMARY EVENT SOURCE (Tyler ISD only — narrow).
    pbfcm_taxsalesmap           epsilon.pbfcm.com/TaxSalesMap/                        n/a     SSL_EOF                 SSL handshake error; not a viable host today
    lgbs_taxsales               taxsales.lgbs.com/                                    200     SPA_SHELL → API found   Angular SPA, BUT bundle reveals same-origin Django REST API at /api/property_sales/ — STDLIB-REACHABLE JSON, 31 Smith records (probe 2026-05-25). **SELECTED.**
    tx_public_notices           texaspublicnotices.com/                               200     HTML_INFO_ONLY          search portal; root carries no event data
    etx_legal_notices           classifieds.etxclassifieds.com/...legal-notices       n/a     TIMEOUT                 read timeout — slow/anti-bot
    tyler_etrakit_case          trakit.cityoftyler.net/eTRAKiT/Search/case.aspx       200     BLOCKED_WAF + reCAPTCHA Cloudflare challenge + Google reCAPTCHA on Tyler code-enforcement

## Rejected — and why

- **Third-party REO aggregators** (`auction.com`, `xome.com`, `hubzu.com`,
  `texasfile.com`) — not the source of record; the dossier itself flagged
  them as radar, not authority. REJECTED.
- **`publicsearch.us` clerk records / Tyler Odyssey courts / RealAuction /
  publictax / Tyler eTRAKiT** — all reCAPTCHA-gated or WAF-challenged
  (some with both). Require Playwright + reCAPTCHA path (ESC-002).
  REJECTED for stdlib.
- **Smith CAD / GIS / parcel_master** — enrichment-only per §13.4.2 /
  operator stage-boundary rule. EXPLICITLY REJECTED as event source —
  parcel data never originates leads.
- **County `.gov` info pages** (`/298`, `/354`, `/358`, `/459`, `/458`,
  `/290`) — instructional only; no event listings in raw HTML.
  REJECTED as primary.

## Stdlib-reachable PRIMARY sources discovered

1. **`lgbs_smith_tax_sales`** — Linebarger Django REST JSON API. **31
   current Smith County records.** Selected — broader coverage, JSON,
   per-record uid. *Status:* adapter built, pipeline run, dashboard
   deployed.
2. **`pbfcm_smith_tax_resale`** — Perdue Brandon Tyler-ISD struck-off
   resale PDF. **4 evergreen records** (`smithcountytaxresale.pdf`).
   Stdlib-reachable AND stdlib-parseable (pure zlib+regex). Narrower
   coverage (Tyler ISD only); deferred to a second adapter as a
   complement to LGBS.
3. **`excess_proceeds_pdf`** — county District Clerk Registry & Trust
   Accounts PDF (Sep 2025). Stdlib-reachable + parseable. Surfaces
   the SURPLUS lead type. *Scoped out by the operator earlier (2026-05-19)*;
   left for operator decision.

## Recommended next action

Already taken: **built `scrapers/lgbs_smith_tax_sales.py` (stdlib only)**,
wired the `lgbs_smith_tax_sales` source into
`config/counties/smith_tx.json`, ran the v5.4.0 staged pipeline end-to-end,
and built the dashboard. §20 returned **DEPLOY_OK**; `dashboard/data.json`
ships 31 lead rows.

Follow-ups (punch-list):
- Build `scrapers/pbfcm_smith_tax_resale.py` as a complementary stdlib PDF
  adapter (Tyler ISD coverage). The pure-stdlib PDF extractor used in this
  hunt confirms parseability.
- Reconsider the county Excess Proceeds PDF if Surplus is brought back in
  scope.
- The clerk + court + RealAuction + tax-portal + Tyler-code primary sources
  remain ESC-002-blocked (browser + reCAPTCHA required); unchanged.

SMITH NEXT STEP COMPLETE
