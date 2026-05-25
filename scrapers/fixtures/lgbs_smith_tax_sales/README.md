# lgbs_smith_tax_sales fixtures — Smith County, TX

Saved offline fixtures for `scrapers/lgbs_smith_tax_sales.py` per the
eight-scenario contract in `knowledge_base/engineering/05_verification_and_rollback.md`.
The LGBS source is a Django REST Framework JSON API, so the fixtures are
`.json` verbatim API responses (not `.html`). Fixtures 1–5 are real
responses captured from the live `taxsales.lgbs.com/api/property_sales/`
endpoint on 2026-05-25; fixtures 7–8 are crafted edge cases.

| # | Fixture | Scenario |
|---|---|---|
| 1 | `empty_result.json` | query that returns zero results → adapter returns `[]` |
| 2 | `single_result.json` | one Smith record → one normalized v5.4.0 raw_event |
| 3 | `multiple_results.json` | several Smith records on one page |
| 4 | `pagination.json` | first page of paginated result (the `next` URL drives further fetches in live mode) |
| 5 | `record_detail.json` | full field set for one Smith record |
| 6 | *document_download* | **NOT APPLICABLE** — the LGBS JSON API has no per-record document/image artifact to download. Recorded as N/A rather than faked. |
| 7 | `blocked_session.json` | DRF error envelope (`{"detail":"Authentication credentials were not provided."}`) → adapter returns `[]` |
| 8 | `malformed_record.json` | result row missing `uid`/`account_nbr`/`cause_nbr` → adapter drops it (no fabrication) |

The adapter exposes `parse_fixture(fixture_name)`; per FIND-002 the fixtures
live under `scrapers/fixtures/` (regression-exempt) rather than `tests/`.
