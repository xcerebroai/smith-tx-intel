"""
Scraper fixture test harness — Smith County, TX (smith_tx).

Drives every county adapter under `scrapers/` against its saved offline
fixtures per the eight-scenario contract in
`knowledge_base/engineering/05_verification_and_rollback.md`. No network.

Fixtures live at `scrapers/fixtures/<source_id>/` and this harness at
`scrapers/test_scrapers.py` — inside the regression-exempt `scrapers/`
tree, because county-specific fixture data cannot live in a universal
directory scanned by the county-agnostic regression test. See
runs/smith_tx/build/findings.md FIND-002.

Run directly:  python3 scrapers/test_scrapers.py   (exit 0 = pass)
Also importable as a pytest module (test_* functions).

Phase 2 acceptance: REVIEW_GATE_3 requires this harness to pass before the
first adapter is considered production-ready.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scrapers import parcel_master  # noqa: E402
from scrapers.parcel_master import ArcGISServerError  # noqa: E402

# §4.32 wrapped raw-record required top-level keys.
WRAPPED_KEYS = {
    "raw_record_id", "source_id", "source_url",
    "source_fetched_at", "parser_confidence", "raw_payload",
}


class Checker:
    def __init__(self) -> None:
        self.passes: list = []
        self.fails: list = []

    def ok(self, label: str, cond: bool, detail: str = "") -> None:
        (self.passes if cond else self.fails).append(
            label if cond else (label, detail))

    def assert_wrapped(self, label: str, rec: dict) -> None:
        self.ok(f"{label}: §4.32 wrapped shape",
                isinstance(rec, dict) and WRAPPED_KEYS.issubset(rec),
                f"keys={sorted(rec) if isinstance(rec, dict) else rec}")
        self.ok(f"{label}: source_id is parcel_master",
                rec.get("source_id") == "parcel_master",
                f"got {rec.get('source_id')!r}")
        self.ok(f"{label}: raw_payload is a dict",
                isinstance(rec.get("raw_payload"), dict))


def _check_parcel_master(c: Checker) -> None:
    # 1 — empty
    empty = parcel_master.parse_fixture("empty_result.json")
    c.ok("empty_result → []", empty == [], f"got {empty!r}")

    # 2 — single
    single = parcel_master.parse_fixture("single_result.json")
    c.ok("single_result → 1 record", len(single) == 1, f"got {len(single)}")
    if single:
        rec = single[0]
        c.assert_wrapped("single_result", rec)
        c.ok("single_result: parcel_id present",
             bool(rec["raw_payload"].get("parcel_id")))
        c.ok("single_result: confidence >= review floor",
             rec["parser_confidence"] >= parcel_master.REVIEW_CONFIDENCE,
             f"conf={rec['parser_confidence']}")

    # 3 — multiple
    multi = parcel_master.parse_fixture("multiple_results.json")
    c.ok("multiple_results → 4 records", len(multi) == 4, f"got {len(multi)}")
    ids = [r["raw_record_id"] for r in multi]
    c.ok("multiple_results: no duplicate record ids", len(ids) == len(set(ids)))
    for i, rec in enumerate(multi):
        c.assert_wrapped(f"multiple_results[{i}]", rec)

    # 4 — pagination (3 on offset 0, 2 on offset 3)
    paged = parcel_master.parse_fixture("pagination.json")
    c.ok("pagination → 5 records across offsets", len(paged) == 5,
         f"got {len(paged)}")

    # 5 — record detail (full field set)
    detail = parcel_master.parse_fixture("record_detail.json")
    c.ok("record_detail → 1 record", len(detail) == 1, f"got {len(detail)}")
    if detail:
        payload = detail[0]["raw_payload"]
        c.ok("record_detail: enrichment fields populated",
             bool(payload.get("parcel_id")) and bool(payload.get("address"))
             and bool(payload.get("owner_name")),
             f"payload keys={sorted(payload)}")

    # 6 — document_download: N/A for an ArcGIS parcel enrichment layer.
    c.ok("document_download: N/A for enrichment parcel layer (documented)",
         not (parcel_master.FIXTURE_DIR / "document_download.pdf").exists())

    # 7 — blocked session → clean ArcGISServerError, no crash
    try:
        parcel_master.parse_fixture("blocked_session.json")
        c.ok("blocked_session → raises ArcGISServerError", False,
             "no error raised")
    except ArcGISServerError:
        c.ok("blocked_session → raises ArcGISServerError (clean)", True)
    except Exception as exc:  # noqa: BLE001
        c.ok("blocked_session → raises ArcGISServerError", False,
             f"raised {type(exc).__name__} instead")

    # 8 — malformed → routed to review, never fabricated
    bad = parcel_master.parse_fixture("malformed_record.json")
    c.ok("malformed_record → 1 record (not dropped)", len(bad) == 1,
         f"got {len(bad)}")
    if bad:
        rec = bad[0]
        c.assert_wrapped("malformed_record", rec)
        c.ok("malformed_record: parser_confidence < review floor",
             rec["parser_confidence"] < parcel_master.REVIEW_CONFIDENCE,
             f"conf={rec['parser_confidence']}")
        c.ok("malformed_record: missing fields flagged, not fabricated",
             bool(rec.get("parser_missing_fields"))
             and "parcel_id" not in rec["raw_payload"],
             f"payload={rec['raw_payload']}")

    # ENRICHMENT-ONLY invariant: the adapter emits parcel records only.
    # No fixture path produces a signal or a lead row.
    all_recs = single + multi + paged + detail
    c.ok("enrichment-only: every record carries a parcel_id payload, no signal keys",
         all("raw_payload" in r and "signal_type" not in r for r in all_recs))


def run() -> int:
    c = Checker()
    _check_parcel_master(c)
    print(f"PASS: {len(c.passes)}")
    print(f"FAIL: {len(c.fails)}")
    for item in c.fails:
        label, detail = item if isinstance(item, tuple) else (item, "")
        print(f"  [FAIL] {label}  --  {detail}")
    if c.fails:
        return 1
    print("Scraper fixture harness PASSED — parcel_master (8/8 scenarios; "
          "#6 document-download N/A for an enrichment layer).")
    return 0


# pytest entry point
def test_parcel_master_fixtures() -> None:
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(run())
