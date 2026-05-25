"""Smith County, TX — delinquent-tax SFTP drop adapter (ENRICHMENT).

STAGE BOUNDARY (§13 / §16): This source carries TAX-ROLL DELINQUENCY STATUS
— how much an account owes, since which year, to which taxing units — NOT
recorded distress events. Per the framework's source-of-record rules, that
makes it ENRICHMENT-only:

  - It DOES NOT emit `raw_event` rows.
  - It DOES NOT feed §17 debtor_party_engine.
  - It DOES attach delinquency fields to existing Smith leads via
    `parcel_id` join, alongside parcel_master CAD enrichment.

Source layout (operator-verified 2026-05-25 against the official drop):

    sftp://mft.smi.tax:22/  user=taxrolls
        /Smith/TaxRoll_Smith_Flat_V1_YYYY_MM_DD.zip   (weekly)
            MM*.DAT  Master account records, 951-char fixed-width, 210,057 rows
            MR*.DAT  Master Receivables (line items), 224-char fixed-width,
                     1,185,702 rows.  account × tax_year × tax_unit
                                       + 12-char outstanding amount field.
            MS*.DAT  Summary by year (totals: $34.3M owed across 1.18M items).
            TU*.DAT  Taxing-unit roster, 35 units (codes 001-035).

For enrichment we only need MR (and TU for the unit code → name lookup): each
account's outstanding balance is the SUM of its MR receivable line items.
MM is heavier and the owner / legal-description fields it carries are already
available through parcel_master — so this adapter skips MM by default.

Output format — one JSON line per delinquent account, schema:

    {
      "parcel_id":            "100000038101031000",
      "delinquent_balance":   1903.17,
      "years_delinquent":     ["2025"],
      "earliest_year":        2025,
      "latest_year":          2025,
      "years_back":           1,
      "delinquent_units":     5,
      "delinquent_unit_codes": ["006","015","016","018","023"],
      "_enrichment_source":   "smith_delinquent_tax_sftp",
      "_drop_label":          "TaxRoll_Smith_Flat_V1_2026_05_23",
      "_captured_at":         "2026-05-25T..."
    }

Output path: data/raw/smith_delinquent_tax.jsonl

Credentials. Defaults are baked in (operator-shared) but may be overridden
via env vars:

    SMITH_TAX_SFTP_HOST     (default: mft.smi.tax)
    SMITH_TAX_SFTP_USER     (default: taxrolls)
    SMITH_TAX_SFTP_PASSWORD (no default — falls back to baked-in if unset)
"""
from __future__ import annotations
import argparse, json, os, re, stat as _stat, sys, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ID = "smith_delinquent_tax"
OUT_PATH = REPO_ROOT / "data" / "raw" / f"{SOURCE_ID}.jsonl"
CACHE_DIR = REPO_ROOT / "data" / "raw" / SOURCE_ID

# Credentials. Loaded from env vars or a gitignored config file. NEVER baked
# into source. Resolution order:
#   1. SMITH_TAX_SFTP_PASSWORD env var
#   2. SMITH_TAX_SFTP_PWFILE env var pointing at a file containing the password
#   3. ./.secrets/smith_tax_sftp.env (gitignored), parsed for KEY=VALUE lines
# Daily-refresh CI feeds these from GitHub secrets (see
# .github/workflows/daily-refresh.yml). Local runs read from .secrets/.
SECRETS_FILE = REPO_ROOT / ".secrets" / "smith_tax_sftp.env"
SFTP_REMOTE_DIR = "/Smith"


def _load_credentials() -> tuple[str, str, str]:
    """Return (host, user, password) — fail loud if password unresolved."""
    host = os.environ.get("SMITH_TAX_SFTP_HOST", "")
    user = os.environ.get("SMITH_TAX_SFTP_USER", "")
    pw   = os.environ.get("SMITH_TAX_SFTP_PASSWORD", "")
    pwfile = os.environ.get("SMITH_TAX_SFTP_PWFILE", "")
    if not pw and pwfile:
        try:
            pw = Path(pwfile).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    if (not pw or not host or not user) and SECRETS_FILE.exists():
        for raw in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, _, v = raw.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "SMITH_TAX_SFTP_HOST" and not host: host = v
            if k == "SMITH_TAX_SFTP_USER" and not user: user = v
            if k == "SMITH_TAX_SFTP_PASSWORD" and not pw: pw = v
    if not pw:
        raise SystemExit(
            "FATAL: SMITH_TAX_SFTP_PASSWORD not set. Provide via env var, "
            "SMITH_TAX_SFTP_PWFILE, or .secrets/smith_tax_sftp.env "
            "(gitignored). See header docstring for details.")
    return (host or "mft.smi.tax", user or "taxrolls", pw)


# MR fixed-width layout (verified against the 2026-05-23 drop's MS summary).
# Each row is 224 characters (plus trailing newline).
#
# The MR file carries TWO 12-char amount fields. Confirmed empirically that
# the SECOND field is the field whose grand-total matches the operator-
# supplied MS summary ($34,326,313.04 across 1,185,702 line items):
#     pos 63-74 (decimal @ 72)  =  amount BILLED to date (incl. P&I accrual)
#     pos 75-86 (decimal @ 84)  =  amount OUTSTANDING (current open balance)
# We aggregate on the OUTSTANDING field and filter rows to outstanding>0 so
# closed/paid line items (which the file retains for audit) do not inflate.
MR_ACCOUNT      = slice(0, 18)
MR_YEAR         = slice(30, 34)
MR_UNIT         = slice(34, 37)
MR_BILLED_RAW   = slice(63, 75)
MR_OUTSTANDING_RAW = slice(75, 87)

# MM fixed-width layout (verified empirically against the 2026-05-23 drop).
# Each row is 950 characters. Field positions identified via density profile
# + visual cross-check on the first 10 rows; valid for the V1 schema.
MM_ACCOUNT      = slice(0, 18)
MM_OWNER_NAME   = slice(334, 384)   # 50 chars
MM_OWNER_STREET = slice(434, 484)   # 50 chars
MM_OWNER_CITY   = slice(534, 584)   # 50 chars
MM_OWNER_STATE  = slice(580, 582)   # 2 chars (NB: city slice runs to 584;
                                    # state overlaps the trailing pad of city
                                    # in some rows — strip+validate downstream)
MM_OWNER_ZIP    = slice(600, 610)   # 10 chars

# Estate-title detection — three orthogonal classifiers.
#
# 1. CORP_SUFFIX_RE — corporate / entity owners. ESTATE-shaped strings on
#    these are commercial naming ("REFORGED REAL ESTATE LLC", "ESTATE
#    PALIFROVA FIX & FLIPS LLC", "JORDAN MARGARET ROYALTIES INC EST"), NOT
#    decedent estates. Hard exclusion from BOTH probate and life-estate.
#
# 2. LIFE_ESTATE_PATTERNS — a life estate is a living estate-planning
#    arrangement; the named life-tenant is alive. NOT probate. Tagged
#    separately as `life_estate` so the operator can see them but not
#    confuse them with motivated-heir probate leads.
#
# 3. ESTATE_PATTERNS — genuine decedent estates: "ESTATE OF X", "EST OF X",
#    "X ESTATE", "X (DECD)", "X DECEASED", "X DCSD", "HEIRS OF X". Operator
#    keep-list per 2026-05-25 spec.
CORP_SUFFIX_RE = re.compile(
    r"\b("
    r"LLC|L\.L\.C\.|INC|INCORPORATED|CORP|CORPORATION|"
    r"LP|LLP|LLLP|PLLC|PA|PC|"
    r"COMPANY|CO\.|CO,|"
    r"REALTY|REAL\s+ESTATE|REAL\s+ESTATES|PROPERTIES|PROPERTY|"
    r"HOMES|ESTATES|HOLDINGS|INVESTMENTS|VENTURES|PARTNERS|"
    r"PARTNERSHIP|GROUP|FUND|TRUST|REVOCABLE|IRREVOCABLE|"
    r"RENTALS|MANAGEMENT|ENTERPRISE|ENTERPRISES|ROYALTIES|"
    r"BANK|N\.A\.|CHURCH|MINISTRIES|CITY\s+OF|COUNTY\s+OF|"
    r"STATE\s+OF|ISD|SCHOOL\s+DISTRICT"
    r")\b",
    re.IGNORECASE)

LIFE_ESTATE_PATTERNS = re.compile(
    r"\bLIFE\s+ESTATES?\b|\bLIFE\s+ESTS?\b|"
    r"\bL\s*/\s*E\b|\bL\.E\.\b",
    re.IGNORECASE)

# Real decedent-estate patterns. Each requires either a leading/trailing
# context that disambiguates from corporate "ESTATE" or "EST" usage.
ESTATE_PATTERNS = re.compile(
    r"\bESTATE\s+OF\b|"                           # ESTATE OF X
    r"\bEST\s+OF\b|"                              # EST OF X
    r"\bESTATE\s*(?:\(|$)|"                       # X ESTATE end-of-string or "X ESTATE (..."
    r"\s+ESTATE\s*$|"                             # X ESTATE (end)
    r"\s+EST\s*$|"                                # X EST (end)
    r"\bDECEASED\b|"                              # X DECEASED
    r"\bDEC[''’]?D\b|"                            # X DEC'D
    r"\bDCSD\b|"                                  # X DCSD
    r"\bDECD\b|"                                  # X DECD
    r"\bHEIRS?\s+OF\b|"                           # HEIRS OF X
    r"\(\s*DECD\s*\)|"                            # (DECD)
    r"\(\s*DECEASED\s*\)",                        # (DECEASED)
    re.IGNORECASE)


def classify_owner_estate(owner: str) -> str:
    """Return one of: 'estate' (decedent probate), 'life_estate' (living
    estate-planning vehicle — NOT probate), or '' (neither).

    Order matters:
      1. Corporate / entity / trust → never estate-typed (excluded)
      2. Life-estate phrase wins over generic ESTATE match
      3. Genuine probate patterns
    """
    if not owner:
        return ""
    if CORP_SUFFIX_RE.search(owner):
        return ""
    if LIFE_ESTATE_PATTERNS.search(owner):
        return "life_estate"
    if ESTATE_PATTERNS.search(owner):
        return "estate"
    return ""


def is_estate_titled(owner: str) -> bool:
    """True iff the owner-name string reads as a DECEDENT estate (real
    probate lead). Excludes corporates AND life estates."""
    return classify_owner_estate(owner) == "estate"


def is_life_estate(owner: str) -> bool:
    """True iff the owner reads as a LIVING life estate (estate-planning
    vehicle — NOT probate)."""
    return classify_owner_estate(owner) == "life_estate"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# SFTP download
# ---------------------------------------------------------------------------

def _sftp_connect():
    """Open and return (transport, sftp_client) using paramiko."""
    import paramiko
    host, user, pw = _load_credentials()
    transport = paramiko.Transport((host, 22))
    transport.connect(username=user, password=pw)
    return transport, paramiko.SFTPClient.from_transport(transport)


def list_remote_drops() -> list[tuple[str, int]]:
    """Return [(filename, size_bytes), ...] of all Smith/TaxRoll zips,
    newest first."""
    transport, sftp = _sftp_connect()
    try:
        entries = sftp.listdir_attr(SFTP_REMOTE_DIR)
    finally:
        sftp.close(); transport.close()
    files = [(e.filename, e.st_size) for e in entries
             if not _stat.S_ISDIR(e.st_mode)
             and e.filename.lower().endswith(".zip")]
    files.sort(reverse=True)
    return files


def download_latest_drop(dest_dir: Path) -> Path:
    """Download the most-recent /Smith/TaxRoll_Smith_Flat_V1_*.zip into
    `dest_dir` and return its local path. No-op (just returns the path) when
    the local copy already exists at the same size as the remote."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    transport, sftp = _sftp_connect()
    try:
        entries = sftp.listdir_attr(SFTP_REMOTE_DIR)
        zips = [e for e in entries if e.filename.lower().endswith(".zip")
                and not _stat.S_ISDIR(e.st_mode)]
        if not zips:
            raise RuntimeError(f"no .zip files in {SFTP_REMOTE_DIR}")
        latest = max(zips, key=lambda e: e.filename)
        local = dest_dir / latest.filename
        if local.exists() and local.stat().st_size == latest.st_size:
            print(f"  [sftp] cached: {local.name} "
                  f"({latest.st_size:,} bytes)", flush=True)
        else:
            print(f"  [sftp] downloading {SFTP_REMOTE_DIR}/{latest.filename} "
                  f"({latest.st_size:,} bytes) -> {local}", flush=True)
            sftp.get(f"{SFTP_REMOTE_DIR}/{latest.filename}", str(local))
    finally:
        sftp.close(); transport.close()
    return local


# ---------------------------------------------------------------------------
# Local extraction + MR aggregation
# ---------------------------------------------------------------------------

def _extract_zip(zip_path: Path, extract_to: Path) -> dict[str, Path]:
    """Extract the four DAT files; return {prefix: path} where prefix is one
    of 'MM','MR','MS','TU'. Already-extracted files are reused."""
    extract_to.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            m = re.match(r"^(MM|MR|MS|TU)\d+\.DAT$", name, re.IGNORECASE)
            if not m:
                continue
            prefix = m.group(1).upper()
            target = extract_to / name
            if not target.exists() or target.stat().st_size != info.file_size:
                print(f"  [zip] extracting {name} "
                      f"({info.file_size:,} bytes)", flush=True)
                zf.extract(info, extract_to)
            out[prefix] = target
    return out


def _parse_mr_amount(raw: str) -> float:
    """Parse the MR outstanding-amount field. The 12-char field carries an
    implicit status digit in the high position; the value-with-decimal is
    in the trailing 11 chars. Examples:
        '200000310.27' -> 310.27   (status '2' = open balance)
        '000000000.00' ->   0.00
    Returns 0.0 on any parse failure (defensive — partial rows do not
    poison the aggregate)."""
    s = (raw or "").rstrip()
    if not s or "." not in s:
        return 0.0
    # The field is a fixed 12 chars wide: 1 status digit + 8 integer digits +
    # '.' + 2 fraction digits. Strip the status prefix by taking the last 11
    # chars; that yields an unambiguous "<int>.<frac>" amount.
    body = s[-11:] if len(s) >= 11 else s
    try:
        return float(body)
    except ValueError:
        return 0.0


def aggregate_mr(mr_path: Path) -> dict[str, dict]:
    """Stream the MR receivables file and aggregate by account_nbr.

    Returns: {parcel_id: {
        "delinquent_balance": float,
        "years_delinquent": sorted list[str],
        "earliest_year": int|None,
        "latest_year": int|None,
        "years_back": int,
        "delinquent_units": int,
        "delinquent_unit_codes": sorted list[str],
    }}
    """
    bal: dict[str, float] = defaultdict(float)
    billed: dict[str, float] = defaultdict(float)
    years: dict[str, set] = defaultdict(set)
    units: dict[str, set] = defaultdict(set)
    n_rows = 0
    n_open = 0
    with mr_path.open(encoding="latin-1") as f:
        for line in f:
            if len(line) < 87:
                continue
            acct = line[MR_ACCOUNT].strip()
            if not acct:
                continue
            yr = line[MR_YEAR].strip()
            unit = line[MR_UNIT].strip()
            outstanding = _parse_mr_amount(line[MR_OUTSTANDING_RAW])
            n_rows += 1
            # Closed / paid line items carry outstanding = 0.00; the file
            # retains them for audit. Drop them — they do not represent
            # active delinquency.
            if outstanding <= 0:
                continue
            n_open += 1
            bal[acct] += outstanding
            billed[acct] += _parse_mr_amount(line[MR_BILLED_RAW])
            if yr.isdigit():
                years[acct].add(yr)
            if unit:
                units[acct].add(unit)
            if n_rows % 200000 == 0:
                print(f"    [mr] scanned {n_rows:,} rows  "
                      f"open: {n_open:,}", flush=True)
    out: dict[str, dict] = {}
    for acct, total in bal.items():
        yrs = sorted(years[acct])
        earliest = int(yrs[0]) if yrs else None
        latest = int(yrs[-1]) if yrs else None
        years_back = len(yrs)   # distinct unpaid years (not span)
        out[acct] = {
            "delinquent_balance": round(total, 2),
            "billed_total": round(billed[acct], 2),
            "years_delinquent": yrs,
            "earliest_year": earliest,
            "latest_year": latest,
            # years_back is the COUNT of distinct unpaid years — the operator
            # signal that gates "real distress" (3+ years).
            "years_back": years_back,
            "delinquent_units": len(units[acct]),
            "delinquent_unit_codes": sorted(units[acct]),
        }
    print(f"  [mr] {n_rows:,} total rows  "
          f"{n_open:,} open  ->  {len(out):,} delinquent accounts  "
          f"(${sum(r['delinquent_balance'] for r in out.values()):,.2f})",
          flush=True)
    return out


def parse_mm_owners(mm_path: Path,
                     wanted_accts: set[str] | None = None) -> dict[str, dict]:
    """Stream MM master file and return {parcel_id: {owner_name, city, ...,
    estate_titled, mm_payment_plan_flag}}.

    `wanted_accts` — restrict parsing to a known-delinquent set (saves time;
    the MM file carries every assessed account, not just delinquent ones).
    """
    out: dict[str, dict] = {}
    n = 0
    n_kept = 0
    with mm_path.open(encoding="latin-1") as f:
        for line in f:
            n += 1
            if len(line) < 610:
                continue
            acct = line[MM_ACCOUNT].strip()
            if not acct:
                continue
            if wanted_accts is not None and acct not in wanted_accts:
                continue
            owner = line[MM_OWNER_NAME].strip()
            street = line[MM_OWNER_STREET].strip()
            city = line[MM_OWNER_CITY].strip()
            state = line[MM_OWNER_STATE].strip()
            zipc = line[MM_OWNER_ZIP].strip()
            out[acct] = {
                "owner_name": owner or None,
                "owner_street": street or None,
                "owner_city": city or None,
                "owner_state": state or None,
                "owner_zip": zipc or None,
                # Three orthogonal estate classifiers — corporates are
                # excluded from BOTH; living life estates are tagged
                # `life_estate` (NOT probate); decedent estates are
                # `estate_titled`.
                "estate_titled": is_estate_titled(owner),
                "life_estate":   is_life_estate(owner),
                # No genuine payment-plan flag exists in MM (verified 2026-05-25
                # via keyword sweep across the 950-char layout — PLAN keyword
                # only catches "PLANO" the city; AGREEM only catches trust
                # agreements; no INSTAL/DEFER/CONTRACT match a real plan
                # field). The few "1-52" / "1-2-5" codes after the
                # delinquent-since date in pos 610-700 are attorney case-folder
                # codes, not installment plans. Field reserved for the day a
                # plan flag appears in a future schema version.
                "mm_payment_plan_flag": None,
            }
            n_kept += 1
            if n % 50000 == 0:
                print(f"    [mm] scanned {n:,}  kept {n_kept:,}", flush=True)
    print(f"  [mm] {n:,} master rows scanned -> "
          f"{n_kept:,} owners harvested", flush=True)
    return out


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_enrichment_jsonl(agg: dict[str, dict],
                            owners: dict[str, dict],
                            drop_label: str,
                            out_path: Path) -> int:
    """Write one JSON line per delinquent account to `out_path`. Each line
    carries the MR delinquency aggregate AND the MM owner-name slice (for
    estate-detection + dashboard display when the parcel isn't covered by
    the Smith CAD enrichment join)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    captured = _now_iso()
    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for acct, rec in sorted(agg.items()):
            mm = owners.get(acct) or {}
            row = {
                "parcel_id": acct,
                **rec,
                **mm,
                "_enrichment_source": "smith_delinquent_tax_sftp",
                "_drop_label": drop_label,
                "_captured_at": captured,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Smith County, TX — delinquent-tax SFTP enrichment adapter.")
    p.add_argument("--out", default=str(OUT_PATH))
    p.add_argument("--cache-dir", default=str(CACHE_DIR),
                   help="Local directory for downloaded zip + extracted DAT files.")
    p.add_argument("--zip", default=None,
                   help="Reuse a specific local zip (skip SFTP download).")
    p.add_argument("--list", action="store_true",
                   help="Just list available remote drops and exit.")
    p.add_argument("--no-fetch", action="store_true",
                   help="Skip SFTP; reuse newest local zip in --cache-dir.")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    cache_dir = Path(args.cache_dir).resolve()
    if args.list:
        for name, size in list_remote_drops():
            print(f"  {size:>14,}  {name}")
        return 0

    if args.zip:
        zip_path = Path(args.zip).resolve()
        if not zip_path.exists():
            print(f"FATAL: {zip_path} not found", file=sys.stderr); return 2
    elif args.no_fetch:
        cache_dir.mkdir(parents=True, exist_ok=True)
        candidates = sorted(cache_dir.glob("TaxRoll_Smith_Flat_V1_*.zip"),
                            reverse=True)
        if not candidates:
            print(f"FATAL: no cached zip in {cache_dir}", file=sys.stderr); return 2
        zip_path = candidates[0]
        print(f"  [cache] reusing {zip_path.name}", flush=True)
    else:
        zip_path = download_latest_drop(cache_dir)

    drop_label = zip_path.stem    # e.g. TaxRoll_Smith_Flat_V1_2026_05_23
    extracted = _extract_zip(zip_path, cache_dir / "extracted")
    if "MR" not in extracted:
        print(f"FATAL: no MR receivables file in {zip_path.name}",
              file=sys.stderr); return 3
    print(f"\nparsing MR receivables: {extracted['MR'].name}", flush=True)
    agg = aggregate_mr(extracted["MR"])
    delinquent_accts = set(agg.keys())
    owners: dict[str, dict] = {}
    if "MM" in extracted:
        print(f"\nparsing MM owner names (filtered to delinquent set): "
              f"{extracted['MM'].name}", flush=True)
        owners = parse_mm_owners(extracted["MM"], wanted_accts=delinquent_accts)
    n = write_enrichment_jsonl(agg, owners, drop_label, Path(args.out).resolve())

    # quick summary stats
    if agg:
        total_owed = sum(r["delinquent_balance"] for r in agg.values())
        deep = sum(1 for r in agg.values() if r["years_back"] >= 3)
        oldest = min((r["earliest_year"] for r in agg.values()
                      if r["earliest_year"]), default=None)
        estate_count = sum(1 for a in delinquent_accts
                            if (owners.get(a) or {}).get("estate_titled"))
        plan_count = sum(1 for a in delinquent_accts
                          if (owners.get(a) or {}).get("mm_payment_plan_flag"))
        print(f"  total delinquent: ${total_owed:,.2f} across {n:,} accounts")
        print(f"  accounts with 3+ years back: {deep:,}")
        print(f"  oldest unpaid year: {oldest}")
        print(f"  estate-titled delinquent accounts: {estate_count:,}")
        print(f"  payment-plan-flagged accounts: {plan_count:,} "
              f"(field absent from MM V1 schema — see header note)")
    print(f"wrote {n} enrichment records to "
          f"{Path(args.out).resolve().relative_to(REPO_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
