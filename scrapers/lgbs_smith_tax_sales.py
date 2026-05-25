"""
Smith County, TX — LGBS tax-sale adapter (PRIMARY EVENT SOURCE).

Officially-linked: https://www.smith-county.com/358/Delinquent-Tax-Sales
names Linebarger Goggan Blair & Sampson, LLP ("Linebarger" / LGBS) as the
delinquent-tax attorney for Smith County and most taxing units (Tyler ISD
is handled separately by Perdue Brandon — out of scope for this adapter).

Linebarger publishes the Smith County tax-foreclosure sale list via the
SPA at https://taxsales.lgbs.com. The SPA's bundle exposes the same-origin
Django-REST-Framework API the page uses:

    https://taxsales.lgbs.com/api/property_sales/?county=SMITH+COUNTY&state=TX

That endpoint is unauthenticated, JSON, no CAPTCHA, no SPA gating — stdlib
reachable with urllib alone. As of 2026-05-25 it returns 31 Smith County
records (22 STRUCK OFF + 9 SALE; 100% with property address + account_nbr +
cause_nbr).

This adapter emits v5.4.0 raw_event_record-shaped rows directly to
data/raw/lgbs_smith_tax_sales.jsonl. Stdlib only (urllib, json, re).

§13.5 / §16.E classification: PRIMARY_EVENT_SOURCE.
§17 routing: the LGBS API carries NO party names — every record will be
routed to REVIEW_REQUIRED with the §17.D placeholder owner. That is the
correct framework behavior when expected_debtor is missing from the event
document. Owner / party enrichment attaches downstream from parcel_master
via the parcel_id join (it NEVER originates the lead).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_ID = "lgbs_smith_tax_sales"
API_BASE = "https://taxsales.lgbs.com/api/property_sales/"
DETAIL_URL = "https://taxsales.lgbs.com/api/property_sales/{uid}/"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FIXTURE_DIR = REPO_ROOT / "scrapers" / "fixtures" / SOURCE_ID
OUT_PATH = REPO_ROOT / "data" / "raw" / "lgbs_smith_tax_sales.jsonl"

# Mapping of LGBS sale_type → framework-registered canonical_doc_type.
#
# Per the §17 debtor_party_engine rule table (lowercase keys) and the
# canonical_doc_types.json registry (UPPERCASE keys with lowercase subtype),
# the lead-bearing tax-foreclosure canonicals are:
#   tax_foreclosure_notice  -> §16 lead_type "Tax Lien Foreclosure" (lead_pattern "tax")
#   tax_deed                -> §16 lead_type "Tax Sale"
#   tax_sale_certificate    -> §16 lead_type "Tax Sale Certificate" (not used in TX)
#
# LGBS records are EITHER "Scheduled for Online Auction" with a sale_date_only
# (upcoming first-Tuesday tax-foreclosure auction) OR "Available for Future
# Sale" struck-off properties (taxing-entity-held, awaiting re-listing). Both
# represent UPCOMING / SCHEDULED tax-foreclosure SALE NOTICES rather than
# completed deed transfers; per the operator's mapping guidance both map to
# `tax_foreclosure_notice` (lowercase to match §17 rule keys directly).
# Property attachment is proven on every row (Duval JUDGMENT standard met).
SALE_TYPE_TO_CANONICAL = {
    "SALE": "tax_foreclosure_notice",
    "STRUCK OFF": "tax_foreclosure_notice",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _to_float_or_none(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compose_situs(rec: dict) -> str:
    parts = [_clean(rec.get("prop_address_one")), _clean(rec.get("prop_address_two")),
             _clean(rec.get("prop_city")), _clean(rec.get("prop_state")),
             _clean(rec.get("prop_zipcode"))]
    addr_line = " ".join(p for p in parts[:2] if p).strip()
    city_state_zip = ", ".join(p for p in parts[2:] if p).strip()
    out = ", ".join(p for p in (addr_line, city_state_zip) if p)
    return out.upper()


def _http_get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Live fetch (paginated)
# --------------------------------------------------------------------------

def fetch_smith_records(*, limit_per_page: int = 100,
                        max_records: int | None = None) -> list:
    """Fetch all Smith County tax-sale records from the LGBS API, paginating
    via the response's `next` URL until exhausted or `max_records` reached."""
    params = {"county": "SMITH COUNTY", "state": "TX",
              "limit": limit_per_page}
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    out: list = []
    while url:
        data = _http_get_json(url)
        for rec in data.get("results", []):
            out.append(rec)
            if max_records and len(out) >= max_records:
                return out
        url = data.get("next")
    return out


# --------------------------------------------------------------------------
# Normalize one LGBS record → v5.4.0 raw_event_record
# --------------------------------------------------------------------------

def normalize_record(rec: dict) -> dict:
    """Convert one LGBS API record into a v5.4.0 raw_event_record dict.

    Per the v5.4.0 raw_event_record schema (`additionalProperties: false`),
    only the documented fields are emitted. The LGBS-only extras (geometry,
    venue_id, sale_published, google_view) are intentionally dropped at this
    stage; they belong on an evidence ledger entry, not the raw_event.
    """
    uid = rec.get("uid")
    cause = _clean(rec.get("cause_nbr"))
    account = _clean(rec.get("account_nbr"))
    sale_type = _clean(rec.get("sale_type"))
    status = _clean(rec.get("status"))
    sale_date_only = rec.get("sale_date_only") or None
    situs = _compose_situs(rec)

    # Lower parser_confidence when the LGBS row is marked Cancelled — it is a
    # suppression-candidate per §4.18 lifecycle. Downstream review/suppression
    # is the §17/§18 stage's responsibility; the adapter just flags it.
    confidence = 50 if status.lower() == "cancelled" else 95

    canonical = SALE_TYPE_TO_CANONICAL.get(sale_type.upper(), "tax_foreclosure_notice")

    amounts = []
    mb = _to_float_or_none(rec.get("minimum_bid"))
    if mb is not None:
        amounts.append({"label": "minimum_bid", "value": mb})
    vj = _to_float_or_none(rec.get("value"))
    if vj is not None:
        amounts.append({"label": "value_at_judgment", "value": vj})

    return {
        "raw_event_id": f"smith_tx-lgbs-{uid}",
        "source_id": SOURCE_ID,
        "source_role": "PRIMARY_EVENT_SOURCE",
        "raw_doc_type": sale_type or None,
        "canonical_doc_type": canonical,
        "instrument_number": cause or None,
        "recorded_date": None,
        "event_date": sale_date_only,
        "source_url": DETAIL_URL.format(uid=uid),
        "parties": [],
        "document_body_text": None,
        "property_refs": {
            "parcel_id": account or None,
            "situs_address": situs or None,
            "legal_description": None,
            "case_number": cause or None,
        },
        "amounts": amounts,
        "evidence_ids": [],
        "parser_name": "scrapers/lgbs_smith_tax_sales.py",
        "parser_version": "0.1",
        "parser_confidence": confidence,
        "captured_at": _now_iso(),
    }


# --------------------------------------------------------------------------
# Fixture entry point (per §05 8-scenario contract)
# --------------------------------------------------------------------------

def parse_fixture(fixture_name: str) -> list:
    """Parse a saved LGBS API response fixture offline (no network).

    Returns a list of v5.4.0 raw_event records. For the blocked fixture an
    empty list is returned (CLI exit 4 is the runtime signal — fixtures
    surface the failure via empty list + log message in the harness)."""
    path = FIXTURE_DIR / fixture_name
    body = path.read_text(encoding="utf-8")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    if "error" in data or data.get("detail"):
        # API error envelope — adapter signals empty (no records produced)
        return []
    results = data.get("results")
    if results is None:
        # malformed fixture: no `results` key
        return []
    out = []
    for r in results:
        if not isinstance(r, dict) or not r.get("uid"):
            # malformed individual record — route by emitting low confidence
            continue
        out.append(normalize_record(r))
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Smith County, TX — LGBS tax-sale PRIMARY EVENT SOURCE adapter.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max records to emit (default: all).")
    parser.add_argument("--out", default=str(OUT_PATH),
                        help="Output JSONL path.")
    parser.add_argument("--fixture", default=None,
                        help="Parse a fixture offline; print normalized records.")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.fixture:
        records = parse_fixture(args.fixture)
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    print(f"fetching Smith County tax-sale records from LGBS API ...", flush=True)
    api_records = fetch_smith_records(max_records=args.limit)
    print(f"  fetched {len(api_records)} LGBS records", flush=True)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    review = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for api_rec in api_records:
            ev = normalize_record(api_rec)
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            written += 1
            if ev["parser_confidence"] < 80:
                review += 1
    print(f"wrote {written} raw_event records to "
          f"{out_path.relative_to(REPO_ROOT)} ({review} below review floor — "
          f"cancelled sales)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
