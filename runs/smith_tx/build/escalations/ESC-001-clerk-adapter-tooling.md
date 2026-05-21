# ESC-001 — Phase 2 clerk adapter blocked by execution-environment tooling

Raised: 2026-05-19T18:25:34Z
County: smith_tx   Phase: 2   Severity: build-blocking
Routed per Build Mode Protocol §02.10.

## Context
Build Mode reached Phase 2 (first real adapter) with verdict READY_TO_BUILD,
operator standing authorization for REVIEW_GATE_2..6, and halt conditions armed.

The Phase 2 target — the Smith County Clerk publicsearch.us adapter — cannot be
built in this execution environment. publicsearch.us is a JavaScript SPA backed
by an undocumented internal API; building the adapter requires live browser
network inspection (Playwright / DevTools / a HAR capture). This environment has
no browser and no network-inspection tooling, and v5.3.0 ships no
`_publicsearch_portal.py` protocol client (§4.32 "Future"). See halt_log.md
HALT-001 for the full attempt record.

This is an environment/tooling gap, not a county-source defect and not a
framework logic bug. It generalizes to every remaining Build Mode phase
(SPA scraping, RealAuction browser strategy, Phase 6 Playwright verification,
Phase 8 GitHub Pages deploy).

## Recommended action (operator decision required)
Pick one:

  A. Run Build Mode Phases 2–8 in a full Claude Code environment that has
     Playwright/Chromium, a Python venv with the scraping dependencies
     (requests, httpx, playwright, pdfplumber, etc.), and GitHub auth for the
     Pages deploy. Re-enter Build Mode there; Phase 0 recon + config + the
     Phase 1 synthetic pass in this repo are complete and reusable as-is.

  B. Provide Build Mode the missing inputs for this environment: a seeded
     browser session or a network HAR capture of a publicsearch.us search, so
     the internal API contract can be discovered without a live browser here.

  C. Re-scope: treat this run as Phase 0 + Phase 1 delivery only (recon dossier,
     validated county config, synthetic harness green) and schedule Build Mode
     Phases 2–8 separately on provisioned infrastructure.

## Operator decision
    decision:        <A | B | C | other>
    decided_by:
    decided_at:
    notes:

## Do not auto-resume
Per §02.9 the build does not auto-resume. It waits for this decision.
