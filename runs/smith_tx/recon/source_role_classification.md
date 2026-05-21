# Phase 0.E — Source Role Classification — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

Per §13 (Lead Origination Contract) and §16.E.

## clerk_recordings — PRIMARY_EVENT_SOURCE
    rationale: County Clerk recorded instruments (deeds, deeds of trust, liens, lis
               pendens, substitute-trustee-sale notices, abstracts of judgment,
               federal/state tax liens, probate instruments) are officially-recorded
               distress / transfer / encumbrance events. §13.2.

## district_court — PRIMARY_EVENT_SOURCE
    rationale: District-court filings originate civil-judgment, divorce, and
               delinquent-tax-suit leads, and supply supporting detail for
               foreclosure. §13.2.

## sheriff_tax_auctions — BLOCKED_SOURCE
    rationale: A primary event source (sheriff / tax-foreclosure sales) that is
               currently inaccessible to automated recon (HTTP 403). §16.E.

## tax_collector — BLOCKED_SOURCE
    rationale: A primary tax-delinquency event source currently inaccessible to
               automated recon (HTTP 403); also per-record-only coverage.

## parcel_master — ENRICHMENT_SOURCE
    rationale: Appraisal-district parcel/owner/valuation data; attaches context to
               leads, never originates one. §13.3.

## gis_parcels — ENRICHMENT_SOURCE
    rationale: Parcel geometry / identifiers; map rendering and join support only.
               §13.3.
