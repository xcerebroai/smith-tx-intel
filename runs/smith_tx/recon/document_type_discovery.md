# Phase 0.F — Document Type Discovery — Smith County, Texas (smith_tx) — recon generated 2026-05-19T18:06:03Z — framework v5.3.0

Metadata-only (§01.12). Performed for accessible PRIMARY sources.

## clerk_recordings
    document_type_taxonomy_field_name: "doc type" (search filter on publicsearch.us)
    total_types_observed:              taxonomy not enumerated without an interactive
                                       session; canonical TX recorder doc types expected
    types_mapped_to_canonical_primary: Notice of Substitute Trustee's Sale, Notice of
                                       Trustee's Sale, Lis Pendens, Abstract of Judgment,
                                       Federal Tax Lien, State Tax Lien, Mechanic's &
                                       Materialman's Lien, Affidavit of Heirship,
                                       Executor's Deed, Administrator's Deed, Sheriff's Deed
    types_mapped_to_canonical_enrichment: Warranty Deed, Special Warranty Deed,
                                       Deed of Trust, Release / Satisfaction (negative signal)
    types_unknown:                     county-specific abbreviations — confirm against the
                                       live doc-type dropdown in Build Mode
    recommended_primary_doc_types_for_build: substitute-trustee-sale notices, lis pendens,
                                       abstracts of judgment, tax liens, mechanic's liens,
                                       heirship/estate instruments

## district_court
    document_type_taxonomy_field_name: Odyssey "case type" / "case category"
    total_types_observed:              not enumerated without an interactive session
    types_mapped_to_canonical_primary: delinquent-tax suit, civil judgment, divorce
    types_mapped_to_canonical_enrichment: (none — court portal is event-based)
    types_unknown:                     full Odyssey case-type list — confirm in Build Mode
    recommended_primary_doc_types_for_build: delinquent-tax suits, civil judgments, divorce

Sample-document inspection (§01.22): the County Clerk portal's certified document
IMAGES are purchase-gated, so 3 sample document images were not pulled during
metadata-only recon. The free search-result metadata (grantor/grantee, doc type,
doc #, recording date, legal description) independently carries the fields needed
to originate a lead, so this does not block the build.
