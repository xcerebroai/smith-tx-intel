# Phase 0.D — Access Classification — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

Enum per §01.9 / §16.F. Recon is metadata-only; no forbidden action was taken.

## clerk_recordings — SEARCH_ONLY_PUBLIC
    evidence: Portal loads a public search form (grantor/grantee, subdivision, doc
              type, doc #). Two free search modes ("Search Index Only",
              "Search Index & Full Text (OCR)"). Sign-in is optional; no CAPTCHA
              observed. A shopping cart / checkout gates certified document images.
    notes:    Search-result metadata is free and sufficient to originate leads;
              only document IMAGES are payment-gated. Acceptable for the framework.

## district_court — SEARCH_ONLY_PUBLIC
    evidence: Tyler Odyssey public portal; "Smart Search" and hearings-by-date are
              public. "Register / Sign In" present; cookies required. Document
              images / some case types are gated behind registration.
    notes:    Index/case-metadata search is public; treat as SEARCH_ONLY_PUBLIC.

## sheriff_tax_auctions — BLOCKED
    evidence: Automated HTTPS fetch returned HTTP 403 Forbidden (anti-bot). The
              RealAuction platform is publicly browsable for a human and free
              bidder registration exists, but recon could not reach it.
    notes:    Technical blocker. See Phase 0.5 — auto-resolve.

## tax_collector — BLOCKED
    evidence: Automated HTTPS fetch returned HTTP 403 Forbidden (anti-bot).
    notes:    Technical blocker; per-account lookup only (no public bulk roll).

## parcel_master — OPEN_PUBLIC
    evidence: Free public property search; a Downloads page hosts GIS / appraisal
              data. No login or payment for search.
    notes:    Enrichment source; fully accessible.

## gis_parcels — OPEN_PUBLIC
    evidence: Public ArcGIS parcel viewer and REST services.
    notes:    Enrichment source; fully accessible.
