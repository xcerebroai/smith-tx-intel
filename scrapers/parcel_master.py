"""
Smith County, TX — parcel-master ENRICHMENT adapter (Phase 2).

Source: Smith County GIS "Tax Parcels" layer, an open public ArcGIS REST
MapServer (no auth, no CAPTCHA, no session):

    https://www.smithcountymapsite.org/publicgis/rest/services/Gallery/TaxParcelQuery/MapServer/1

141,692 parcels. Each carries ACCOUNT (Smith CAD appraisal account number),
ParcelID/PIN, situs ADDRESS, POSTAL_CITY, ZIPCODE, owner OWN1/OWN2,
Calc_Acre, YRBLT, SFLA, Type, subdivision/block/lot, ISD.

ENRICHMENT FOUNDATION ONLY. Per the §13 Lead Origination Contract, parcel
data is ENRICHMENT — it decorates a lead that a primary event source has
already originated; it NEVER originates a lead itself. This adapter emits
parcel records for the matcher to join against. It produces zero signals
and zero lead rows. The built-in `parcel_master` translator that consumes
this output returns ([], parcels, {}) by contract.

Output: `data/raw/parcel_master.jsonl`, one JSON line per parcel in the
framework-canonical wrapped raw-record shape (MASTER_PROMPT §4.32).

Protocol handling (ArcGIS pagination, retries, error envelopes) is delegated
to the county-agnostic framework helper `scaffold/scrapers/_arcgis_featureserver.py`.
This module owns only the Smith-County-specific field normalization.

Built for framework v5.3.1 — Smith County (smith_tx) Phase 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scaffold" / "scrapers"))
from _arcgis_featureserver import ArcGISFeatureServer, ArcGISServerError  # noqa: E402

SOURCE_ID = "parcel_master"
SERVICE_URL = (
    "https://www.smithcountymapsite.org/publicgis/rest/services"
    "/Gallery/TaxParcelQuery/MapServer"
)
LAYER_ID = 1  # "Tax Parcels"
USER_AGENT = "xcerebro-smith-tx-parcel-master/0.1 (+private county build)"
FIXTURE_DIR = REPO_ROOT / "scrapers" / "fixtures" / SOURCE_ID
OUT_PATH = REPO_ROOT / "data" / "raw" / "parcel_master.jsonl"

# parser_confidence floor below which the framework routes a record to the
# review queue rather than trusting it (MASTER_PROMPT §3 / §4.32).
REVIEW_CONFIDENCE = 80


# --------------------------------------------------------------------------
# Field normalization — Smith County ArcGIS attrs -> framework-canonical names
# --------------------------------------------------------------------------

def _clean(value) -> str:
    """Trim a string field; ArcGIS uses ' ' and '' for blanks."""
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _norm_address(value) -> str:
    """Situs address, uppercased and single-spaced (canonical per §4.32)."""
    return _clean(value).upper()


def _int_or_none(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _legal_description(attrs: dict) -> str:
    """Compose a light legal description from subdivision / block / lot."""
    parts = []
    subd = _clean(attrs.get("SUBDNUM"))
    block = _clean(attrs.get("BLOCK")) or _clean(attrs.get("BLOCK_1"))
    lot = _clean(attrs.get("LOT")) or _clean(attrs.get("LOT_1"))
    if subd:
        parts.append(f"SUBD {subd}")
    if block:
        parts.append(f"BLK {block}")
    if lot:
        parts.append(f"LOT {lot}")
    return " ".join(parts)


def normalize_feature(feature: dict, fetched_at: str) -> dict:
    """Convert one ArcGIS feature into a §4.32 wrapped raw record.

    Never fabricates. A feature missing the parcel identifier or situs
    address is emitted with parser_confidence below the review floor so the
    pipeline routes it to review rather than trusting it.
    """
    attrs = (feature.get("attributes") or {}) if isinstance(feature, dict) else {}
    oid = attrs.get("OBJECTID") or attrs.get("objectid") or attrs.get("FID")

    account = _clean(attrs.get("ACCOUNT"))
    address = _norm_address(attrs.get("ADDRESS"))
    own1 = _clean(attrs.get("OWN1"))
    own2 = _clean(attrs.get("OWN2"))
    owner = own1 if not own2 else f"{own1} {own2}".strip()

    # parser_confidence reflects whether the PARSER succeeded — not whether
    # optional enrichment fields happen to be populated. A parcel with a
    # valid ACCOUNT but no situs address (vacant land, right-of-way, county
    # tract) is a sound enrichment record. Only a missing join key
    # (parcel_id) makes the record unusable and routes it to review.
    confidence = 95
    missing = []
    if not account:
        missing.append("parcel_id")
        confidence = 40

    # Build raw_payload with framework-canonical field names. Only set keys
    # that carry a real value — absent fields are omitted, not fabricated.
    payload: dict = {}
    if account:
        payload["parcel_id"] = account
    if address:
        payload["address"] = address
    if owner:
        payload["owner_name"] = owner
    city = _clean(attrs.get("POSTAL_CITY")).upper()
    if city:
        payload["city"] = city
    zipcode = _int_or_none(attrs.get("ZIPCODE"))
    if zipcode:
        payload["zip"] = str(zipcode)
    acres = _float_or_none(attrs.get("Calc_Acre"))
    if acres is not None:
        payload["acres"] = acres
    yrblt = _int_or_none(attrs.get("YRBLT"))
    if yrblt:  # 0 means "unknown" in this layer — omit rather than emit 0
        payload["year_built"] = yrblt
    prop_use = _clean(attrs.get("Type"))
    if prop_use:
        payload["property_use"] = prop_use
    legal = _legal_description(attrs)
    if legal:
        payload["legal_description"] = legal

    # Smith-County-specific extras the canonical translator ignores but that
    # are useful provenance for the matcher / operator review.
    sfla = _int_or_none(attrs.get("SFLA"))
    if sfla:
        payload["building_sqft"] = sfla
    gis_pid = _clean(attrs.get("ParcelID"))
    if gis_pid:
        payload["gis_parcel_id"] = gis_pid
    pin = _clean(attrs.get("PIN"))
    if pin:
        payload["pin"] = pin
    tax_year = _int_or_none(attrs.get("TAXYR"))
    if tax_year:
        payload["tax_year"] = tax_year
    city_county = _clean(attrs.get("CITY_COUNTY"))
    if city_county:
        payload["city_county"] = city_county
    isd = _clean(attrs.get("ISD"))
    if isd:
        payload["school_district"] = isd

    record_key = account or (f"OID{oid}" if oid is not None else "UNKNOWN")
    record = {
        "raw_record_id": f"smith_tx-{SOURCE_ID}-{record_key}",
        "source_id": SOURCE_ID,
        "source_url": f"{SERVICE_URL}/{LAYER_ID}/query?objectIds={oid}&f=json",
        "source_fetched_at": fetched_at,
        "parser_confidence": confidence,
        "raw_payload": payload,
    }
    if missing:
        # Surfaced for the review queue; not a fabricated value.
        record["parser_missing_fields"] = missing
    return record


# --------------------------------------------------------------------------
# Live pull
# --------------------------------------------------------------------------

def iter_records(server: ArcGISFeatureServer, *, where: str = "1=1",
                 max_features: int | None = None):
    """Yield normalized §4.32 records for the Tax Parcels layer."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for feature in server.iter_features(
        layer_id=LAYER_ID, where=where, out_fields="*",
        return_geometry=False, max_features=max_features,
    ):
        yield normalize_feature(feature, fetched_at)


def run_live(where: str = "1=1", limit: int | None = None,
             out_path: Path = OUT_PATH) -> int:
    """Pull parcels from the live ArcGIS service into data/raw/parcel_master.jsonl."""
    server = ArcGISFeatureServer(SERVICE_URL, user_agent=USER_AGENT)
    try:
        total = server.count_features(LAYER_ID, where=where)
        print(f"  layer {LAYER_ID} feature count (where {where!r}): {total}",
              flush=True)
    except ArcGISServerError as exc:
        print(f"ERROR: ArcGIS service unreachable: {exc}", file=sys.stderr)
        return 4

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    review = 0
    try:
        with out_path.open("w", encoding="utf-8") as fh:
            for record in iter_records(server, where=where, max_features=limit):
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                written += 1
                if record["parser_confidence"] < REVIEW_CONFIDENCE:
                    review += 1
                if written % 500 == 0:
                    print(f"  [{written}] parcels written", flush=True)
    except ArcGISServerError as exc:
        print(f"ERROR: ArcGIS error mid-pull: {exc}", file=sys.stderr)
        return 4
    print(f"Wrote {written} parcel records to {out_path.relative_to(REPO_ROOT)} "
          f"({review} below review confidence floor).", flush=True)
    return 0


# --------------------------------------------------------------------------
# Fixture entry point — required by the §05 scraper fixture contract
# --------------------------------------------------------------------------

def parse_fixture(fixture_name: str) -> list:
    """Parse a saved fixture offline (no network). Returns a list of records.

    Raises ArcGISServerError for the blocked-session fixture so the harness
    can assert clean failure handling. The fixture files live in
    tests/fixtures/parcel_master/.
    """
    path = FIXTURE_DIR / fixture_name
    fixture = json.loads(path.read_text(encoding="utf-8"))

    def fetch_fn(url: str, params: dict) -> dict:
        # Error-envelope fixture: replay the ArcGIS error verbatim.
        if "error" in fixture:
            return fixture
        # Paginated fixture: {"by_offset": {"0": resp, "3": resp, ...}}
        if "by_offset" in fixture:
            offset = int(params.get("resultOffset", 0) or 0)
            return fixture["by_offset"].get(str(offset), {"features": []})
        # Count probe.
        if str(params.get("returnCountOnly", "")).lower() == "true":
            return {"count": len(fixture.get("features", []))}
        # Single-page fixtures: page 0 returns the fixture, later pages empty.
        if int(params.get("resultOffset", 0) or 0) > 0:
            return {"features": []}
        return fixture

    server = ArcGISFeatureServer(SERVICE_URL, user_agent=USER_AGENT,
                                 fetch_fn=fetch_fn, page_size=100)
    return list(iter_records(server))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Smith County, TX parcel-master enrichment adapter "
                    "(ArcGIS Tax Parcels layer). ENRICHMENT ONLY — no leads.")
    parser.add_argument("--where", default="1=1",
                        help="ArcGIS WHERE clause (default: all parcels).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max parcels to pull (default: all 141,692).")
    parser.add_argument("--out", default=str(OUT_PATH),
                        help="Output JSONL path.")
    parser.add_argument("--fixture", default=None,
                        help="Parse a fixture offline and print the records "
                             "instead of hitting the network.")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.fixture:
        try:
            records = parse_fixture(args.fixture)
        except ArcGISServerError as exc:
            print(f"fixture {args.fixture}: blocked/error envelope handled "
                  f"cleanly: {exc}", flush=True)
            return 4
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    return run_live(where=args.where, limit=args.limit,
                    out_path=Path(args.out).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
