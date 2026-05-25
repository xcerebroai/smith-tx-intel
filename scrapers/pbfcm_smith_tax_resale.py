"""Smith County, TX — PBFCM Tyler-ISD struck-off tax-resale adapter.

PRIMARY EVENT SOURCE. Officially-linked from
https://www.smith-county.com/358/Delinquent-Tax-Sales — the county tax page
names Perdue, Brandon, Fielder, Collins & Mott ("Perdue Brandon" / PBFCM)
as the delinquent-tax attorney for Tyler ISD (Linebarger handles general
+ other ISDs, see scrapers/lgbs_smith_tax_sales.py).

Source: a PDF list of Tyler-ISD struck-off properties published at
    https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf
Each row: Account No · Legal Description / Address · Cause No ·
Original Minimum Bid · Sale Date · Market Value (at time of judgment).

Stdlib only (urllib + scrapers/_pdf_text.py).

§13.5 / §16.E: PRIMARY_EVENT_SOURCE. §17 routing: the PDF carries no party
names — REVIEW_REQUIRED / owner_not_on_document is the correct routing.
Property attachment is proven for every emitted row (Account No → Smith CAD
parcel_id, Duval JUDGMENT standard met).
"""
from __future__ import annotations
import argparse, json, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
from _pdf_text import extract_text  # noqa: E402

SOURCE_ID = "pbfcm_smith_tax_resale"
PDF_URL = "https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FIXTURE_DIR = REPO_ROOT / "scrapers" / "fixtures" / SOURCE_ID
OUT_PATH = REPO_ROOT / "data" / "raw" / "pbfcm_smith_tax_resale.jsonl"

# Row pattern: <18-digit account>  <legal/address (lazy)>  <cause CAUSE-LETTER>
#               <$bid>  <MM-DD-YYYY date>  <market_value>
# Account numbers in the PDF can be 18-digit Smith CAD ACCOUNT format.
_ROW_RE = re.compile(
    r'(\d{18})\s+'                                              # ACCOUNT
    r'(.+?)\s+'                                                 # legal/address (lazy)
    r'(\d{1,2}[,\s]?\d{0,3}-[A-Z])\s+'                          # cause "24,998-C" / "26915-B"
    r'\$?\s*([\d,]+\.\d{2})\s+'                                 # min bid
    r'(\d{2}-\d{2}-\d{4})\s+'                                   # sale date
    r'\$?\s*([\d,]+\.\d{2})'                                    # market value
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_money(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None


def _to_iso_date(mdy: str) -> str | None:
    try:
        return datetime.strptime(mdy, "%m-%d-%Y").date().isoformat()
    except ValueError:
        return None


def parse_pdf_text(text: str) -> list[dict]:
    """Pull row tuples out of the extracted PDF text. Returns list of dicts."""
    rows: list[dict] = []
    for m in _ROW_RE.finditer(text):
        account, legal, cause, bid, sale_date, mkt = m.groups()
        rows.append({
            "account_nbr": account.strip(),
            "legal_description": " ".join(legal.split()).strip(),
            "cause_nbr": cause.strip(),
            "minimum_bid": _clean_money(bid),
            "sale_date": _to_iso_date(sale_date),
            "market_value": _clean_money(mkt),
        })
    return rows


def normalize_record(row: dict, fetched_at: str) -> dict:
    """v5.4.0 raw_event_record shape — sale_type STRUCK OFF -> tax_foreclosure_notice."""
    account = row["account_nbr"]
    cause = row["cause_nbr"]
    legal = row.get("legal_description") or ""
    amounts = []
    if row.get("minimum_bid") is not None:
        amounts.append({"label": "minimum_bid", "value": row["minimum_bid"]})
    if row.get("market_value") is not None:
        amounts.append({"label": "value_at_judgment", "value": row["market_value"]})
    return {
        "raw_event_id": f"smith_tx-pbfcm_resale-{account}-{cause}",
        "source_id": SOURCE_ID,
        "source_role": "PRIMARY_EVENT_SOURCE",
        "raw_doc_type": "STRUCK OFF (Tyler ISD)",
        "canonical_doc_type": "tax_foreclosure_notice",
        "instrument_number": cause,
        "recorded_date": None,
        "event_date": row.get("sale_date"),
        "source_url": PDF_URL + f"#account={account}",
        "parties": [],
        "document_body_text": None,
        "property_refs": {
            "parcel_id": account,
            "situs_address": legal.upper() if legal else None,
            "legal_description": legal or None,
            "case_number": cause,
        },
        "amounts": amounts,
        "evidence_ids": [],
        "parser_name": "scrapers/pbfcm_smith_tax_resale.py",
        "parser_version": "0.1",
        "parser_confidence": 90,
        "captured_at": fetched_at,
    }


def fetch_pdf_bytes() -> bytes:
    req = urllib.request.Request(PDF_URL, headers={
        "User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_fixture(fixture_name: str) -> list:
    """Parse a saved fixture PDF or JSON offline. PDF fixture: raw bytes
    saved as `*.pdf`; JSON fixture: list of pre-parsed row dicts."""
    path = FIXTURE_DIR / fixture_name
    body = path.read_bytes()
    fetched_at = _now_iso()
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            if "rows" in data:
                data = data["rows"]
            elif "error" in data:
                return []
            else:
                return []
        return [normalize_record(r, fetched_at) for r in data if isinstance(r, dict)
                and r.get("account_nbr")]
    text = extract_text(body)
    return [normalize_record(r, fetched_at) for r in parse_pdf_text(text)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Smith County, TX — PBFCM Tyler-ISD struck-off resale PDF adapter.")
    p.add_argument("--out", default=str(OUT_PATH))
    p.add_argument("--fixture", default=None)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    if args.fixture:
        recs = parse_fixture(args.fixture)
        print(json.dumps(recs, indent=2, ensure_ascii=False))
        return 0

    print(f"fetching {PDF_URL} ...", flush=True)
    body = fetch_pdf_bytes()
    print(f"  {len(body):,} bytes", flush=True)
    text = extract_text(body)
    rows = parse_pdf_text(text)
    print(f"  parsed {len(rows)} struck-off rows", flush=True)
    fetched_at = _now_iso()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(normalize_record(r, fetched_at), ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} raw_event records to {out.relative_to(REPO_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
