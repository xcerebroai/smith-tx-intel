# Phase 0 — Documented API Discovery — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

Per §01.23. Recon performed web-level API discovery for each candidate source.
Direct probing of /api, /swagger, /docs paths and live network inspection is a
Build-Mode task and is NOT performed during metadata-only recon.

## Paths / locations checked (web search level)
    <domain>/api, <domain>/swagger, <domain>/api/swagger, <domain>/docs,
    <domain>/api-docs ; Postman public collections ; GitHub "<vendor> api".

## Findings
    clerk_recordings (publicsearch.us / GovOS): no public/documented API or Swagger
        found. The portal is a SPA backed by an internal JSON API — recommend
        hidden-API discovery via network inspection in Build Mode (preferred over
        HTML scraping). api_discovery_status = NOT_FOUND (documented).
    district_court (Tyler Odyssey): no public/documented API. Odyssey is SPA-backed
        by an internal API; hidden-API discovery in Build Mode. NOT_FOUND (documented).
    sheriff_tax_auctions (RealAuction): no public/documented API; portal returns 403
        to automated requests. NOT_TESTED beyond the 403.
    tax_collector: no public/documented API; portal returns 403. NOT_TESTED.
    parcel_master (Smith CAD esearch): no documented REST API; a bulk downloads page
        exists (preferred ingest path). NOT_FOUND (documented API); BULK_FILE available.
    gis_parcels (ArcGIS): ArcGIS REST feature services are the de-facto API for this
        source — FOUND (ArcGIS REST). Standard ArcGIS query endpoints apply.
