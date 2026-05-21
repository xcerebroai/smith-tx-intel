# parcel_master fixtures — Smith County, TX

Saved offline fixtures for the `scrapers/parcel_master.py` adapter, per the
eight-scenario scraper fixture contract in
`knowledge_base/engineering/05_verification_and_rollback.md`.

The source is an ArcGIS REST MapServer (Smith County GIS "Tax Parcels"
layer), so the fixtures are `.json` ArcGIS responses rather than `.html`.
Fixtures 1–5 are real responses captured from the live service; fixtures
7–8 are crafted edge cases (an error envelope and a malformed record
cannot be obtained by a normal query).

| # | Fixture | Scenario |
|---|---|---|
| 1 | `empty_result.json` | query with zero matches → adapter returns `[]` |
| 2 | `single_result.json` | one parcel → one normalized record |
| 3 | `multiple_results.json` | several parcels on one page |
| 4 | `pagination.json` | multi-offset result set (`by_offset` keyed) |
| 5 | `record_detail.json` | full field set for one parcel |
| 6 | *document_download* | **NOT APPLICABLE** — an ArcGIS parcel enrichment layer has no per-record document/image artifact to download. Recorded here as N/A rather than faked. |
| 7 | `blocked_session.json` | ArcGIS error envelope → adapter raises `ArcGISServerError`, CLI exits 4 |
| 8 | `malformed_record.json` | parcel missing `ACCOUNT` / garbage values → routed to review (`parser_confidence < 80`), never fabricated |

The adapter exposes `parse_fixture(fixture_name)`; `tests/test_scrapers.py`
drives it against each fixture offline (no network).
