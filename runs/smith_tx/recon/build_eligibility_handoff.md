# Build Eligibility — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

## Counts
    VERIFIED_OFFICIAL sources:   6
    by role:   PRIMARY_EVENT_SOURCE 2 (clerk_recordings, district_court)
               BLOCKED_SOURCE 2 (sheriff_tax_auctions, tax_collector)
               ENRICHMENT_SOURCE 2 (parcel_master, gis_parcels)
    by access: OPEN_PUBLIC 2 · SEARCH_ONLY_PUBLIC 2 · BLOCKED 2

## Accessible primary sources
    clerk_recordings — SEARCH_ONLY_PUBLIC, no login, no CAPTCHA. This is the moat:
        it originates Foreclosure / Notice of Substitute Trustee Sale, Lis Pendens,
        Abstract of Judgment, Mechanic/Construction Lien, Federal/State Tax Lien,
        and probate/heirship/estate-deed lead types.
    district_court — SEARCH_ONLY_PUBLIC; originates Civil Judgment, Divorce, and
        supports delinquent-tax-suit leads.

## Accessible primary document types
    Notice of Substitute Trustee's Sale, Notice of Trustee's Sale, Lis Pendens,
    Abstract of Judgment, Federal Tax Lien, State Tax Lien, Mechanic's &
    Materialman's Lien, Affidavit of Heirship, Executor's / Administrator's Deed;
    delinquent-tax suits and civil judgments via the district court.

## Blockers
    technical: 2 — sheriff_tax_auctions (RealAuction, HTTP 403) and tax_collector
               (county tax portal, HTTP 403). Both are auto-resolvable in Build
               Mode with a real browser (use_playwright / use_stealth_browser).
    permission: 1 — Bankruptcy via PACER (paid; out of county scope).
    not-found: Demolition, Condemnation (municipal — out of county scope).
    operator-review: Eviction (JP-court portal unconfirmed), Surplus (excess-proceeds
               list unconfirmed).

## Verdict — READY_TO_BUILD
    At least one verified primary lead source (clerk_recordings) is fully accessible
    without operator escalation, with multiple accessible primary document types, and
    enrichment (Smith CAD parcel master + GIS) is available. The two blocked primary
    sources are P1 secondary distress feeds with a clear technical next_access_strategy;
    they do not gate the build. No Do-Not-Proceed condition (§4.11) fired.

## Recommended operator next actions
    Approve Build Mode. Build the County Clerk recordings adapter first (the moat),
    then the District Clerk Odyssey adapter and Smith CAD enrichment. Plan a
    browser-based adapter for the RealAuction tax/sheriff auctions and the county tax
    portal. Decide whether Eviction (JP courts), Surplus (excess proceeds), and
    Bankruptcy (PACER) are in scope.
