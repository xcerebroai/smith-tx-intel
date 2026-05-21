# Source of Record Matrix — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

county_build_status: READY_TO_BUILD

27 canonical lead types swept. Per-type detail (machine-readable copy in
`source_of_record_matrix.json`):

## Foreclosure
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               TX non-judicial. Substitute-trustee sale notices are recorded with the County Clerk; searchable on publicsearch.us.

## Trustee Sale
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Recorded notice of trustee/substitute-trustee sale in County Clerk official records.

## Notice of Trustee Sale
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Recorded instrument type in County Clerk official records.

## Notice of Substitute Trustee Sale
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Dominant TX foreclosure-notice form; filed 21 days before the first-Tuesday sale; County Clerk records.

## Sheriff Sale
    state_applicability: APPLICABLE
    status:              SOURCE_FOUND_BLOCKED
    selected_source:     sheriff_tax_auctions
    authorities:         Sheriff's Office
    notes:               RealAuction online platform; automated fetch returns 403 (anti-bot). Technical blocker; build-mode browser resolves.

## Tax Lien Foreclosure
    state_applicability: APPLICABLE
    status:              SOURCE_FOUND_BLOCKED
    selected_source:     sheriff_tax_auctions
    authorities:         Tax Office, Sheriff's Office
    notes:               Delinquent-tax foreclosure suits sold via RealAuction since 2023; same anti-bot blocker.

## Tax Sale
    state_applicability: APPLICABLE
    status:              SOURCE_FOUND_BLOCKED
    selected_source:     sheriff_tax_auctions
    authorities:         Tax Office, Sheriff's Office
    notes:               Monthly first-Tuesday tax sale, online via RealAuction; anti-bot blocker.

## Tax Sale Certificate
    state_applicability: NOT_APPLICABLE_IN_STATE
    status:              NOT_APPLICABLE_IN_STATE
    selected_source:     (none)
    authorities:         n/a
    notes:               Texas is a redeemable tax-DEED state; it does not issue tax-lien/sale certificates.

## Tax Delinquency
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND_LIMITED_COVERAGE
    selected_source:     tax_collector
    authorities:         Tax Office
    notes:               publictax portal is per-account lookup only (no public bulk delinquent roll) and returns 403 to automated fetch.

## Lis Pendens
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Recorded lis pendens in County Clerk official records.

## Civil Judgment
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     district_court
    authorities:         District Clerk, County Clerk
    notes:               District-court civil judgments via Odyssey; abstracts also recorded with the County Clerk.

## Abstract of Judgment
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Abstract of judgment is a recorded instrument in County Clerk records.

## Mechanic Lien
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Mechanic's & materialman's liens recorded with the County Clerk.

## Construction Lien
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Same TX instrument family as the mechanic's lien; County Clerk records.

## Federal Tax Lien
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               IRS notices of federal tax lien recorded with the County Clerk.

## State Tax Lien
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               State tax liens recorded with the County Clerk.

## Probate
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND_LIMITED_COVERAGE
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               County Clerk is record-keeper for probate (constitutional county court). Recorded probate instruments are on publicsearch.us; live probate-docket coverage to be confirmed against the County Clerk probate index in Build Mode.

## Affidavit of Heirship
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Recorded affidavit of heirship in County Clerk official records.

## Executor Deed
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Executor's deed sub-type in County Clerk deed records.

## Administrator Deed
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     clerk_recordings
    authorities:         County Clerk
    notes:               Administrator's deed sub-type in County Clerk deed records.

## Code Lien
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND_LIMITED_COVERAGE
    selected_source:     clerk_recordings
    authorities:         County Clerk, Municipalities
    notes:               Municipal code liens are caught when abstracted/recorded with the County Clerk; live city code-enforcement rolls are per-municipality and out of scope for a county-wide build.

## Demolition
    state_applicability: APPLICABLE
    status:              SOURCE_NOT_FOUND
    selected_source:     (none)
    authorities:         Municipalities
    notes:               Demolition orders are municipal (City of Tyler etc.); no county-level source. Per-municipality, out of scope.

## Condemnation
    state_applicability: APPLICABLE
    status:              SOURCE_NOT_FOUND
    selected_source:     (none)
    authorities:         Municipalities
    notes:               Condemnation / unsafe-structure orders are municipal; no county-level source.

## Eviction
    state_applicability: APPLICABLE
    status:              NEEDS_OPERATOR_REVIEW
    selected_source:     (none)
    authorities:         Justice of the Peace Courts
    notes:               TX evictions (forcible entry & detainer) are heard in JP courts; a Smith County JP public portal was not confirmed during recon. Operator review needed before classifying buildable.

## Divorce
    state_applicability: APPLICABLE
    status:              LIVE_SOURCE_FOUND
    selected_source:     district_court
    authorities:         District Clerk
    notes:               Divorce / family cases via the District Clerk Odyssey portal; some family detail may be access-restricted.

## Bankruptcy
    state_applicability: APPLICABLE
    status:              SOURCE_FOUND_PAID
    selected_source:     (none)
    authorities:         U.S. Bankruptcy Court (E.D. Tex., Tyler Division)
    notes:               Federal jurisdiction; PACER is paywalled. Not a county source. Defer unless the operator funds PACER.

## Surplus
    state_applicability: APPLICABLE
    status:              NEEDS_OPERATOR_REVIEW
    selected_source:     (none)
    authorities:         District Clerk / County Treasurer
    notes:               Excess-proceeds (surplus funds) from foreclosure / tax sales are held by the county; a published Smith County excess-proceeds list was not confirmed during recon. Operator review needed.
