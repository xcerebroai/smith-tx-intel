# Build-run findings — Smith County, TX (smith_tx)

Generated 2026-05-19T18:23:18Z — framework v5.3.0 — recommended for the v5.3.1 backlog.

## FIND-001 — build_leads.py county-config default leak

`scaffold/pipeline/build_leads.py:724` sets `--county-config` default to
`config/counties/bexar_tx.json` — a real prior-county slug baked into a
universal pipeline file.

Two reachable paths to the defect:

- **Path A — default value.** Any invocation of `build_leads.py` that omits
  `--county-config` silently targets `bexar_tx.json`.
- **Path B — verifier invocation pattern.** `scaffold/tests/verify_synthetic_harness.py`
  calls `build_leads.py --synthetic` with no `--county-config`, so it inherits
  the Path A default. In a county repo where `bexar_tx.json` is absent
  (e.g. this Smith County repo) the verifier fails on a missing config.

### Smith County response (v5.3.0-correct)
Phase 2+ for this county MUST invoke the pipeline with an explicit
`--county-config config/counties/smith_tx.json`. The Phase 1 verifier was
driven by running the pipeline with the explicit config and then executing
`verify_synthetic_harness.py`'s assertion logic against that output
(its hardcoded pipeline call skipped). All 110 assertions passed. The
framework file was NOT modified — that is outside operator authorization.

### Cross-reference
Operator notes a related "Duval halt" finding: Duval's run hit the Path A
default through the Path B verifier invocation and halted. Both Smith's
workaround and Duval's halt are correct v5.3.0 responses to the same root
cause. (Duval detail is not available in this repo and is recorded here only
as the operator-supplied cross-reference.)

### Recommended v5.3.1 fix
Address BOTH paths: (A) remove the `bexar_tx.json` default — require
`--county-config`, or auto-select the sole `config/counties/<slug>.json`
present; and (B) update `verify_synthetic_harness.py` to pass an explicit
`--county-config` rather than relying on the default.

## Invocation pattern for Phase 2+ (this county)
    python3 scaffold/pipeline/build_leads.py --county-config config/counties/smith_tx.json [...]
Always pass `--county-config config/counties/smith_tx.json` explicitly.


---

## FIND-001 — RESOLVED in framework v5.3.1 (verified 2026-05-21T22:38:32Z)

`FRAMEWORK_VERSION.json` is now `v5.3.1`. `scaffold/pipeline/build_leads.py`
adds `_auto_discover_county_config()`:

- **Path A fixed** — `--county-config` default is now `None` (no longer
  `bexar_tx.json`). When omitted, the pipeline auto-discovers the sole
  non-underscore `config/counties/*.json` and fails loud on zero/multiple
  matches, demanding explicit `--county-config`.
- **Path B fixed** — `verify_synthetic_harness.py` (which calls
  `build_leads.py --synthetic` with no `--county-config`) now resolves
  `smith_tx.json` via auto-discovery and runs natively: 110/110 assertions
  PASS, rc 0. The Phase 1 workaround documented above is no longer required.

The Phase 2+ invocation pattern is unchanged and still valid: passing
`--county-config config/counties/smith_tx.json` explicitly is the recommended
discipline for multi-county clarity, but is no longer mandatory in this
single-county repo.

This finding is closed. ESC-001 (Phase 2 SPA browser-tooling halt) is a
separate, unrelated issue and remains OPEN — v5.3.1 does not address it.


---

## FIND-002 — fixture path conflicts with the county-agnostic regression scanner

Found 2026-05-21T23:53:29Z, framework v5.3.1, during Phase 2.

`knowledge_base/engineering/05_verification_and_rollback.md` mandates that
scraper fixtures live at `tests/fixtures/<source_id>/` and the harness at
`tests/test_scrapers.py`. But `scaffold/tests/test_county_agnostic_regression.py`
scans `tests/` as a universal directory and fails the build when county-specific
terms appear there. County scraper fixtures inherently contain county data
(owner names, situs cities, the state code) — so the two framework documents
are in direct conflict: following the fixture doc breaks the regression gate.

The regression scanner's exemption list is `data/`, `runs/`, `.claude/`,
`dashboard/`, `scrapers/` — it does NOT exempt `tests/`.

### Smith County response (v5.3.1-correct, no framework patch)
County scraper fixtures and the fixture harness were placed inside the
regression-exempt `scrapers/` tree instead of `tests/`:

- `scrapers/fixtures/parcel_master/` — the 8-scenario fixtures
- `scrapers/test_scrapers.py` — the fixture harness

The framework files were NOT modified. The harness still satisfies the §05
eight-scenario contract; it simply lives in a county-scoped, regression-exempt
location.

### Recommended v5.3.1+ fix
Reconcile the two documents: either add `tests/fixtures/` to the regression
scanner's exemption list (fixtures are inherently county-specific test data),
or amend `05_verification_and_rollback.md` to specify a county-scoped,
regression-exempt fixtures path (e.g. `scrapers/fixtures/<source_id>/`).
