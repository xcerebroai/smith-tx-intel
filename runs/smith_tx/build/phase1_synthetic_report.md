# Phase 1 — Synthetic Harness Report — Smith County, TX (smith_tx)

Generated: 2026-05-19T18:17:23Z — framework v5.3.0 — Build Mode classification: PARTIAL_BUILD

## Result: PASS

The universal pipeline (`scaffold/pipeline/build_leads.py --synthetic`) was run
against the framework synthetic fixtures (`scaffold/data/synthetic_parcels.jsonl`
12 parcels, `synthetic_signals.jsonl` 24 signals) using the Smith County config
`config/counties/smith_tx.json`. Output written to `data/leads_synthetic.json`.

The Phase 1 acceptance verifier (`scaffold/tests/verify_synthetic_harness.py`)
ran 110 assertions against `scaffold/data/synthetic_expectations.json` — all 110
PASSED, 0 failed. Verifier exit 0.

### Synthetic output summary
    lead_total:              12
    pattern_counts:          bankruptcy 1, code 1, divorce 1, estate 3,
                             eviction 1, foreclosure 3, lien 4, surplus_owed 1,
                             tax 3, tired_landlord 1, transfer 2
    attribute_counts:        absentee 4, entity_owned 1, free_and_clear 1,
                             high_equity 2, long_term_owned 6, multiple_properties 1,
                             out_of_state 2, senior_owner 1, vacant 2
    score_tiers:             Hot 3, Strong 3, Workable 4, Low 2
    deal_paths:              wholesale 11, sub_to 3, messy_title 2,
                             partial_interest 2, flip 1, seller_finance 1,
                             surplus_recovery 1
    stack_depth:             depth-1 6, depth-2 4, depth-3 2

The pipeline, scoring, stacking, deal-path classifier, and dashboard-side JSON
projections all behave correctly end-to-end on fake data before any real Smith
County source is touched — the Phase 1 contract from MASTER_PROMPT §6.

## Framework friction observed (reported, not patched)

`scaffold/pipeline/build_leads.py` defaults `--county-config` to
`config/counties/bexar_tx.json` — a prior-county default baked into a universal
pipeline file. `scaffold/tests/verify_synthetic_harness.py` invokes
`build_leads.py --synthetic` without `--county-config`, so out of the box it
tried to load `bexar_tx.json` (which does not exist in this Smith County repo)
and failed.

Workaround used for this run: the pipeline was invoked directly with
`--county-config config/counties/smith_tx.json`, and the framework verifier's
assertion logic was then driven against that output (its hardcoded pipeline
invocation skipped). All 110 assertions passed.

This is a genuine county-leak observation (a real county slug as a default in a
universal file). It was NOT patched — modifying framework files is outside the
operator's authorization. Recommend the operator decide whether `build_leads.py`
should drop the `bexar_tx.json` default (e.g. require `--county-config`, or
default to the single county config present in `config/counties/`).

## Gate

REVIEW_GATE_2 (end of Phase 1) is now pending operator review. Phase 2 (first
real adapter) cannot begin until `runs/smith_tx/gates/REVIEW_GATE_2.signoff.json`
is in place.
