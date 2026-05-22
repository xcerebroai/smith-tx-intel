# ESC-002 — Phase 3 primary event source (clerk) blocked: runtime-injected reCAPTCHA-gated API

Raised: 2026-05-21
County: smith_tx   Phase: 3 (first primary event source)   Severity: build-blocking
Routed per Build Mode Protocol §02.9 / §02.10. Supersedes the generic ESC-001
characterization of this source with concrete evidence.

## Context
Phase 3 is the real lead-origination test: lead rows originate from the Smith
County Clerk Official Public Records (the moat, source `clerk_recordings`,
https://smith.tx.publicsearch.us/). Phase 2 enrichment is committed; Phase 3
attempts the first PRIMARY EVENT SOURCE.

The build runtime now has network egress, so Phase 3 ran a genuine hidden-API
discovery pass against the live portal — not a repeat of the WebFetch-era
assumption in ESC-001.

## What recon discovered (genuine deep characterization)
- The portal is a React single-page app. Backend is **`ko-search-api`**
  (Kofile / GovOS Cloud Search) — confirmed by a `github.com/kofile/ko-search-api`
  reference in the client bundle.
- Tenant config is server-rendered into `window.__data`: `tenantId 48423`,
  county "Smith County, Texas", clerk "Phillips".
- **The clerk document-type taxonomy was fully enumerated** from the SSR config
  blob — 10 groups, 190 doc types — and saved to
  `runs/smith_tx/recon/clerk_doc_type_taxonomy.json`. Lead-bearing groups:
  `[FC] Foreclosures`, `[RP] Land Records` (87 types), plus `[GVRN]` /
  `[CCM]` / `[MISC]`. This carries over to a future Phase 3 build.
- `/results?q=...&searchType=quickSearch` returns HTTP 200 but the
  server-rendered `window.__data` carries an **empty documents state**
  (`hasFetched:false, isLoading:true`). The actual records are fetched by a
  client-side XHR after page load — a plain-HTTP fetch yields no records.
- The document-search XHR endpoint base is **runtime-injected** — it is not a
  static string literal in `client.js`, `vendor.dll.js`, or the `0.js` chunk
  (all three were fetched and grepped). Capturing it requires observing the
  live SPA's network traffic in a real browser.
- The vendor bundle loads **Google reCAPTCHA** (`/recaptcha/api.js?onload=`).
  The document search is reCAPTCHA-gated.

## Why Phase 3 halts
Two compounding blockers, each requiring tooling or authorization this
execution environment does not have:

1. **Endpoint discovery** — the `ko-search-api` document-search endpoint is
   runtime-injected. Discovering it requires browser network inspection
   (Playwright / DevTools / a HAR capture). This environment has no browser.
2. **reCAPTCHA gate** — even with the endpoint, the search is reCAPTCHA-
   protected. Per MASTER_PROMPT §4.14 a CAPTCHA solver is a cost-gated
   strategy requiring operator approval; per recon protocol §01.17 solving
   CAPTCHAs during recon is forbidden.

Guessing the endpoint or its parameters is prohibited by §7 ("discover ground
truth from the source"). An unvalidated adapter would also fail the
REVIEW_GATE_3 "validated against the live source" contract.

This is a source-reality + environment blocker, not a framework defect. The
framework halted per §02.9 rather than fabricate lead rows. No dashboard, no
lead output, and no scraped clerk records were produced.

## Recon correction (carried into the config)
Phase 0 recon classified `clerk_recordings` as `SEARCH_ONLY_PUBLIC` with
`captcha NONE`. Phase 3 discovery corrects that: the document search is
**reCAPTCHA-gated** and the records require a client-side XHR. The
`clerk_recordings` source block in `config/counties/smith_tx.json` has been
updated to reflect this (captcha status, blocker, next_access_strategy).

## Recommended action (operator decision required)
Resume Phase 3 on infrastructure with:
- **Playwright + Chromium** — to capture the `ko-search-api` document-search
  XHR (endpoint, params, payload) and to render the SPA.
- **A reCAPTCHA path** — either an operator-approved CAPTCHA solver
  (§4.14 `use_captcha_solver`, cost-gated) or an operator-seeded session
  (§4.14 E1 `use_seeded_session` — operator clears reCAPTCHA once, the
  framework replays the session).

Carry-over assets for that resume: the enumerated clerk doc-type taxonomy
(`clerk_doc_type_taxonomy.json`), the tenant id (48423), and the confirmed
backend (`ko-search-api`).

## Operator decision
    decision:        <provide infra A / seeded-session B / solver C / other>
    decided_by:
    decided_at:
    notes:

## Do not auto-resume
Per §02.9 the build does not auto-resume. Phase 2 enrichment stands committed;
Phase 3 waits for this decision.
