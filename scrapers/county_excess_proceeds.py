"""Smith County, TX — District Clerk Excess Proceeds adapter.

PRIMARY EVENT SOURCE (sheriff_sale_surplus). Source-of-record: the
Smith County District Clerk's Registry & Trust Accounts with Balances
report, published as a PDF on the official county Document Center:

    https://www.smith-county.com/DocumentCenter/View/2032

The PDF (GrapeCity ActiveReports, generated ~monthly) lists, per 114th
District Court cause:
    Case Number   Party Name   Increases   Decreases   Net Credit Balance

Stdlib only (urllib + scrapers/_pdf_text.py).

§13.5 / §16.E classification: PRIMARY_EVENT_SOURCE. §17 routing: each
record carries the original-suit DEFENDANT name (the delinquent taxpayer
whose property generated the surplus). The party is emitted with
`name_type=DF` so §17's `sheriff_sale_surplus` rule resolves owner via
its DF fallback (expected TP, fallback DF) — owner is REAL, not a
placeholder. Property attachment is the court cause_nbr (district court
case), not a parcel_id — the report carries no parcel/address. Surplus
leads ship as `parcel_resolution_status=UNRESOLVED` and the renderer
fills in `legal_description` (Smith County District Court Cause No. X —
Excess Proceeds) for skip-trace.

Only rows with `net_credit_balance > 0` are emitted — zero-balance rows
are closed/settled and not actionable.
"""
from __future__ import annotations
import argparse, json, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
from _pdf_text import extract_text  # noqa: E402

SOURCE_ID = "county_excess_proceeds"
PDF_URL = "https://www.smith-county.com/DocumentCenter/View/2032"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FIXTURE_DIR = REPO_ROOT / "scrapers" / "fixtures" / SOURCE_ID
OUT_PATH = REPO_ROOT / "data" / "raw" / "county_excess_proceeds.jsonl"

# Case-number formats observed in the Smith DC Registry: "13-2734-B",
# "22,773-B", "25-051-B", "26,175-C/B" (compound suffix).
_CASE_RE = re.compile(r'(\d{2}[,-]\d{3,4}-[A-Z](?:/[A-Z])?)')
# Money: $X,XXX.XX (with or without commas).
_MONEY_RE = re.compile(r'\$([\d,]+\.\d{2})')


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_pdf_text(text: str) -> list[dict]:
    """Walk the case-number anchors and harvest the (party, amounts)
    between them. Only rows with net_credit_balance > 0 are returned."""
    matches = list(_CASE_RE.finditer(text))
    rows: list[dict] = []
    for i, m in enumerate(matches):
        case = m.group(1).strip()
        # Slice between this match end and the next match start (or EOF)
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = text[m.end():seg_end]
        amts = [_to_float(a) for a in _MONEY_RE.findall(seg)]
        if not amts:
            continue
        # Party name = the text BEFORE the first $ in the segment
        first_dollar = seg.find("$")
        if first_dollar < 0:
            continue
        party = " ".join(seg[:first_dollar].split()).strip().rstrip(",").strip()
        if not party:
            continue
        # net_credit_balance interpretation:
        #   3 amounts -> Increases, Decreases, Net Credit Balance
        #   2 amounts -> Increases == Decreases -> Net = 0 (skip)
        if len(amts) >= 3:
            increases, decreases, net = amts[0], amts[1], amts[2]
        elif len(amts) == 2:
            increases, decreases, net = amts[0], amts[1], 0.0
        else:
            continue
        if not net or net <= 0:
            continue  # zero / closed — not a real surplus lead
        rows.append({
            "case_number": case,
            "party_name": party,
            "increases": increases,
            "decreases": decreases,
            "net_credit_balance": net,
        })
    return rows


def normalize_record(row: dict, fetched_at: str) -> dict:
    """Emit v5.4.0 raw_event with DF-tagged party (§17 fallback resolves)."""
    case = row["case_number"]
    party = row["party_name"]
    return {
        "raw_event_id": f"smith_tx-excess_proceeds-{case}",
        "source_id": SOURCE_ID,
        "source_role": "PRIMARY_EVENT_SOURCE",
        "raw_doc_type": "District Clerk Registry & Trust — Excess Proceeds",
        "canonical_doc_type": "sheriff_sale_surplus",
        "instrument_number": case,
        "recorded_date": None,
        "event_date": None,
        "source_url": PDF_URL + f"#case={case.replace(',', '%2C')}",
        "parties": [{
            "name": party,
            "name_type": "DF",     # original-suit defendant -> §17 fallback for owner
            "raw_role": "district court registry — party of record",
        }],
        "document_body_text": None,
        "property_refs": {
            "parcel_id": None,            # not in registry PDF
            "situs_address": None,
            "legal_description": (f"Smith County District Court Cause No. {case} "
                                  f"— Excess Proceeds (114th Judicial District)"),
            "case_number": case,
        },
        "amounts": [
            {"label": "increases", "value": row["increases"]},
            {"label": "decreases", "value": row["decreases"]},
            {"label": "net_credit_balance", "value": row["net_credit_balance"]},
        ],
        "evidence_ids": [],
        "parser_name": "scrapers/county_excess_proceeds.py",
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
    path = FIXTURE_DIR / fixture_name
    body = path.read_bytes()
    fetched_at = _now_iso()
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            data = data.get("rows", []) if "rows" in data else []
        return [normalize_record(r, fetched_at) for r in data
                if isinstance(r, dict) and r.get("case_number")]
    text = extract_text(body)
    return [normalize_record(r, fetched_at) for r in parse_pdf_text(text)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Smith County, TX — District Clerk Excess Proceeds adapter.")
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
    print(f"  parsed {len(rows)} excess-proceeds rows (net > 0)", flush=True)
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
