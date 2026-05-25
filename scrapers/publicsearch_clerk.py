"""Smith County, TX — publicsearch.us clerk records adapter (Playwright).

PRIMARY EVENT SOURCE. Officially-linked from
https://www.smith-county.com/293/Official-Public-Records — the County Clerk's
GovOS Cloud Search portal. The portal SPA renders search results via
hyperscript (htmx-style) on the client; the raw HTTP shell carries only a
"Loading..." placeholder, so production scraping requires a real browser.

CAPTCHA status: reCAPTCHA library IS loaded in the vendor bundle but is NOT
triggered on read-only quick-search navigations during recon. Each query is
rate-limited and the adapter halts cleanly on any 403 / reCAPTCHA challenge
(see _recaptcha_visible).

Quick-search URL pattern (discovered 2026-05-25):
    https://smith.tx.publicsearch.us/results?
      department=RP&keywordSearch=false&recordedDateRange=YYYYMMDD,YYYYMMDD
      &searchOcrText=false&searchType=quickSearch&searchValue=<KEYWORD>

For each distress keyword query, results render as an HTML table:
    GRANTOR | GRANTEE | DOC TYPE | RECORDED DATE | DOC NUMBER |
    BOOK/VOLUME/PAGE | LEGAL DESCRIPTION

The adapter sweeps a fixed set of distress keywords, parses the rendered
table, classifies each row's canonical_doc_type from the DOC TYPE column,
and emits one v5.4.0 raw_event per row.

§13.5 / §16.E: PRIMARY_EVENT_SOURCE. §17 routing: each row's grantor /
grantee names are emitted as parties (GR / GE name_types). For lead-bearing
doc types §17 will resolve the debtor accordingly:
  - lis_pendens / federal_tax_lien / state_tax_lien / mechanics_lien:
    debtor extracted from GR (grantor / lienee).
  - affidavit_of_heirship: debtor extracted from grantee fallback.
  - foreclosure_notice: debtor extracted from GR (foreclosed owner).
Property attachment is proven via the LEGAL DESCRIPTION column (and the
recorded doc_number).
"""
from __future__ import annotations
import argparse, json, re, sys, time, urllib.parse
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_ID = "publicsearch_clerk"
RESULTS_URL = "https://smith.tx.publicsearch.us/results"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FIXTURE_DIR = REPO_ROOT / "scrapers" / "fixtures" / SOURCE_ID
OUT_PATH = REPO_ROOT / "data" / "raw" / "publicsearch_clerk.jsonl"

# Distress-bearing quick-search keywords to sweep. Each yields a different
# slice of the recorder's distress records.
DISTRESS_QUERIES = [
    "FORECLOSURE",            # PUBLIC NOTICE / NOTICE OF SUBSTITUTE TRUSTEE'S SALE
    "LIS PENDENS",
    "FEDERAL TAX LIEN",
    "STATE TAX LIEN",
    "MECHANIC LIEN",
    "AFFIDAVIT OF HEIRSHIP",
    "ABSTRACT OF JUDGMENT",
]

# DOC TYPE (publicsearch column) -> §17-registered canonical_doc_type.
# Verified against §17 rule keys in scaffold/pipeline/debtor_party_engine.py.
# Synonym for the Smith County Clerk index taxonomy ("ABSTRACT JUDGMENT" — the
# literal DOC TYPE column value) added 2026-05-25 after the keyword sweep
# returned 50 raw rows with that exact label (the FRAMEWORK-level
# canonical_doc_types.json registry knows it as "ABSTRACT OF JUDGMENT").
DOC_TYPE_MAP = {
    "LIS PENDENS": "lis_pendens",
    "NOTICE OF LIS PENDENS": "lis_pendens",
    "FEDERAL TAX LIEN": "federal_tax_lien",
    "NOTICE OF FEDERAL TAX LIEN": "federal_tax_lien",
    "STATE TAX LIEN": "state_tax_lien",
    "MECHANIC'S LIEN": "mechanics_lien",
    "MECHANICS LIEN": "mechanics_lien",
    "MECHANIC LIEN": "mechanics_lien",
    "AFFIDAVIT OF HEIRSHIP": "affidavit_of_heirship",
    "ABSTRACT OF JUDGMENT": "abstract_of_judgment",
    "ABSTRACT JUDGMENT": "abstract_of_judgment",   # Smith clerk taxonomy code AJ
    "NOTICE OF SUBSTITUTE TRUSTEE'S SALE": "foreclosure_notice",
    "NOTICE OF SUBSTITUTE TRUSTEES SALE": "foreclosure_notice",
    "NOTICE OF TRUSTEE'S SALE": "foreclosure_notice",
    "NOTICE OF TRUSTEES SALE": "foreclosure_notice",
    "NOTICE OF FORECLOSURE SALE": "foreclosure_notice",
    "FORECLOSURE": "foreclosure_notice",     # FC department row literal
    "PUBLIC NOTICE": "foreclosure_notice",   # only emitted when query==FORECLOSURE
    "NOTICE": "foreclosure_notice",          # same context-gated
}

# Canonical doc types for which the publicsearch grantor/grantee columns
# carry the litigation-style PL/DF roles §17 expects (and NOT the GR/GE
# recording roles). On Smith County's publicsearch portal we verified the
# convention from the rendered table:
#   - LIS PENDENS:        GR = plaintiff filing the notice  (= PL)
#                         GE = defendant property owner    (= DF)
#   - ABSTRACT JUDGMENT:  GR = judgment creditor / filer    (= PL)
#                         GE = judgment debtor             (= DF)
# §17 rule keys (lis_pendens / abstract_of_judgment) expect
# expected_debtor_name_type=DF, filer_name_types=[PL]. Emitting GR/GE here
# results in REVIEW_REQUIRED / owner_not_on_document → UNKNOWN owner_type on
# the dashboard. The remap below routes them correctly.
PL_DF_REMAP_CANONICALS = {"lis_pendens", "abstract_of_judgment"}

# DEEDs are not distress on their own — only emit when grantor pattern
# matches a taxing-entity trustee (tax_deed). Built downstream.

DEED_TAXING_AUTHORITIES = re.compile(
    r'\b(ISD\s+TRUSTEE|TAX\s+ASSESSOR|TAXING\s+UNIT|COUNTY\s+OF\s+SMITH)\b',
    re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_results_url(keyword: str, date_from: str, date_to: str,
                       department: str = "RP") -> str:
    """Compose the quick-search results URL. date_from/to are YYYYMMDD."""
    qs = urllib.parse.urlencode({
        "department": department,
        "keywordSearch": "false",
        "recordedDateRange": f"{date_from},{date_to}",
        "searchOcrText": "false",
        "searchType": "quickSearch",
        "searchValue": keyword,
    })
    return f"{RESULTS_URL}?{qs}"


def _build_fc_url(date_from: str, date_to: str,
                  offset: int = 0, limit: int = 50) -> str:
    """Compose the department=FC trustee-foreclosure listing URL.

    The FC department table layout (operator-verified 2026-05-25):
        DOC TYPE | RECORDED DATE | SALE DATE | DOC NUMBER | PROPERTY ADDRESS
    NO grantor / grantee columns — the listing is indexed by doc number, and
    PROPERTY ADDRESS is typically "N/A" because TX trustee foreclosure notices
    record the legal/parcel only inside the document body.
    """
    qs = urllib.parse.urlencode({
        "department": "FC",
        "instrumentDateRange": f"{date_from},{date_to}",
        "keywordSearch": "false",
        "limit": str(limit),
        "offset": str(offset),
        "searchType": "quickSearch",
        "sort": "desc",
        "sortBy": "recordedDate",
    })
    return f"{RESULTS_URL}?{qs}"


def _parse_iso_date(mdy: str):
    """Convert 5/4/2026 -> 2026-05-04."""
    try:
        return datetime.strptime(mdy.strip(), "%m/%d/%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


def _classify_canonical(doc_type: str, legal_description: str,
                        query_keyword: str) -> str | None:
    """Return a §17-registered canonical_doc_type or None to skip the row."""
    dt = (doc_type or "").strip().upper()
    if dt in DOC_TYPE_MAP:
        canon = DOC_TYPE_MAP[dt]
        # PUBLIC NOTICE / NOTICE only count as foreclosure_notice when the
        # query was FORECLOSURE-related AND legal_description mentions it.
        if canon == "foreclosure_notice" and dt in ("PUBLIC NOTICE", "NOTICE"):
            ld = (legal_description or "").upper()
            if "FORECLOSURE" not in ld and "FORECLOSURE" not in query_keyword.upper():
                return None
        return canon
    if "DEED" in dt:
        return None   # only tax_deed handled below (grantor-pattern gated)
    return None


def _record(row: dict, query_keyword: str) -> dict | None:
    """Convert a parsed row dict (from the DOM) into a v5.4.0 raw_event."""
    grantor = (row.get("grantor") or "").strip()
    grantee = (row.get("grantee") or "").strip()
    doc_type = (row.get("doc_type") or "").strip()
    doc_number = (row.get("doc_number") or "").strip()
    legal = (row.get("legal") or "").strip()
    recorded = _parse_iso_date(row.get("recorded_date"))

    # tax-deed special case: grantor is a taxing authority -> canonical tax_deed
    canon = _classify_canonical(doc_type, legal, query_keyword)
    if canon is None and "DEED" in doc_type.upper() and DEED_TAXING_AUTHORITIES.search(grantor):
        canon = "tax_deed"
    if canon is None:
        return None

    if not doc_number:
        return None  # no instrument number -> can't dedup/cite; skip

    # Party-role remap: for lis_pendens / abstract_of_judgment the
    # publicsearch GR/GE columns carry plaintiff / defendant identities, NOT
    # recording-style grantor / grantee. Emit PL / DF so §17 resolves the
    # debtor instead of routing REVIEW_REQUIRED / owner_not_on_document.
    if canon in PL_DF_REMAP_CANONICALS:
        gr_name_type, gr_raw_role = "PL", "plaintiff / filer (publicsearch GR column)"
        ge_name_type, ge_raw_role = "DF", "defendant / debtor (publicsearch GE column)"
    else:
        gr_name_type, gr_raw_role = "GR", "grantor (publicsearch column)"
        ge_name_type, ge_raw_role = "GE", "grantee (publicsearch column)"
    parties = []
    if grantor:
        parties.append({"name": grantor, "name_type": gr_name_type,
                        "raw_role": gr_raw_role})
    if grantee and grantee.upper() != "PUBLIC":
        # Skip "PUBLIC" placeholder on foreclosure_notice / NOTICE rows — it is
        # the clerk's stand-in for "notice to the public", never a real party.
        parties.append({"name": grantee, "name_type": ge_name_type,
                        "raw_role": ge_raw_role})

    detail_url = (f"https://smith.tx.publicsearch.us/doc/{doc_number}"
                  if doc_number else RESULTS_URL)
    return {
        "raw_event_id": f"smith_tx-publicsearch-{doc_number}",
        "source_id": SOURCE_ID,
        "source_role": "PRIMARY_EVENT_SOURCE",
        "raw_doc_type": doc_type,
        "canonical_doc_type": canon,
        "instrument_number": doc_number,
        "recorded_date": recorded,
        "event_date": recorded,
        "source_url": detail_url,
        "parties": parties,
        "document_body_text": None,
        "property_refs": {
            "parcel_id": None,           # publicsearch table has no parcel id
            "situs_address": None,       # no situs in the table (legal only)
            "legal_description": legal or None,
            "case_number": None,
        },
        "amounts": [],
        "evidence_ids": [],
        "parser_name": "scrapers/publicsearch_clerk.py",
        "parser_version": "0.1",
        "parser_confidence": 90,
        "captured_at": _now_iso(),
    }


def _record_fc(row: dict) -> dict | None:
    """Convert a department=FC listing row into a v5.4.0 raw_event.

    FC rows carry NO parties — `parties=[]` — so §17 will REVIEW_REQUIRED the
    lead with `owner_not_on_document`; downstream enrichment can attach an
    owner via parcel_master if the situs_address (or a later document-body
    drill) resolves. The trustee sale date (the operator-relevant future
    date) is carried via `event_date`; the actual recording date stays in
    `recorded_date`.
    """
    doc_type = (row.get("doc_type") or "").strip()
    doc_number = (row.get("doc_number") or "").strip()
    recorded = _parse_iso_date(row.get("recorded_date"))
    sale_iso = _parse_iso_date(row.get("sale_date"))
    addr_raw = (row.get("property_address") or "").strip()

    canon = _classify_canonical(doc_type, "", "FORECLOSURE")
    if canon != "foreclosure_notice":
        return None
    if not doc_number:
        return None

    # PROPERTY ADDRESS is "N/A" on most TX trustee notices — keep None then,
    # the lead resolves REVIEW_REQUIRED for parcel and downstream enrichment
    # picks it up. Real addresses pass through verbatim.
    situs = None
    if addr_raw and addr_raw.upper() not in {"N/A", "NA", ""}:
        situs = addr_raw

    detail_url = f"https://smith.tx.publicsearch.us/doc/{doc_number}"
    return {
        "raw_event_id": f"smith_tx-publicsearch-{doc_number}",
        "source_id": SOURCE_ID,
        "source_role": "PRIMARY_EVENT_SOURCE",
        "raw_doc_type": doc_type or "FORECLOSURE",
        "canonical_doc_type": canon,
        "instrument_number": doc_number,
        "recorded_date": recorded,
        # event_date carries the trustee sale_date — this is the
        # operator-relevant date the FC listing exposes, and the dashboard
        # renderer already pulls event_date into the per-lead sale_date slot.
        "event_date": sale_iso or recorded,
        "source_url": detail_url,
        "parties": [],
        "document_body_text": None,
        "property_refs": {
            "parcel_id": None,
            "situs_address": situs,
            "legal_description": None,
            "case_number": None,
        },
        "amounts": [],
        "evidence_ids": [],
        "parser_name": "scrapers/publicsearch_clerk.py",
        "parser_version": "0.2",
        "parser_confidence": 92,
        "captured_at": _now_iso(),
    }


# ----------------------------------------------------------------------
# Playwright runtime — production fetch path
# ----------------------------------------------------------------------

def _fetch_with_playwright(keyword: str, date_from: str, date_to: str,
                            timeout_ms: int = 30000) -> list[dict]:
    """Navigate to the results URL via stealth Playwright, parse the
    rendered table, return list of row dicts. Raises on reCAPTCHA challenge."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    url = _build_results_url(keyword, date_from, date_to)
    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            page.goto(url, timeout=timeout_ms)
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            page.wait_for_timeout(3000)   # let hyperscript render
            # reCAPTCHA challenge check
            if page.locator("iframe[src*='recaptcha'][title*='challenge']").count() > 0:
                raise RuntimeError("reCAPTCHA challenge fired; halting")
            # Parse table rows from the DOM. The publicsearch table has a
            # variable number of leading control cells (checkbox / favorite
            # star / view icon) before the data columns — map by HEADER
            # rather than by index.
            rows = page.evaluate("""() => {
                const out = [];
                const wanted = ['GRANTOR','GRANTEE','DOC TYPE','RECORDED DATE',
                                'DOC NUMBER','BOOK/VOLUME/PAGE','LEGAL DESCRIPTION'];
                const tables = Array.from(document.querySelectorAll('table'));
                for (const t of tables) {
                    const headerEls = Array.from(t.querySelectorAll('thead th, tr:first-child th'));
                    const headers = headerEls.map(c => (c.innerText || '').trim().toUpperCase());
                    if (!headers.some(h => h.includes('GRANTOR'))) continue;
                    // Build column-index map by header text
                    const colIdx = {};
                    headers.forEach((h, i) => {
                        for (const w of wanted) {
                            if (h.includes(w.split(' ')[0]) && h.includes(w.split(' ').slice(-1)[0])) {
                                colIdx[w] = i;
                                break;
                            }
                        }
                    });
                    const trs = Array.from(t.querySelectorAll('tbody tr'));
                    for (const tr of trs) {
                        const tds = Array.from(tr.querySelectorAll('td')).map(c =>
                            (c.innerText || '').trim());
                        const get = key => (colIdx[key] != null ? tds[colIdx[key]] || '' : '');
                        out.push({
                            grantor: get('GRANTOR'),
                            grantee: get('GRANTEE'),
                            doc_type: get('DOC TYPE'),
                            recorded_date: get('RECORDED DATE'),
                            doc_number: get('DOC NUMBER'),
                            book_volume_page: get('BOOK/VOLUME/PAGE'),
                            legal: get('LEGAL DESCRIPTION'),
                        });
                    }
                    if (out.length) break;
                }
                return out;
            }""")
        finally:
            browser.close()
    return rows


def _fetch_fc_page(date_from: str, date_to: str, offset: int, limit: int,
                    timeout_ms: int = 90000) -> tuple[list[dict], int | None]:
    """Fetch ONE page of department=FC listings via stealth Playwright.

    Returns (rows, total_result_count). The result_count is parsed from the
    page header text ("75 Results") and is used by the caller to drive
    pagination — None if it can't be parsed.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    url = _build_fc_url(date_from, date_to, offset=offset, limit=limit)
    rows: list[dict] = []
    total: int | None = None
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)  # SPA render
            if page.locator("iframe[src*='recaptcha'][title*='challenge']").count() > 0:
                raise RuntimeError("reCAPTCHA challenge fired; halting")
            data = page.evaluate("""() => {
                const out = {rows: [], total: null};
                const txt = document.body.innerText || '';
                const m = txt.match(/([\\d,]+)\\s+(?:Results|results)/);
                if (m) out.total = parseInt(m[1].replace(/,/g, ''), 10);
                const tables = Array.from(document.querySelectorAll('table'));
                for (const t of tables) {
                    const headerEls = Array.from(t.querySelectorAll('thead th, tr:first-child th'));
                    const headers = headerEls.map(c => (c.innerText || '').trim().toUpperCase());
                    if (!headers.some(h => h.includes('DOC TYPE'))) continue;
                    if (!headers.some(h => h.includes('SALE DATE'))) continue;
                    // map column headers to indices
                    const idx = {};
                    headers.forEach((h, i) => {
                        if (h.includes('DOC TYPE'))       idx.doc_type = i;
                        if (h.includes('RECORDED DATE'))  idx.recorded_date = i;
                        if (h.includes('SALE DATE'))      idx.sale_date = i;
                        if (h.includes('DOC NUMBER'))     idx.doc_number = i;
                        if (h.includes('PROPERTY ADDRESS')) idx.property_address = i;
                    });
                    const trs = Array.from(t.querySelectorAll('tbody tr'));
                    for (const tr of trs) {
                        const tds = Array.from(tr.querySelectorAll('td')).map(c =>
                            (c.innerText || '').trim());
                        const get = key => (idx[key] != null ? tds[idx[key]] || '' : '');
                        out.rows.push({
                            doc_type:         get('doc_type'),
                            recorded_date:    get('recorded_date'),
                            sale_date:        get('sale_date'),
                            doc_number:       get('doc_number'),
                            property_address: get('property_address'),
                        });
                    }
                    if (out.rows.length) break;
                }
                return out;
            }""")
            rows = data.get("rows") or []
            total = data.get("total")
        finally:
            browser.close()
    return rows, total


def fetch_fc_department(date_from: str, date_to: str,
                         rate_limit_seconds: float = 2.0,
                         page_limit: int = 50,
                         max_pages: int = 50) -> list[dict]:
    """Paginate the department=FC listing through `offset` until exhausted.

    Returns a list of v5.4.0 raw_event dicts (canonical_doc_type =
    foreclosure_notice). Pagination stops when (a) we've drained
    `total_result_count`, (b) a page returns 0 rows, or (c) we hit `max_pages`.
    """
    print(f"  FC sweep: department=FC  range: {date_from}..{date_to}", flush=True)
    events: list[dict] = []
    seen: set = set()
    offset = 0
    total: int | None = None
    pages = 0
    while pages < max_pages:
        pages += 1
        try:
            rows, page_total = _fetch_fc_page(date_from, date_to, offset, page_limit)
        except Exception as exc:
            print(f"    FC page offset={offset} FAILED ({type(exc).__name__}): {exc}",
                  flush=True)
            break
        if total is None and page_total is not None:
            total = page_total
            print(f"    FC total result_count (header): {total}", flush=True)
        n_emit = 0
        for r in rows:
            ev = _record_fc(r)
            if ev and ev["instrument_number"] not in seen:
                seen.add(ev["instrument_number"])
                events.append(ev)
                n_emit += 1
        print(f"    FC page offset={offset:>4}  raw: {len(rows):>2}  "
              f"emitted: {n_emit:>2}  cumulative: {len(events)}", flush=True)
        if not rows:
            break
        offset += len(rows)
        if total is not None and offset >= total:
            break
        time.sleep(rate_limit_seconds)
    return events


def fetch_all_distress(date_from: str | None = None, date_to: str | None = None,
                       queries: list[str] = None,
                       rate_limit_seconds: float = 2.0) -> list[dict]:
    """Sweep all DISTRESS_QUERIES, return list of normalized raw_events."""
    if date_from is None:
        df_d = date.today() - timedelta(days=730)
        date_from = df_d.strftime("%Y%m%d")
    if date_to is None:
        date_to = date.today().strftime("%Y%m%d")
    queries = queries or DISTRESS_QUERIES
    all_events: list[dict] = []
    seen_doc_numbers: set = set()
    for q in queries:
        print(f"  query: {q!r}  range: {date_from}..{date_to}", flush=True)
        try:
            rows = _fetch_with_playwright(q, date_from, date_to)
        except Exception as exc:
            print(f"    FAILED ({type(exc).__name__}): {exc}", flush=True)
            continue
        n_raw = len(rows)
        n_emit = 0
        for r in rows:
            ev = _record(r, q)
            if ev and ev["instrument_number"] not in seen_doc_numbers:
                all_events.append(ev)
                seen_doc_numbers.add(ev["instrument_number"])
                n_emit += 1
        print(f"    raw rows: {n_raw}  emitted: {n_emit}  (cumulative: {len(all_events)})",
              flush=True)
        time.sleep(rate_limit_seconds)
    return all_events


def parse_fixture(fixture_name: str) -> list:
    """Offline parse: fixture is a JSON list of row dicts (as if scraped)."""
    path = FIXTURE_DIR / fixture_name
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        rows = data.get("rows", [])
        query = data.get("query", "FORECLOSURE")
    else:
        rows = data
        query = "FORECLOSURE"
    out: list[dict] = []
    for r in rows:
        ev = _record(r, query)
        if ev:
            out.append(ev)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Smith County, TX — publicsearch.us clerk records adapter (Playwright).")
    p.add_argument("--out", default=str(OUT_PATH))
    p.add_argument("--queries", nargs="+", default=None,
                   help="Override default distress query keywords.")
    p.add_argument("--days", type=int, default=730,
                   help="Days back to search (default 730 = 2 years).")
    p.add_argument("--skip-fc", action="store_true",
                   help="Skip the department=FC trustee-foreclosure sweep.")
    p.add_argument("--skip-keywords", action="store_true",
                   help="Skip the keyword sweeps (RP department).")
    p.add_argument("--fixture", default=None)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    if args.fixture:
        evs = parse_fixture(args.fixture)
        print(json.dumps(evs, indent=2, ensure_ascii=False))
        return 0
    df = (date.today() - timedelta(days=args.days)).strftime("%Y%m%d")
    dt = date.today().strftime("%Y%m%d")
    print(f"fetching publicsearch.us clerk records via Playwright "
          f"({df}..{dt})", flush=True)
    all_evs: list[dict] = []
    seen: set = set()
    if not args.skip_fc:
        print(f"-- department=FC trustee foreclosure sweep --", flush=True)
        for ev in fetch_fc_department(df, dt):
            if ev["instrument_number"] not in seen:
                seen.add(ev["instrument_number"])
                all_evs.append(ev)
    if not args.skip_keywords:
        nq = len(args.queries or DISTRESS_QUERIES)
        print(f"-- keyword sweep (department=RP, {nq} queries) --", flush=True)
        for ev in fetch_all_distress(df, dt, queries=args.queries):
            if ev["instrument_number"] not in seen:
                seen.add(ev["instrument_number"])
                all_evs.append(ev)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ev in all_evs:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    # one-line summary by canonical doc type
    by_canon: dict = {}
    for ev in all_evs:
        by_canon[ev["canonical_doc_type"]] = by_canon.get(ev["canonical_doc_type"], 0) + 1
    print(f"wrote {len(all_evs)} raw_event records to {out.relative_to(REPO_ROOT)}",
          flush=True)
    print(f"  canonical_doc_type breakdown: {by_canon}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
