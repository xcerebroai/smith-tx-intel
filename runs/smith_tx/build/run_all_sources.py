#!/usr/bin/env python3
"""Smith TX v5.4.0 — all stdlib primary sources end-to-end + dashboard.

Loads LGBS + PBFCM + County Excess Proceeds raw_events, pre-resolves
parcel_id for those that carry one, runs the staged pipeline §17->§20,
patches primary_parcel_id between §19 and the seam (F-1 framework
workaround), scores with parcel_master enrichment, renders the El Paso
dashboard payload, and writes dashboard/data.json + data.js.

No scaffold/ or knowledge_base/ edits. Stops on crash or §20 DEPLOY_BLOCKED.

Stage boundaries (preserved):
- event_source        = LGBS / PBFCM / Excess Proceeds (PRIMARY_EVENT_SOURCE)
- owner_source        = parcel_master enrichment OR §17 DF fallback (excess proc.)
- enrichment_source   = parcel_master (Smith CAD TaxParcels)
- §17 reads event-document parties only — parcel_master never feeds §17
"""
from __future__ import annotations
import json, re, sys, urllib.parse, urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path("/Users/quentinflores/Dev/xcerebro/counties/smith-tx")
sys.path.insert(0, str(REPO))
from scaffold.pipeline import (
    aggregator, debtor_party_engine,
    evidence_ledger as evidence_ledger_mod,
    leads_base_writer, scoring_seam, semantic_verify,
)
from scaffold.pipeline.run_pipeline_staged import build_dashboard_payload

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
TODAY = date.today()
WORKDIR = REPO / "runs" / "smith_tx" / "build" / "staged_v5_4_0_all_sources"
WORKDIR.mkdir(parents=True, exist_ok=True)
DASH = REPO / "dashboard"
RAW = REPO / "data" / "raw"
CAD_URL = ("https://www.smithcountymapsite.org/publicgis/rest/services/"
           "Gallery/TaxParcelQuery/MapServer/1/query")
UA = {"User-Agent": "Mozilla/5.0 (xcerebro-smith-tx-all/0.1)",
      "Accept": "application/json"}

punch: list = []
def P(msg): punch.append(msg); print(f"  punch: {msg}")

# ---- 1. Load raw_events from every adapter that produced output ----------
# STAGE BOUNDARY: smith_delinquent_tax is ENRICHMENT-only (delinquency status
# is tax-roll state, not a recorded distress event — §13 / §16.B). It is
# LOADED below but NEVER added to SOURCES, NEVER fed to §17, and NEVER
# allowed to originate a standalone lead. It only stacks onto primary leads
# that already exist for the same parcel_id.
# county_excess_proceeds (sheriff_sale_surplus) DROPPED from active sources
# 2026-05-25 per operator framework decision — the client does not work
# surplus. The scraper code at scrapers/county_excess_proceeds.py stays in
# tree for future re-enable, but its raw_events file is intentionally
# excluded from this SOURCES list so it never enters the §17 / dashboard
# pipeline.
SOURCES = ["lgbs_smith_tax_sales", "pbfcm_smith_tax_resale", "publicsearch_clerk"]
raw_events: list = []
per_source: dict = {}
for sid in SOURCES:
    p = RAW / f"{sid}.jsonl"
    if not p.exists():
        P(f"missing raw file: data/raw/{sid}.jsonl — adapter not yet run")
        continue
    n = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw_events.append(json.loads(line))
                n += 1
    per_source[sid] = n
    print(f"  loaded {n:>3} raw_events from {sid}")
print(f"  total: {len(raw_events)} raw_events across {len(per_source)} sources")

# ---- 2. Targeted Smith CAD enrichment cache by parcel_id -----------------
parcel_ids = sorted({ev.get("property_refs", {}).get("parcel_id")
                     for ev in raw_events
                     if ev.get("property_refs", {}).get("parcel_id")})
print(f"\n  distinct parcel_ids carried by raw_events: {len(parcel_ids)}")
parcel_cache: dict = {}
if parcel_ids:
    quoted = ",".join("'%s'" % a for a in parcel_ids)
    params = urllib.parse.urlencode({"where": f"ACCOUNT IN ({quoted})",
        "outFields": "*", "returnGeometry": "false", "f": "json"})
    with urllib.request.urlopen(
        urllib.request.Request(CAD_URL + "?" + params, headers=UA), timeout=30
    ) as r:
        feats = json.loads(r.read()).get("features", [])
    for f in feats:
        a = f.get("attributes") or {}
        acct = (a.get("ACCOUNT") or "").strip()
        if acct and acct not in parcel_cache:
            parcel_cache[acct] = a
    print(f"  Smith CAD enrichment cache: {len(parcel_cache)} / {len(parcel_ids)}")
    missing = sorted(set(parcel_ids) - set(parcel_cache))
    if missing:
        P(f"{len(missing)} parcel_id(s) not in Smith CAD TaxParcels: "
          f"{missing[:5]}{'...' if len(missing) > 5 else ''}")

# ---- 2b. FC ENRICHMENT — recover owner+address for foreclosure_notice rows ---
# The publicsearch.us department=FC listing exposes doc_number / recorded_date
# / sale_date / property_address only. ~2/97 records carry a real address
# (the rest read "N/A" because TX trustee notices index by party+doc, not
# address). Without a joinable signal, §17 routes these REVIEW_REQUIRED.
#
# Downstream enrichment per operator framework: for any FC record that
# carries a non-N/A property_address, reverse-lookup Smith CAD by ADDRESS
# to recover owner_name + ACCOUNT (parcel_id) + full address. This runs
# every build (CI included).
#
# Per the operator: REVIEW_REQUIRED still applies internally (§17 honest);
# the CARD displays the resolved owner. FC records that cannot join (no
# situs_address) stay REVIEW_REQUIRED — reported as a count.
fc_events = [ev for ev in raw_events
              if ev.get("canonical_doc_type") == "foreclosure_notice"]
fc_with_addr = [ev for ev in fc_events
                 if (ev.get("property_refs") or {}).get("situs_address")]
fc_addr_cache: dict = {}   # normalized_address -> CAD attrs
print(f"\n  FC foreclosure_notice records: {len(fc_events)}  "
      f"with situs_address: {len(fc_with_addr)}")
if fc_with_addr:
    # Build a CAD address-lookup query (ArcGIS supports IN on ADDRESS).
    # Normalize: uppercase, strip, collapse whitespace.
    def _norm_addr(s):
        return re.sub(r"\s+", " ", (s or "").strip().upper())
    wanted_addrs = sorted({_norm_addr(ev["property_refs"]["situs_address"])
                            for ev in fc_with_addr})
    # CAD ADDRESS values are uppercase + space-normalized; build a LIKE-OR
    # WHERE clause (chunked if many) — for 2-5 addresses, a simple IN works.
    # Quote single quotes inside addresses.
    def _q(s): return "'%s'" % s.replace("'", "''")
    where = "ADDRESS IN (%s)" % ",".join(_q(a) for a in wanted_addrs)
    params2 = urllib.parse.urlencode({
        "where": where, "outFields": "*", "returnGeometry": "false", "f": "json"})
    try:
        with urllib.request.urlopen(
            urllib.request.Request(CAD_URL + "?" + params2, headers=UA),
            timeout=45
        ) as r:
            feats = json.loads(r.read()).get("features", [])
        for f in feats:
            a = f.get("attributes") or {}
            addr_key = _norm_addr(a.get("ADDRESS"))
            if addr_key and addr_key not in fc_addr_cache:
                fc_addr_cache[addr_key] = a
        print(f"  FC address-lookup resolved: {len(fc_addr_cache)} / {len(wanted_addrs)}")
    except Exception as exc:
        P(f"FC address lookup failed ({type(exc).__name__}: {exc})")
# Per-FC-doc resolution table (lookup by instrument_number)
fc_resolution: dict = {}
for ev in fc_events:
    refs = ev.get("property_refs") or {}
    situs = refs.get("situs_address")
    if not situs:
        fc_resolution[ev["instrument_number"]] = {
            "resolved": False, "reason": "no_situs_address_on_clerk_listing",
        }
        continue
    norm = re.sub(r"\s+", " ", situs.strip().upper())
    cad = fc_addr_cache.get(norm)
    if not cad:
        fc_resolution[ev["instrument_number"]] = {
            "resolved": False, "reason": "address_not_in_smith_cad",
        }
        continue
    own1 = (cad.get("OWN1") or "").strip()
    own2 = (cad.get("OWN2") or "").strip()
    owner = own1 if not own2 else f"{own1} {own2}".strip()
    acct  = (cad.get("ACCOUNT") or "").strip()
    addr  = (cad.get("ADDRESS") or "").strip()
    city  = (cad.get("POSTAL_CITY") or "").strip()
    zipc  = str(cad.get("ZIPCODE") or "").strip()
    full  = ", ".join(p for p in (addr, city, "TX" if (addr or city) else "", zipc) if p).replace(", ,", ",")
    fc_resolution[ev["instrument_number"]] = {
        "resolved": True, "owner_name": owner or None, "parcel_id": acct or None,
        "property_full_address": full or None,
        "property_street": addr or None, "property_city": city or None,
        "property_zip": zipc or None,
        "_owner_source": "smith_cad_taxparcels_address_join",
    }
    # Also seed parcel_cache so the seam enrichment_provider picks it up
    # downstream when scoring runs against this parcel.
    if acct and acct not in parcel_cache:
        parcel_cache[acct] = cad
fc_resolved_count = sum(1 for r in fc_resolution.values() if r["resolved"])
print(f"  FC enrichment per-doc: resolved {fc_resolved_count}/{len(fc_events)}, "
      f"REVIEW_REQUIRED {len(fc_events) - fc_resolved_count}")

def enrichment_provider(parcel_id):
    cad = parcel_cache.get(parcel_id) if parcel_id else None
    if not cad: return None
    own1 = (cad.get("OWN1") or "").strip()
    own2 = (cad.get("OWN2") or "").strip()
    owner = own1 if not own2 else f"{own1} {own2}".strip()
    addr = (cad.get("ADDRESS") or "").strip()
    return {
        "parcel_id": (cad.get("ACCOUNT") or "").strip(),
        "address": addr.upper() if addr else None,
        "situs_address": addr.upper() if addr else None,
        "city": (cad.get("POSTAL_CITY") or "").strip().upper() or None,
        "situs_city": (cad.get("POSTAL_CITY") or "").strip().upper() or None,
        "situs_state": "TX",
        "situs_zip": str(cad.get("ZIPCODE") or "").strip() or None,
        "zip": str(cad.get("ZIPCODE") or "").strip() or None,
        "owner_name": owner or None,
        "year_built": int(cad.get("YRBLT")) if cad.get("YRBLT") else None,
        "acres": float(cad["Calc_Acre"]) if cad.get("Calc_Acre") is not None else None,
        "property_use": (cad.get("Type") or "").strip() or None,
        "assessed_value": None, "land_value": None, "improvement_value": None,
        "last_sale_date": None, "last_sale_price": None,
        "_enrichment_source": "smith_cad_taxparcels",
    }

# ---- 2b. Delinquent-tax enrichment cache (SFTP drop, ENRICHMENT-only) ----
# Loaded once into a {parcel_id: {balance, years_back, ...}} dict. Joins onto
# the per-lead render below via parcel_id. NEVER feeds §17 — this is roll
# status, not a recorded event document. Never originates a standalone lead.
delinq_cache: dict = {}
DELINQ_PATH = RAW / "smith_delinquent_tax.jsonl"
if DELINQ_PATH.exists():
    with DELINQ_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            pid = (r.get("parcel_id") or "").strip()
            if pid:
                delinq_cache[pid] = r
    print(f"  delinquent-tax enrichment cache: {len(delinq_cache):,} accounts "
          f"(drop_label={next(iter(delinq_cache.values()),{}).get('_drop_label','?')})")
else:
    P(f"missing enrichment file: data/raw/smith_delinquent_tax.jsonl "
      f"— delinquent-tax adapter not yet run")

# ---- 3. Staged pipeline §17->§19 + county patch + §20 + seam -------------
print("\n== §17 -> §18 -> §19 [patch] -> §20 -> seam ==")
debtor_resolved = [debtor_party_engine.resolve_debtor_party(ev) for ev in raw_events]
ledger = evidence_ledger_mod.build_evidence_ledger([])
by_source: dict = defaultdict(list)
for drr in debtor_resolved:
    by_source[drr.get("source_id") or "unknown"].append(drr)
all_base = []
base_paths = []
for sid, drrs in by_source.items():
    src_base = [leads_base_writer.build_base_record(d, signal_type_labels={},
                                                    evidence_ledger=ledger) for d in drrs]
    all_base.extend(src_base)
    base_paths.append(leads_base_writer.write_leads_base(sid, src_base, output_dir=WORKDIR))
print(f"  §17 debtor_resolved: {len(debtor_resolved)}")
print(f"  §18 leads_base:      {len(all_base)} across {len(base_paths)} source file(s)")

matched_path = WORKDIR / "matched_leads.json"
matched = aggregator.aggregate(base_paths, output_path=matched_path)
evidence_ledger_mod.write_evidence_ledger([], output_dir=WORKDIR)
print(f"  §19 matched_leads:   {len(matched)}")

# County-side patch: rewrite primary_parcel_id from raw_event lookup
ev_by_instr = {ev.get("instrument_number"): ev["property_refs"].get("parcel_id")
               for ev in raw_events if ev.get("instrument_number")}
patched = 0
for ml in matched:
    if ml.get("primary_parcel_id"):
        continue
    for sig in ml.get("signals") or []:
        for instr in sig.get("instrument_numbers") or []:
            pid = ev_by_instr.get(instr)
            if pid:
                ml["primary_parcel_id"] = pid
                patched += 1
                break
        if ml.get("primary_parcel_id"): break
matched_path.write_text(json.dumps(matched, indent=2, sort_keys=True,
                                    ensure_ascii=False) + "\n")
print(f"  primary_parcel_id patched: {patched}/{len(matched)} (F-1 workaround)")

semantic_report = semantic_verify.run_semantic_verification(
    matched, leads_base_records=all_base, evidence_ledger=ledger)
verdict = semantic_report.get("verdict")
(WORKDIR / "semantic_verify_report.json").write_text(
    json.dumps(semantic_report, indent=2, ensure_ascii=False, default=str) + "\n")
print(f"  §20 verdict:         {verdict}")
if verdict == "DEPLOY_BLOCKED":
    print("HALT — §20 DEPLOY_BLOCKED"); sys.exit(20)

scored = scoring_seam.score_matched_leads(
    matched, as_of=date(2026, 5, 25), enrichment_provider=enrichment_provider)
(WORKDIR / "scored_leads.json").write_text(
    json.dumps(scored, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
enriched = sum(1 for s in scored if s.get("enrichment_status") == "ENRICHED")
print(f"  seam scored:         {len(scored)}  ENRICHED: {enriched}")

# ---- 4. El Paso dashboard payload (multi-source) -------------------------
print("\n== el paso dashboard render (multi-source) ==")
raw_by_instr = {ev.get("instrument_number"): ev for ev in raw_events if ev.get("instrument_number")}
matched_by_lead = {m["lead_id"]: m for m in matched}

_ENTITY_RE = re.compile(
    r'\b(LLC|L\.L\.C\.|INC\b|INCORPORATED|CORP(?:ORATION)?|LP\b|LLP|LLLP|PLLC|'
    r'PA\b|LTD\b|COMPANY|CO\.|HOLDINGS|PROPERTIES|VENTURES|INVESTMENTS|'
    r'PARTNERS(?:HIP)?|GROUP|ASSOCIATES|ENTERPRISE(?:S)?|CHURCH|'
    r'SCHOOL\s+DISTRICT|\bISD\b|CITY\s+OF|COUNTY\s+OF|STATE\s+OF|TRUSTEE\s+OF)\b')
_ESTATE_RE = re.compile(r"\b(ESTATE\s+OF|ESTATE\b|EST\b|DECEASED|DEC\'?D|DCSD|HEIRS\s+OF)\b")
_TRUST_RE = re.compile(r'\bTRUST\b|\bREVOCABLE\b|\bIRREVOCABLE\b|\bLIVING\s+TRUST\b')

def classify_owner_type(name):
    if not name or not name.strip(): return "UNKNOWN"
    n = name.upper()
    if _ESTATE_RE.search(n): return "ESTATE"
    if _TRUST_RE.search(n): return "TRUST"
    if _ENTITY_RE.search(n): return "ENTITY"
    return "INDIVIDUAL"

# Display-name + signal-label dictionaries (county-side)
CANON_TO_LABEL = {
    "tax_foreclosure_notice": "Tax Foreclosure Notice",
    "sheriff_sale_surplus": "Sheriff Sale Surplus",
    "tax_deed": "Tax Deed",
    "tax_sale_certificate": "Tax Sale Certificate",
    "foreclosure_notice": "Foreclosure Notice",
    "lis_pendens": "Lis Pendens",
    "federal_tax_lien": "Federal Tax Lien",
    "state_tax_lien": "State Tax Lien",
    "probate": "Probate",
}

records = []
for s in scored:
    lead_id = s["lead_id"]
    ml = matched_by_lead.get(lead_id, {})
    parcel_id = s.get("primary_parcel_id") or ""
    enrichment_status = "ENRICHED" if s.get("enrichment_status") == "ENRICHED" else "UNENRICHED"

    # Find originating raw_event via signals[].instrument_numbers
    ev = None
    for sig in ml.get("signals") or []:
        for instr in sig.get("instrument_numbers") or []:
            if instr in raw_by_instr:
                ev = raw_by_instr[instr]; break
        if ev: break

    # ---- owner: prefer parcel_master enrichment; otherwise §17 resolved party
    # (Excess Proc DF fallback); otherwise FC address→CAD resolution. -----
    cad = parcel_cache.get(parcel_id) if parcel_id else None
    fc_res = None
    if ev and ev.get("canonical_doc_type") == "foreclosure_notice":
        fc_res = fc_resolution.get(ev.get("instrument_number"))
    if cad:
        own1 = (cad.get("OWN1") or "").strip()
        own2 = (cad.get("OWN2") or "").strip()
        owner_name = own1 if not own2 else f"{own1} {own2}".strip()
    elif fc_res and fc_res.get("resolved"):
        owner_name = fc_res.get("owner_name") or ""
    elif s.get("owner_name") and "against unidentified party" not in s["owner_name"]:
        owner_name = s["owner_name"]   # §17 resolved (DF fallback)
    else:
        owner_name = ""
    owner_type = classify_owner_type(owner_name)

    # ---- property address ----
    if cad:
        addr = (cad.get("ADDRESS") or "").strip()
        city = (cad.get("POSTAL_CITY") or "").strip()
        zip_ = str(cad.get("ZIPCODE") or "").strip()
        property_full = ", ".join(p for p in (addr, city, "TX" if (addr or city) else "", zip_) if p).strip(",  ")
        property_full = property_full.replace(", ,", ",")
    elif fc_res and fc_res.get("resolved"):
        property_full = fc_res.get("property_full_address") or ""
    elif ev:
        refs = ev.get("property_refs") or {}
        property_full = refs.get("situs_address") or ""
    else:
        property_full = ""

    # legal description: prefer raw_event's, else compose from cause
    legal = ""
    if ev and (ev.get("property_refs") or {}).get("legal_description"):
        legal = ev["property_refs"]["legal_description"]
    elif ev and ev.get("instrument_number"):
        legal = f"Smith County District Court Cause No. {ev['instrument_number']}"

    # ---- El Paso signals[] ----
    out_signals = []
    for sig in ml.get("signals") or []:
        canon = sig.get("canonical_doc_type") or "unknown"
        label = CANON_TO_LABEL.get(canon, canon.replace("_", " ").title())
        # event_date / recorded_date from originating raw_event. Some sources
        # (publicsearch FC sweep) carry the trustee sale date in event_date
        # and the actual recording date in recorded_date — split them on the
        # signal so the dashboard column "recorded_date" stays truthful.
        ev_for_sig = None
        for ii in sig.get("instrument_numbers") or []:
            ev_for_sig = raw_by_instr.get(ii) or ev_for_sig
        ev_event = (ev_for_sig or {}).get("event_date") if ev_for_sig else None
        ev_recorded = (ev_for_sig or {}).get("recorded_date") if ev_for_sig else None
        out_signals.append({
            "signal_type": canon,
            "signal_label": label,
            "signal_confidence": "HIGH",
            "source_id": (sig.get("source_ids") or ["unknown"])[0],
            "count": sig.get("count", 1),
            "source_urls": sig.get("source_urls", []),
            "evidence_ids": sig.get("evidence_ids", []),
            "instrument_numbers": sig.get("instrument_numbers", []),
            "doc_type_raw": (ev_for_sig or {}).get("raw_doc_type"),
            "recorded_date": ev_recorded or ev_event,
            "sale_date": ev_event,
        })

    signal_types = list(dict.fromkeys(sig["signal_type"] for sig in out_signals))
    source_urls = list(dict.fromkeys(u for sig in out_signals for u in sig["source_urls"]))
    latest_event = max((sig["sale_date"] for sig in out_signals if sig.get("sale_date")), default=None)

    # ---- delinquent-tax enrichment join (parcel_id only) --------------------
    # Stage-boundary preserved: this NEVER creates a lead — it only attaches
    # to a lead that already exists for this parcel_id. The lead's primary
    # `signal_types` are unchanged; delinquency surfaces as enrichment
    # attributes + a stacking flag.
    dlq = delinq_cache.get(parcel_id) if parcel_id else None
    if dlq:
        years_delinq = dlq.get("years_delinquent") or []
        years_back   = int(dlq.get("years_back") or 0)
        delinq_balance = float(dlq.get("delinquent_balance") or 0.0)
        delinq_earliest = dlq.get("earliest_year")
        delinq_latest   = dlq.get("latest_year")
    else:
        years_delinq, years_back = [], 0
        delinq_balance, delinq_earliest, delinq_latest = 0.0, None, None

    # Operator distress filter: ONLY 3+ distinct unpaid years count as a hot
    # tax-delinquency signal. 1-2 years late is "just late" and must not
    # carry strong distress weight. The flag below is the dashboard filter.
    tax_delinquent_hot = years_back >= 3

    # Stacked-lead classification. Multi-signal == this parcel carries more
    # than one primary distress signal_type, OR a primary distress AND
    # hot-delinquency enrichment. We surface the stack class for the
    # operator's lead-board (probate + tax_delinquent is the canonical
    # high-value pattern).
    primary_signal_types = list(signal_types)
    stack_signals = list(primary_signal_types)
    if tax_delinquent_hot:
        stack_signals.append("tax_delinquent_3plus")
    elif dlq:
        stack_signals.append("tax_delinquent")
    stacked = len(set(primary_signal_types)) > 1 or (tax_delinquent_hot and primary_signal_types)
    stack_class = "+".join(sorted(set(stack_signals))) if len(stack_signals) > 1 else (
        stack_signals[0] if stack_signals else "")

    records.append({
        "lead_id": lead_id,
        "parcel_resolution_status": s.get("lead_status", "REVIEW_REQUIRED"),
        "epcad_enrichment_status": enrichment_status,
        "filer_entity": ml.get("filer_entity") or "",
        "parcel_id": parcel_id,
        "owner_name": owner_name,
        "owner_type": owner_type,
        "owners": ml.get("owners", []),
        "property_full_address": property_full,
        "property_street": (cad.get("ADDRESS") or "").strip() if cad else "",
        "property_city": (cad.get("POSTAL_CITY") or "").strip() if cad else "",
        "property_state": "TX",
        "property_zip": (str(cad.get("ZIPCODE") or "").strip() if cad else ""),
        "mailing_full_address": "", "mailing_city": "", "mailing_state": "",
        "assessed_value": None, "appraised_value": None, "homestead": None,
        "absentee_owner_flag": False, "out_of_state_owner_flag": False,
        "legal_description": legal,
        "year_built": (int(cad.get("YRBLT")) if cad and cad.get("YRBLT") else None),
        "signals": out_signals, "signal_types": signal_types,
        "source_urls": source_urls,
        "signal_count": len(out_signals),
        "latest_event_date": latest_event,
        # FC enrichment status — surfaced on the card so the operator can
        # see at-a-glance whether the foreclosure resolved an owner via the
        # CAD address-join enrichment, or remains genuinely REVIEW_REQUIRED.
        "fc_owner_resolved": bool(fc_res and fc_res.get("resolved")),
        "fc_review_reason":  (fc_res or {}).get("reason"),
        # delinquent-tax enrichment (stacking signal — never a primary lead)
        "tax_delinquent": bool(dlq),
        "tax_delinquent_hot": tax_delinquent_hot,   # years_back >= 3
        "tax_delinquent_balance": round(delinq_balance, 2),
        "tax_delinquent_years": years_delinq,
        "tax_delinquent_years_back": years_back,
        "tax_delinquent_earliest_year": delinq_earliest,
        "tax_delinquent_latest_year":   delinq_latest,
        # stacking
        "stacked_lead": bool(stacked),
        "stack_class": stack_class,
        "stack_signals": sorted(set(stack_signals)),
        # provenance — every row in the dashboard declares how it came to be
        "provenance": "primary_event",
    })


# ---- TAX-DEFAULT QUALIFICATION AUDIT (operator framework correction) --------
# The earlier pass converted all 37,796 SFTP delinquent rows into untagged
# "synth" leads with no qualification. That was wrong. The current rule:
# OFFICIAL TAX-DEFAULT RECORDS originate leads when they prove default;
# unqualified tax-roll data stays enrichment. We classify every non-primary
# account against five criteria and tag it into a six-class matrix.
#
# Source authority (criterion 1) is OFFICIALLY-AUTHORIZED:
#   The Smith County Tax Office (smith-county.com/357 — Property Tax FAQs)
#   states: "We have retained the law firm of Linebarger, Goggan, Blair and
#   Sampson, LLP to assist in resolving delinquent accounts."
#   smith-county.com/358 (Delinquent Tax Sales) lists LGBS as the tax
#   attorney representing Smith County. mft.smi.tax is the LGBS Managed File
#   Transfer host that delivers the same firm's authoritative delinquent
#   receivables (MR) + master accounts (MM) on a weekly cadence. That makes
#   the TaxRoll_Smith_Flat_V1 drop the operational source of record for
#   Smith County delinquent-tax status — officially authorized under
#   criterion 1.
#
# Aggregation is at the account level. The MR file is account × year × unit
# line items; we aggregate to ONE record per account carrying years_delinquent
# (multi-year list) + total outstanding balance — one tax_default lead per
# delinquent account, never one per year or per tax-unit.
primary_parcels = {r["parcel_id"] for r in records if r.get("parcel_id")}
synth_records: list = []
audit_counts: dict = defaultdict(int)
drop_label = next((r.get("_drop_label") for r in delinq_cache.values()
                    if r.get("_drop_label")), None)
# Drop label → date (e.g. TaxRoll_Smith_Flat_V1_2026_05_23 → 2026-05-23)
drop_iso = None
if drop_label:
    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", drop_label)
    if m: drop_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
# Synthetic per-account source URL — encodes provenance to the official
# drop. SFTP isn't browser-clickable, but it's the auditable record-of-fetch.
SOURCE_URL_BASE = ("sftp://mft.smi.tax/Smith/"
                   + (drop_label + ".zip" if drop_label else "latest.zip"))
LGBS_TAX_SALES_URL_BASE = ("https://taxsales.lgbs.com/map?lat=32.35&lon=-95.30"
                          "&county=smith&state=TX#account=")


def qualify_tax_default(dlq: dict, owner_name: str) -> tuple[str, str, str]:
    """Apply the five-criteria gate. Return (class, signal_type, signal_label).

    Criteria:
      1. SOURCE: official/authorized (always True here — LGBS/mft.smi.tax).
      2. RECORD: real default condition (open balance > 0, year(s) present).
      3. RECORD ties to real property (account_nbr always present).
      4. RECORD has source proof (drop_label, captured_at, source URL).
      5. NOT mere parcel enrichment (the record is a TAX ACCOUNT WITH
         OFFICIAL DELINQUENT STATUS, not generic owner / value / GIS data).
    """
    bal = float(dlq.get("delinquent_balance") or 0.0)
    yrs = int(dlq.get("years_back") or 0)
    has_owner = bool(owner_name and owner_name.strip())
    # Criterion 2: real default — open balance AND at least one delinquent year
    if bal <= 0 or yrs <= 0:
        return ("TAX_ROLL_ENRICHMENT_ONLY", None, None)
    # Criterion 3: must tie to property — account_nbr is REQUIRED (always true
    # for entries in this cache; defensive guard for malformed input)
    if not dlq.get("parcel_id"):
        return ("REVIEW_REQUIRED", "tax_default", "Tax Default — review")
    # Criterion 5 / owner-of-record proof: an account with delinquency but
    # NO owner name on the master record cannot surface as a lead — the
    # debtor is unidentified.
    if not has_owner:
        return ("REVIEW_REQUIRED", "tax_default", "Tax Default — review")
    # Low-priority bucket: just-late + nominal balance is not strong distress.
    # Threshold: 1 year AND under $100 outstanding (operator: 1-yr late is
    # "just late", not real distress).
    if yrs == 1 and bal < 100.0:
        return ("TAX_DEFAULT_LOW_PRIORITY", "tax_default_low_priority",
                f"Tax Default (Low Priority) — {yrs}yr / ${bal:.2f}")
    return ("QUALIFIED_TAX_DEFAULT_LEAD", "tax_default",
            f"Tax Default — {yrs}yr / ${bal:,.2f}")


for pid, dlq in delinq_cache.items():
    if pid in primary_parcels:
        # Already attached as enrichment to a primary lead — don't
        # double-count. Audit count tracked separately.
        audit_counts["STACKED_WITH_PRIMARY"] += 1
        continue
    is_estate = bool(dlq.get("estate_titled"))
    owner = (dlq.get("owner_name") or "").strip() or None

    if is_estate:
        # Estate-titled is a SEPARATE operator framework decision. These
        # surface as standalone probate leads regardless of the
        # tax-default qualification matrix (the estate title in the owner
        # field IS the distress fact). They never demote to enrichment.
        qualification = "ESTATE_TITLED_LEAD"
        signal_type   = "probate"
        signal_label  = "Probate (Estate-Titled Tax Delinquent)"
    else:
        qualification, signal_type, signal_label = qualify_tax_default(dlq, owner)

    audit_counts[qualification] += 1
    # Demote to enrichment-only: do not emit a dashboard row.
    if qualification == "TAX_ROLL_ENRICHMENT_ONLY":
        continue
    # REVIEW_REQUIRED rows still surface so the operator can triage them,
    # but flagged so they don't crowd the active board by default.

    years_back = int(dlq.get("years_back") or 0)
    bal = float(dlq.get("delinquent_balance") or 0.0)
    ot = "ESTATE" if is_estate else classify_owner_type(owner or "")
    cad = parcel_cache.get(pid)
    addr = ""
    if cad:
        a = (cad.get("ADDRESS") or "").strip()
        c = (cad.get("POSTAL_CITY") or "").strip()
        z = str(cad.get("ZIPCODE") or "").strip()
        addr = ", ".join(p for p in (a, c, "TX" if (a or c) else "", z) if p).replace(", ,", ",")
    mailing = ", ".join(p for p in (
        dlq.get("owner_street"), dlq.get("owner_city"),
        dlq.get("owner_state"), dlq.get("owner_zip")) if p
    ) if not cad else ""

    stack_signals_s = [signal_type]
    if years_back >= 3 and not is_estate and qualification == "QUALIFIED_TAX_DEFAULT_LEAD":
        stack_signals_s.append("tax_default_3plus")
    stack_class_s = "+".join(sorted(set(stack_signals_s)))

    # Per-record signal — SLIM. The criterion-4 source-proof boilerplate
    # (source_name, source_url base, drop_label, captured_at) is identical
    # across all 37K synth rows; we move it to payload-level
    # `tax_default_source_meta` and reconstruct per-row URLs client-side from
    # parcel_id. This drops ~700 bytes/row × 37K = ~26 MB off data.js so it
    # fits in the git tree the live Pages site serves.
    synth = {
        "lead_id": (f"lead_probate_{pid}" if is_estate
                     else f"lead_taxdefault_{pid}"),
        "parcel_id": pid,
        "owner_name": owner or "",
        "owner_type": ot,
        "signal_types": [signal_type] if signal_type else [],
        "signals": ([{
            "signal_type": signal_type,
            "signal_label": signal_label,
            "source_id": "smith_delinquent_tax_sftp_lgbs",
        }] if signal_type else []),
        "signal_count": 1 if signal_type else 0,
        "latest_event_date": drop_iso,
        "parcel_resolution_status": ("REVIEW_REQUIRED"
                                      if qualification == "REVIEW_REQUIRED"
                                      else "APPROVED_FOR_DASHBOARD"),
        "epcad_enrichment_status": "ENRICHED" if cad else "UNENRICHED",
        "tax_delinquent": True,
        "tax_delinquent_hot": years_back >= 3,
        "tax_delinquent_balance": round(bal, 2),
        "tax_delinquent_years_back": years_back,
        "estate_titled": is_estate,
        "stacked_lead": False,
        "stack_class": stack_class_s,
        "qualification_class": qualification,
        "provenance": ("estate_titled_delinquency" if is_estate
                       else "tax_default_source_of_record"),
    }
    # Life-estate flag — informational only, NOT a probate signal. Living
    # life-tenants (e.g. "PASCHE J MARK LIFE ESTATE") are dropped from the
    # probate class but kept here so the operator can see the
    # estate-planning context.
    if dlq.get("life_estate"):
        synth["life_estate"] = True
    # Optional fields — emit only when non-empty (saves ~80 B/row when blank)
    if addr:    synth["property_full_address"] = addr
    if mailing: synth["mailing_full_address"]  = mailing
    if dlq.get("earliest_year"):
        synth["tax_delinquent_earliest_year"] = dlq.get("earliest_year")
    if dlq.get("latest_year"):
        synth["tax_delinquent_latest_year"]   = dlq.get("latest_year")
    if len(stack_signals_s) > 1:
        synth["stack_signals"] = sorted(set(stack_signals_s))
    synth_records.append(synth)

# ---- Dedupe ESTATE leads by owner_name (operator framework correction) -----
# A single decedent estate can own many parcels in Smith County (e.g. JONES
# MINNIE JARVIS ESTATE × 28 parcels). The operator-facing lead is the ESTATE
# itself — contacting the executor once handles all properties. Collapse
# every (owner_name) cluster of probate-tagged synth rows into ONE row, list
# the parcels in `linked_parcels`, sum the balance, take the worst
# years_back / earliest_year. Non-estate tax_default leads are NOT deduped
# (each parcel is a distinct opportunity).
def _norm_owner(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())

estate_rows  = [r for r in synth_records
                 if r["provenance"] == "estate_titled_delinquency"]
nonestate    = [r for r in synth_records
                 if r["provenance"] != "estate_titled_delinquency"]
n_before_dedup = len(estate_rows)
estate_groups: dict = defaultdict(list)
for r in estate_rows:
    estate_groups[_norm_owner(r.get("owner_name", ""))].append(r)
collapsed_estate: list = []
for owner_key, group in estate_groups.items():
    if len(group) == 1:
        r = group[0]
        r["linked_parcels"] = [r["parcel_id"]]
        r["estate_parcel_count"] = 1
        collapsed_estate.append(r)
        continue
    # Aggregate: pick the parcel with the largest balance as primary; carry
    # the rest as linked. Sum balance, max years_back, min(earliest_year),
    # max(latest_year). Property address / mailing come from the primary.
    primary = max(group, key=lambda r: r.get("tax_delinquent_balance") or 0)
    total_bal = round(sum(r.get("tax_delinquent_balance") or 0 for r in group), 2)
    max_yrs   = max(r.get("tax_delinquent_years_back") or 0 for r in group)
    earliest  = min((r.get("tax_delinquent_earliest_year")
                     for r in group if r.get("tax_delinquent_earliest_year")),
                    default=None)
    latest    = max((r.get("tax_delinquent_latest_year")
                     for r in group if r.get("tax_delinquent_latest_year")),
                    default=None)
    parcels   = sorted({r["parcel_id"] for r in group})
    merged = dict(primary)
    merged["lead_id"] = f"lead_probate_estate_{primary['parcel_id']}"
    merged["tax_delinquent_balance"] = total_bal
    merged["tax_delinquent_years_back"] = max_yrs
    merged["tax_delinquent_hot"] = max_yrs >= 3
    if earliest is not None: merged["tax_delinquent_earliest_year"] = earliest
    if latest   is not None: merged["tax_delinquent_latest_year"]   = latest
    merged["linked_parcels"] = parcels
    merged["estate_parcel_count"] = len(parcels)
    # Adjust the signal label to reflect the aggregate
    merged["signals"] = [{
        "signal_type": "probate",
        "signal_label": (f"Probate (Estate-Titled Tax Delinquent) — "
                          f"{len(parcels)} parcels, ${total_bal:,.2f} total, "
                          f"{max_yrs}yr"),
        "source_id": "smith_delinquent_tax_sftp_lgbs",
    }]
    collapsed_estate.append(merged)
synth_records = nonestate + collapsed_estate
n_after_dedup = len(collapsed_estate)
print(f"  estate dedupe: {n_before_dedup:,} rows  ->  "
      f"{n_after_dedup:,} unique estates  "
      f"({n_before_dedup - n_after_dedup:,} multi-parcel rows collapsed)")

# Annotate every PRIMARY lead with its tax-default qualification subtype.
# The §17 canonical_doc_type is preserved as-is (no scaffold edits); we add
# `qualification_class` as the operator-facing audit-classification overlay.
#
# Rules:
#   - LGBS tax_foreclosure_notice with future sale_date     → TAX_SALE_LEAD
#   - LGBS / PBFCM tax_foreclosure_notice (STRUCK OFF / no sale_date)
#                                                            → TAX_FORECLOSURE_LEAD
#   - Sheriff sale surplus / clerk-recorded distress events  → PRIMARY_EVENT_LEAD
def _primary_qualification(r):
    types = set(r.get("signal_types") or [])
    if "tax_foreclosure_notice" in types:
        # Has an upcoming sale date? Then it's an active TAX_SALE_LEAD.
        for sig in r.get("signals") or []:
            sd = sig.get("sale_date")
            if sd and sig.get("signal_type") == "tax_foreclosure_notice":
                # crude future-date check: ISO YYYY-MM-DD strings sort lexically
                if sd >= TODAY.isoformat():
                    return "TAX_SALE_LEAD"
        return "TAX_FORECLOSURE_LEAD"
    return "PRIMARY_EVENT_LEAD"

for r in records:
    pid = r.get("parcel_id")
    dlq_e = delinq_cache.get(pid) if pid else None
    r["estate_titled"] = bool(dlq_e and dlq_e.get("estate_titled"))
    r["qualification_class"] = _primary_qualification(r)
    if r["estate_titled"] and r["stacked_lead"]:
        # Surface the canonical probate+tax_default stack class explicitly
        r["stack_class"] = "probate+" + r["stack_class"]
        r["stack_signals"] = sorted(set(["probate", *r["stack_signals"]]))

# Recency tagging — primary-event leads only. The operator's spec keys off
# the county's recorded date, NOT the scrape date. Synthesized delinquency
# leads carry the SFTP drop date as their `latest_event_date` for
# rendering purposes, but that is a refresh artifact — it is not a real
# recording date, so it MUST NOT trigger NEW / last-30-days tags.
def _parse_iso_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except (TypeError, ValueError):
        return None

for r in records + synth_records:
    if r["provenance"] != "primary_event":
        r["is_new"] = False
        r["is_last_30_days"] = False
        r["recency_age_days"] = None
        r["is_upcoming_sale_30d"] = False
        r["sale_status"] = None
        continue
    # Recency tag — keyed off the COUNTY RECORDED date (backward-looking).
    # For most primary leads (lis_pendens, AOJ, sheriff surplus,
    # tax_foreclosure_notice) this is the same as latest_event_date. For
    # FC sweep foreclosure_notice rows we set event_date = sale_date and
    # recorded_date = the actual filing date; pull the recorded date off
    # the originating raw_event for those rows so the "last 30 days" badge
    # only fires on RECENTLY FILED records, not on past sale dates.
    primary_sig = (r.get("signals") or [{}])[0]
    rec_iso = primary_sig.get("recorded_date") or r.get("latest_event_date")
    d_filed = _parse_iso_date(rec_iso)
    r["is_new"]          = bool(d_filed and d_filed == TODAY)
    r["is_last_30_days"] = bool(d_filed and 0 <= (TODAY - d_filed).days <= 30)
    r["recency_age_days"] = (TODAY - d_filed).days if d_filed else None
    # Sale-window tag — distinct from recency. Fires ONLY for foreclosure-
    # type leads with an UPCOMING sale date in the next 30 days; never for
    # past sales (which carry "(past)" in the chip). The dashboard
    # ≤30d badge keys on this for foreclosure rows.
    sale_iso = primary_sig.get("sale_date")
    d_sale = _parse_iso_date(sale_iso)
    if d_sale:
        days_to_sale = (d_sale - TODAY).days
        if days_to_sale < 0:
            r["sale_status"] = "past"
            r["is_upcoming_sale_30d"] = False
        elif days_to_sale == 0:
            r["sale_status"] = "today"
            r["is_upcoming_sale_30d"] = True
        elif days_to_sale <= 30:
            r["sale_status"] = "upcoming_30d"
            r["is_upcoming_sale_30d"] = True
        else:
            r["sale_status"] = "upcoming_later"
            r["is_upcoming_sale_30d"] = False
    else:
        r["sale_status"] = None
        r["is_upcoming_sale_30d"] = False

records.extend(synth_records)
print(f"\n  synthesized standalone leads from delinquency: {len(synth_records):,}")
print(f"    of which estate-titled (probate): "
      f"{sum(1 for r in synth_records if r.get('estate_titled')):,}")
print(f"    of which non-estate tax_delinquent: "
      f"{sum(1 for r in synth_records if not r.get('estate_titled')):,}")
print(f"  primary leads with estate-titled tax owner: "
      f"{sum(1 for r in records if r['provenance']=='primary_event' and r['estate_titled']):,}")

cfg = json.load(open(REPO / "config" / "counties" / "smith_tx.json"))
review_required = sum(1 for r in records if r["parcel_resolution_status"] == "REVIEW_REQUIRED")

# Qualification-class rollups (operator audit). Counted across the final
# `records` array (primary + estate-titled probate + qualified tax-default).
qual_counts = Counter(r.get("qualification_class") for r in records)
# Specific subtype counts the operator wants in the report
n_qualified_tax_default = qual_counts.get("QUALIFIED_TAX_DEFAULT_LEAD", 0)
n_tax_foreclosure       = qual_counts.get("TAX_FORECLOSURE_LEAD", 0)
n_tax_sale              = qual_counts.get("TAX_SALE_LEAD", 0)
n_tax_default_lowpri    = qual_counts.get("TAX_DEFAULT_LOW_PRIORITY", 0)
n_estate_titled         = qual_counts.get("ESTATE_TITLED_LEAD", 0)
n_primary_event_other   = qual_counts.get("PRIMARY_EVENT_LEAD", 0)
n_review_required_q     = qual_counts.get("REVIEW_REQUIRED", 0)
n_enrichment_excluded   = audit_counts.get("TAX_ROLL_ENRICHMENT_ONLY", 0)
n_stacked_with_primary  = audit_counts.get("STACKED_WITH_PRIMARY", 0)

# Provenance + recency + delinquency rollups for the dashboard summary band.
primary_count   = sum(1 for r in records if r["provenance"] == "primary_event")
estate_synth    = sum(1 for r in records if r["provenance"] == "estate_titled_delinquency")
default_synth   = sum(1 for r in records if r["provenance"] == "tax_default_source_of_record")
tax_delinquent_attached  = sum(1 for r in records if r["tax_delinquent"])
tax_delinquent_hot_count = sum(1 for r in records if r["tax_delinquent_hot"])
stacked_count            = sum(1 for r in records if r["stacked_lead"])
stack_class_counter      = Counter(r["stack_class"] for r in records if r["stack_class"])
new_count                = sum(1 for r in records if r["is_new"])
last_30_count            = sum(1 for r in records if r["is_last_30_days"])
years_back_hist          = Counter(min(r["tax_delinquent_years_back"], 5)
                                    for r in records if r["tax_delinquent"])

# ----- §20 framework punch-list recommendation -----
# Current behavior: §20 (scaffold/pipeline/semantic_verify.py) runs Check 4
# "Enrichment status decoupling integrity" against the §19 matched_leads
# array — which holds ONLY events that passed §17. Tax-default rows from
# the LGBS / mft.smi.tax drop never reach §17 (no recorded-event party
# tuples), so they are invisible to §20. The §20 verdict (DEPLOY_OK or
# DEPLOY_BLOCKED) is therefore a statement about CLERK-RECORDED primary
# leads only — it neither approves nor rejects tax-default source-of-record
# leads.
#
# This means §20 today does NOT correctly express the operator's rule:
# "Tax-default source-of-record rows must be allowed as primary leads when
# they meet official default criteria, while unqualified tax-roll
# enrichment must be blocked." It is silent on the question — the
# qualification audit runs entirely county-side, post-§20.
#
# Punch-list item (framework-level, v5.5+):
SECTION_20_PUNCH = {
    "id": "F-S20-TAXDEFAULT-1",
    "severity": "MAJOR",
    "framework_section": "§20 semantic_verify Check 4 + §16 source-of-record matrix",
    "title": ("Tax-default source-of-record rows must originate primary "
              "leads when they meet official default criteria; unqualified "
              "tax-roll enrichment must be blocked."),
    "current_behavior": ("§20 sees only §17-routed clerk-recorded events. "
                          "Officially-authorized tax-default sources (e.g. "
                          "the county's retained delinquent-tax firm's MFT "
                          "drop) never reach §17 and are invisible to §20. "
                          "The verdict therefore validates nothing about "
                          "tax-default leads."),
    "required_behavior": (
        "Add a `tax_default` canonical_doc_type to the §17 registry with "
        "rule expected_debtor_name_type=TP (taxpayer), "
        "missing_debtor_review_reason=owner_not_on_document. Add "
        "`tax_default_source` as a §16 source role distinct from "
        "PRIMARY_EVENT_SOURCE and ENRICHMENT_SOURCE — it can originate "
        "leads, but §20 must verify each row carries (a) an "
        "officially-authorized source, (b) real default status, (c) "
        "property tie, (d) source proof, (e) is not generic roll data. "
        "§20 should pass qualified tax-default rows and DEPLOY_BLOCK "
        "unqualified ones (e.g. balance==0 without context)."),
    "county_side_workaround_active": True,
    "workaround_location": "runs/smith_tx/build/run_all_sources.py qualify_tax_default()",
}
(WORKDIR / "framework_punch_list.json").write_text(
    json.dumps([SECTION_20_PUNCH], indent=2, ensure_ascii=False) + "\n")

payload = {
    "generated_at": NOW, "county": "Smith", "state": "TX",
    "refresh_date": TODAY.isoformat(),
    "build_label": cfg["dashboard"].get("build_label") or "PARTIAL_BUILD",
    "build_label_reason": cfg["dashboard"].get("build_label_reason") or "",
    # Tax-default source-of-record metadata. Per-row URLs reconstruct from
    # parcel_id + these bases (saves ~26 MB across 37K synth rows).
    "tax_default_source_meta": {
        "source_id": "smith_delinquent_tax_sftp_lgbs",
        "source_name": ("Linebarger Goggan Blair & Sampson LLP "
                        "(Smith County retained delinquent-tax firm) — "
                        "MFT TaxRoll drop"),
        "source_url_base": SOURCE_URL_BASE,             # sftp://mft.smi.tax/...
        "secondary_source_url_base": LGBS_TAX_SALES_URL_BASE,
        "record_id_prefix": (drop_label or "latest") + "::",
        "drop_label": drop_label,
        "drop_date": drop_iso,
        "captured_at": next((r.get("_captured_at") for r in delinq_cache.values()
                              if r.get("_captured_at")), None),
    },
    "sources_active": list(per_source.keys()),
    "enrichment_sources_active": [
        "smith_cad_taxparcels",
        *(["smith_delinquent_tax_sftp_lgbs"] if delinq_cache else []),
    ],
    "tax_default_source_active": bool(delinq_cache),
    "tax_default_source_authority": (
        "Linebarger Goggan Blair & Sampson LLP (LGBS) — Smith County's "
        "officially-retained delinquent-tax collection firm, per "
        "smith-county.com/357 (Property Tax FAQs) and smith-county.com/358 "
        "(Delinquent Tax Sales). mft.smi.tax is the firm's Managed File "
        "Transfer delivery channel for the TaxRoll_<jurisdiction>_Flat_V1 "
        "data set."),
    "delinquent_tax_drop_label": drop_label,
    "delinquent_tax_drop_date": drop_iso,
    "delinquent_tax_universe": len(delinq_cache),
    "lead_total": len(records),
    # The dashboard hides TAX_DEFAULT_LOW_PRIORITY by default (1yr + <$100,
    # operator noise). default_view_lead_count is the count the client sees
    # on first load; lead_total is the full universe available via the
    # "Show low-priority" toggle in the sidebar.
    "default_view_lead_count": len(records) - n_tax_default_lowpri,
    "qualification_class_distribution": dict(qual_counts),
    "qualified_tax_default_lead_count": n_qualified_tax_default,
    "tax_foreclosure_lead_count":       n_tax_foreclosure,
    "tax_sale_lead_count":              n_tax_sale,
    "tax_default_low_priority_count":   n_tax_default_lowpri,
    "estate_titled_lead_count":         n_estate_titled,
    "primary_event_other_lead_count":   n_primary_event_other,
    "review_required_lead_count":       n_review_required_q,
    "enrichment_only_excluded_count":   n_enrichment_excluded,
    "stacked_with_primary_count":       n_stacked_with_primary,
    "primary_lead_count": primary_count,
    "tax_default_originated_lead_count": default_synth,
    "epcad_enrichment_resolved": sum(1 for r in records if r["epcad_enrichment_status"] == "ENRICHED"),
    "epcad_enrichment_unresolved": sum(1 for r in records if r["epcad_enrichment_status"] == "UNENRICHED"),
    "tax_delinquent_attached": tax_delinquent_attached,
    "tax_delinquent_hot_count": tax_delinquent_hot_count,
    "stacked_lead_count": stacked_count,
    "stack_class_distribution": dict(stack_class_counter),
    "years_back_distribution":  {str(k): v for k, v in sorted(years_back_hist.items())},
    "new_lead_count": new_count,
    "last_30_days_count": last_30_count,
    "review_required": review_required,
    "actionable_leads": len(records),
    "framework_punch_list": [SECTION_20_PUNCH],
    "records": records,
}
_compact = (",", ":")
(DASH / "data.json").write_text(json.dumps(payload, separators=_compact, ensure_ascii=False) + "\n")
(DASH / "data.js").write_text("window.LEADS=" + json.dumps(payload, separators=_compact, ensure_ascii=False) + ";\n")
print(f"  dashboard data.json + data.js written")
print(f"  default-view lead count: {payload['default_view_lead_count']:,}  "
      f"(low-priority hidden: {n_tax_default_lowpri:,})")
print(f"  lead_total (incl. low-priority): {payload['lead_total']:,}  "
      f"primary: {primary_count}  estate: {estate_synth}  "
      f"tax-default-originated: {default_synth}")
print(f"  qualification matrix:")
for k in ("QUALIFIED_TAX_DEFAULT_LEAD", "TAX_FORECLOSURE_LEAD", "TAX_SALE_LEAD",
          "TAX_DEFAULT_LOW_PRIORITY", "ESTATE_TITLED_LEAD",
          "PRIMARY_EVENT_LEAD", "REVIEW_REQUIRED"):
    if qual_counts.get(k):
        print(f"    {k:<30} {qual_counts[k]:>6,}")
print(f"  audit-only buckets:")
print(f"    TAX_ROLL_ENRICHMENT_ONLY (excluded): {n_enrichment_excluded:,}")
print(f"    STACKED_WITH_PRIMARY (attached, not duplicated): {n_stacked_with_primary:,}")
print(f"  signal_types: {dict(Counter(t for r in records for t in r['signal_types']))}")
print(f"  owner_type:   {dict(Counter(r['owner_type'] for r in records))}")
print(f"  tax_delinquent attached: {tax_delinquent_attached}  "
      f"(3+ years HOT: {tax_delinquent_hot_count})")
print(f"  stacked leads:           {stacked_count}")
print(f"  stack_class top:         "
      f"{dict(stack_class_counter.most_common(6))}")
print(f"  years_back histogram:    "
      f"{dict(sorted(years_back_hist.items()))}")
print(f"  NEW (recorded=today):    {new_count}")
print(f"  last 30 days:            {last_30_count}")

# punch_list
(WORKDIR / "punch_list.json").write_text(json.dumps({
    "generated_at": NOW, "framework_version": "v5.4.0", "county": "smith_tx",
    "semantic_verdict": verdict, "lead_total": len(records),
    "review_required_count": review_required,
    "per_source": per_source, "items": punch,
}, indent=2, ensure_ascii=False) + "\n")

print(f"\n===== SUMMARY =====")
print(f"§20: {verdict}  total: {len(records)}  ENRICHED: {payload['epcad_enrichment_resolved']}")
print(f"punch-list: {len(punch)} items")
