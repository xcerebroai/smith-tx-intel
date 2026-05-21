# Phase 0.C — Portal Fingerprints — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

Per-source machine fingerprints are in `fingerprints/<source_id>.fingerprint.json`.
Summary:

## clerk_recordings
    vendor:            GovOS Cloud Search (publicsearch.us)
    architecture:      single-page app, JS-rendered, API-backed
    search_interface:  vendor SPA; internal JSON API ("Search Index Only" /
                       "Search Index & Full Text (OCR)")
    scrape_difficulty: MEDIUM — SPA with discoverable internal API; no CAPTCHA, no login

## district_court
    vendor:            Tyler Technologies — Odyssey Public Access Portal
    architecture:      single-page app; cookies required
    search_interface:  Odyssey "Smart Search" + hearings-by-date
    scrape_difficulty: MEDIUM — SPA; public smart search; document images gated

## sheriff_tax_auctions
    vendor:            RealAuction
    architecture:      JS-rendered auction platform
    search_interface:  auction calendar + per-sale listings
    scrape_difficulty: VERY_HIGH — automated fetch returns HTTP 403 (anti-bot)

## tax_collector
    vendor:            custom county-hosted property-tax portal
    architecture:      undetermined (fetch blocked)
    search_interface:  per-account property-tax search
    scrape_difficulty: HIGH — automated fetch returns HTTP 403 (anti-bot)

## parcel_master
    vendor:            Texas CAD esearch (True Automation / Tyler)
    architecture:      server-rendered HTML search + downloads page
    search_interface:  name/address/property-ID search; bulk downloads page
    scrape_difficulty: LOW — open server-rendered HTML, bulk file available

## gis_parcels
    vendor:            Esri ArcGIS
    architecture:      ArcGIS REST feature services behind a web viewer
    search_interface:  ArcGIS REST query API
    scrape_difficulty: LOW — open ArcGIS REST endpoints
