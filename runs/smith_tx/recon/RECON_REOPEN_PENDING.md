# Recon Re-Open Pending — Smith County, TX (smith_tx)

Status date: 2026-05-21

## Decision

The Smith County Phase 0 recon must be **re-run wide** when the county build
resumes. Smith is parked until the v5.4.0 pipeline engine ships; the wide
re-recon is the first task of that resume, before any Build Mode work.

## Why the original Phase 0 is insufficient

The original Phase 0 recon (2026-05-19) was shallow. It verified **6 sources**
(`clerk_recordings`, `district_court`, `sheriff_tax_auctions`, `tax_collector`,
`parcel_master`, `gis_parcels`) and treated the County Clerk records portal as
the moat. It did not reach the breadth the operator's manual recon has since
surfaced — legal-notice / newspaper publication portals, tax-sale law-firm and
struck-off resale portals, third-party foreclosure-auction and REO aggregators,
city (Tyler) code-enforcement / permit / CRM portals, and the county excess-
proceeds report. The operator wide-recon dossier surfaces **36 candidate
sources** across those categories.

One Phase 0 classification error was already corrected during Build Mode:
Phase 0 recorded the clerk source `smith.tx.publicsearch.us` as `captcha NONE`.
Phase 3 hidden-API discovery (see `ESC-002` / `HALT-002`) established that the
clerk document search is **reCAPTCHA-gated** and backed by a runtime-injected
`ko-search-api` endpoint. The `clerk_recordings` block in
`config/counties/smith_tx.json` and `recon/fingerprints/clerk_recordings.fingerprint.json`
were corrected accordingly. The wide re-recon must carry that correction
forward and not regress it.

## Input to the re-recon

`runs/smith_tx/recon/operator_source_dossier_2026-05-21.md` — the operator's
manual wide recon, captured verbatim. It is **UNVERIFIED INPUT**: no source in
it has been empirically probed or §13-classified. Per §16.H it is provenance,
not exemption — the re-recon must still discover and verify each source
independently. Note the dossier's body URLs and its reference-list URLs
partially diverge (Foreclosures / Delinquent-Tax-Sales page numbers, the Smith
CAD search host); the empirical probe resolves those.

## What the re-recon must do (post-v5.4.0)

For every source in the dossier (and any the dossier missed):

1. **Empirical probe** — fetch each URL; record HTTP status, access
   classification (§01.9 enum), and stdlib-reachability (does a plain
   `urllib`/`requests` client reach it, or is a browser / WAF bypass /
   reCAPTCHA path required).
2. **§13 classification** — PRIMARY_EVENT_SOURCE / SUPPORTING_EVENT_SOURCE /
   ENRICHMENT_SOURCE / REFERENCE_SOURCE / REJECTED_SOURCE. Third-party
   aggregators (Auction.com, Xome, Hubzu, TexasFile) are radar, not the
   official record authority — classify accordingly.
3. **Rebuild the §16 Source-of-Record Matrix** from the verified results,
   re-running the full 27-type lead-type sweep.
4. **Re-write `config/counties/smith_tx.json`** sources from the verified map.

Until that re-recon completes, NOTHING from the dossier is written into
`config/counties/smith_tx.json` and the §16 matrix is NOT rebuilt. The current
committed config and matrix remain the v5.3.x recon of record.

## Constraints (current — do not violate while parked)

- Do NOT build any adapter from the dossier.
- Do NOT resume Phase 3.
- Do NOT write dossier sources into `smith_tx.json`.
- Do NOT rebuild the §16 matrix now.
- Smith County stays **parked** until v5.4.0 ships.
