# v5.4.0 Staged Pipeline Run — Smith County, TX

Run: 2026-05-23 — branch `smith-tx-phase0-phase1-delivery` — framework v5.4.0 (commit 266d445)
Driver: `runs/smith_tx/build/run_staged_v5_4_0.py`
Workdir: `runs/smith_tx/build/staged_v5_4_0/`

## Result

**HALT — §20 DEPLOY_BLOCKED.** Dashboard was NOT built; this is one of the
two operator-defined stop conditions. **The halt is correct framework
behavior, not a regression.**

| Stage | Outcome |
|---|---|
| raw_events loaded | 300 (parcel_master.jsonl only) |
| §17 debtor_party_engine | 300 records resolved — all routed REVIEW_REQUIRED (owner role `unresolved`, placeholder `PARCEL_MASTER against unidentified party`) |
| §18 leads_base writer | `parcel_master_leads_base.json` (300 base records) |
| §19 aggregator | 300 → **36 matched_leads** (collapsed by `(parcel_id, canonical_doc_type, signal_type)`) |
| §20 semantic verification | **DEPLOY_BLOCKED** — 1 INVALID check, 1 AMBIGUOUS, 4 VALID, 6 SKIPPED |
| seam / scoring | **NOT RUN** — gated by §20 verdict |
| dashboard | **NOT BUILT** — gated by §20 verdict |

## Why §20 blocked deploy

Check 4 — **Enrichment status decoupling integrity = INVALID**:

> 36 enrichment-only row(s) with no PRIMARY_EVENT_SOURCE signal (No False
> Dashboard, §13.5).

This is exactly the §13.5 "No False Dashboard" rule. Every candidate row in
`matched_leads.json` originated from `parcel_master` (`ENRICHMENT_SOURCE`); no
row was backed by a primary event signal. §20 correctly refused to deploy a
dashboard whose rows would all be enrichment-only — the cardinal Bexar mistake
the framework was built to prevent. This is the framework working.

Secondary finding — Check 5 (Signal aggregation integrity = AMBIGUOUS): the
count vs distinct-`instrument_number` mismatch is the legitimate-null-instrument
branch of §18.E (parcel records carry no recording instrument number), not a
dedup bug.

## What ran (in order)

1. Loaded 300 records from `data/raw/parcel_master.jsonl`.
2. **Bridged each record at the call site** from the §4.32 wrapped raw-record
   shape (which the parcel_master adapter emits) into the v5.4.0
   `raw_event_record.schema.json` shape — supplying the new top-level fields
   the v5.4.0 contract requires (`raw_event_id`, `source_role=ENRICHMENT_SOURCE`,
   `canonical_doc_type="PARCEL_MASTER"`, `parties=[]`, `property_refs` built
   from `raw_payload`). No `scaffold/` edit; the adapter is unmodified.
3. Called `scaffold.pipeline.run_pipeline_staged.run_staged_pipeline(...)` with
   `approve_needs_review=True` (operator rule: AMBIGUOUS → continue).
4. The orchestrator drove §17 → §18 → §19 → §20 cleanly. On the §20
   DEPLOY_BLOCKED verdict it raised `SemanticGateBlocked`, blocking the seam
   and dashboard stages — the documented gate behavior.
5. Re-ran `semantic_verify.run_semantic_verification` directly on
   `matched_leads.json` to capture the full §20 report
   (`semantic_verify_report.json`) — the orchestrator raises before returning
   the report, so this is the only way to inspect WHY on a halt.

## §20 detail (12 checks)

    [1]  Debtor attribution sampling                  VALID    — no resolved owner_name matches a known filer pattern (full scan of 36)
    [2]  Owner type classification sampling           VALID    — full scan of 0 resolved (no resolved owners — REVIEW_REQUIRED everywhere)
    [3]  Parcel-resolution plausibility               SKIPPED  — deploy-time check (§20.H)
    [4]  Enrichment status decoupling integrity       INVALID  — 36 enrichment-only rows with no PRIMARY_EVENT_SOURCE (§13.5)
    [5]  Signal aggregation integrity                 AMBIGUOUS — 36 signals with count above distinct instrument-number (legitimate-null-instrument)
    [6]  Cross-source aggregation integrity           VALID    — every signal has a distinct, self-consistent aggregation key (§18.F)
    [7]  OCR confidence routing                       SKIPPED  — deploy-time data not on matched_leads.json
    [8]  CSV output schema validation                 SKIPPED  — deploy-time artifact
    [9]  Source proof link validation                 SKIPPED  — requires live source-URL resolution
    [10] Dashboard row integrity                      SKIPPED  — requires browser automation against rendered dashboard
    [11] Methodology consistency                      SKIPPED  — requires the build report
    [12] Filer-as-owner spot check (universal)        VALID    — no universal filer pattern appears as owner_name

## Artifacts produced

    runs/smith_tx/build/staged_v5_4_0/
      parcel_master_leads_base.json    — §18 per-source base file (300 base records)
      matched_leads.json               — §19 aggregator output (36 matched_leads, all REVIEW_REQUIRED)
      evidence_ledger.json             — empty (no evidence_entries supplied)
      semantic_verify_report.json      — §20 report verbatim (12 checks)
      halt_deploy_blocked.json         — terse halt marker from the orchestrator gate
      punch_list.json                  — 12 punch-list items (P-001 .. P-012)
      V5_4_0_RUN_REPORT.md             — this report
    runs/smith_tx/build/
      run_staged_v5_4_0.py             — the driver (committed for reproducibility)

`scored_leads.json` and `dashboard/data.json` were NOT produced — the §20
gate blocked them. This is correct.

## Counts the operator asked for

    Dashboard built:           NO (DEPLOY_BLOCKED)
    Lead count:                0 active leads (36 matched_leads all REVIEW_REQUIRED, none scored / shipped)
    REVIEW_REQUIRED count:     36 (every matched_lead; 36/36 owner rows REVIEW_REQUIRED)
    §20 verdict:               DEPLOY_BLOCKED
    Stop condition triggered:  §20 DEPLOY_BLOCKED
    Punch-list size:           12 items (1 BLOCKING category for §20, 3 BLOCKING for coverage / primary-source, others MAJOR / INFO / MINOR)

## How to unblock

The §20 verdict will flip to DEPLOY_OK only when at least one PRIMARY_EVENT_SOURCE
adapter is built and produces real records. That requires:

- **Playwright + Chromium** to capture the runtime-injected `ko-search-api`
  document-search XHR for the County Clerk source (ESC-002), and to drive the
  Tyler Odyssey district-court SPA and the RealAuction tax/sheriff sale platform.
- **A reCAPTCHA path** for the clerk source — operator-seeded session
  (§4.14 E1) or an approved CAPTCHA solver.
- Optionally, the v5.4.0 doc-type normalization stage (Build Mode Protocol §02.3)
  wired into the staged orchestrator so adapters emitting the §4.32 wrapped
  shape don't need driver-side bridging.

When any one PRIMARY_EVENT_SOURCE adapter ships real raw events, re-run
`runs/smith_tx/build/run_staged_v5_4_0.py` — the parcel_master enrichment
already in `data/raw/` will then decorate those real leads (via the
`enrichment_provider` seam) rather than masquerade as them.
