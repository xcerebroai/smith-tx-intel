# Recon Summary — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

County: Smith County, Texas — county seat Tyler — FIPS 48423 — America/Chicago.
Texas is a non-judicial-foreclosure state; substitute-trustee sales occur on the
first Tuesday of each month and the notices are recorded with the County Clerk.

## Build Eligibility Gate verdict: READY_TO_BUILD

The recon found and verified six official sources. The County Clerk's Official
Public Records portal (GovOS Cloud Search at smith.tx.publicsearch.us) is a
verified primary lead source with free, login-free, CAPTCHA-free index search —
this is the moat and it covers the bulk of the 27 canonical lead types. The
District Clerk's Tyler Odyssey portal adds civil judgments, divorce, and
delinquent-tax suits. Smith CAD and the county GIS supply enrichment.

Two primary sources are blocked by anti-bot protection (HTTP 403): the RealAuction
tax / sheriff auction platform and the county property-tax portal. Both are
technical blockers with a clear Build-Mode resolution path (real browser); neither
gates the build because the County Clerk source already satisfies the P0 gate.

Municipal lead types (Demolition, Condemnation) have no county-level source.
Eviction (JP courts) and Surplus (excess proceeds) need operator review.
Bankruptcy is federal/PACER (paid). Tax Sale Certificate is not applicable —
Texas is a redeemable tax-deed state.

Detail: see `build_eligibility_report.md`, `source_of_record_matrix.md` /
`.json`, `source_coverage_map.md`, and the Phase 0.A–0.F artifacts in this folder.

## Next phase
    Verdict is READY_TO_BUILD. The build awaits explicit operator authorization at
    the Build Mode Approval Gate (MASTER_PROMPT §4.15).
