# Phase 0.A — Source Discovery — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

Candidate official sources discovered via web search (§01.6 query set). Paid-data
aggregators (texasfile, netronline, smithrecords.us, taxnetusa, regrid, etc.) were
seen in results and excluded as non-official reseller layers.

## clerk_recordings
    name:                 Smith County Clerk — Official Public Records
    official_url:         https://smith.tx.publicsearch.us/
    page_title:           Official Record Search — Smith County, Texas County Clerk
    gov_or_aggregator:    government vendor portal (GovOS Cloud Search)
    records_covered:      real property — deeds, deeds of trust, liens, lis pendens,
                          substitute-trustee-sale notices, judgments, plats, probate instruments
    discovered_via_query: "Smith County Texas county clerk official public records search"

## district_court
    name:                 Smith County District Clerk — Court Record Inquiry
    official_url:         https://portal.smith-county.com/Public/
    page_title:           Smith County Public Access (Tyler Odyssey Portal)
    gov_or_aggregator:    government portal (county subdomain)
    records_covered:      district-court civil, family/divorce, felony, delinquent-tax suits
    discovered_via_query: "Smith County Texas district clerk court records search civil"

## sheriff_tax_auctions
    name:                 Smith County Sheriff / Tax Foreclosure Auctions
    official_url:         https://smith.texas.sheriffsaleauctions.com/
    page_title:           Smith County, TX online auctions (RealAuction)
    gov_or_aggregator:    government vendor portal (RealAuction)
    records_covered:      tax-foreclosure sales and sheriff/execution sales (monthly, first Tuesday)
    discovered_via_query: "Smith County Texas tax office delinquent tax sale" / "sheriff sale"

## tax_collector
    name:                 Smith County Tax Office — Property Tax Search
    official_url:         https://publictax.smith-county.com/search
    page_title:           Smith County property tax search
    gov_or_aggregator:    government portal (county subdomain)
    records_covered:      property tax accounts, balances, delinquency status
    discovered_via_query: "Smith County Texas tax assessor collector delinquent property tax"

## parcel_master
    name:                 Smith County Appraisal District (Smith CAD)
    official_url:         https://www.smithcad.org/   (property search: https://esearch.smithcad.org/)
    page_title:           Smith County Appraisal District
    gov_or_aggregator:    government (appraisal district .org)
    records_covered:      parcel master — owner, situs/mailing address, values, year built, acreage
    discovered_via_query: "Texas appraisal district" (state-dependent enrichment search)

## gis_parcels
    name:                 Smith County Map Site (GIS parcels)
    official_url:         https://www.smithcountymapsite.org/   (also https://smithcad.org/WAB/)
    page_title:           Smith County Map Site
    gov_or_aggregator:    government (county GIS / Smith CAD ArcGIS)
    records_covered:      parcel geometry, identifiers, ownership polygons
    discovered_via_query: "Smith CAD downloads appraisal roll data export GIS"
