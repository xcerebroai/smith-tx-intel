# Phase 0 — Source Coverage Map — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

## Live primary sources
    clerk_recordings — County Clerk recordings (publicsearch.us) — SEARCH_ONLY_PUBLIC.
        The moat: foreclosure notices, liens, lis pendens, judgments, tax liens,
        heirship/estate instruments. Daily cadence.
    district_court — District Clerk Odyssey portal — SEARCH_ONLY_PUBLIC.
        Civil judgments, divorce, delinquent-tax suits.

## Blocked sources (technical — HTTP 403 anti-bot)
    sheriff_tax_auctions — RealAuction tax/sheriff auctions. next: use_playwright /
        use_stealth_browser in Build Mode.
    tax_collector — county property-tax portal. next: use_playwright in Build Mode.

## Limited-coverage lead types
    Tax Delinquency, Probate, Code Lien

## Not-found lead types
    Demolition, Condemnation

## Operator-review-required lead types
    Eviction, Surplus  (plus Bankruptcy — PACER paywall)

## Enrichment
    parcel_master (Smith CAD) and gis_parcels (Smith County Map Site) — both
    OPEN_PUBLIC; bulk data available.

## Lead-type sweep tally (27 canonical types)
    live / live-limited: 18    blocked: 3    paid: 1
    not found: 2    not applicable in TX: 1    operator review: 2
