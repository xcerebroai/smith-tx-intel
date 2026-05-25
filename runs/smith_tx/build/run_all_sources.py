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
SOURCES = ["lgbs_smith_tax_sales", "pbfcm_smith_tax_resale", "county_excess_proceeds", "publicsearch_clerk"]
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

    # ---- owner: prefer parcel_master enrichment; otherwise §17 resolved party (Excess Proc DF fallback) ----
    cad = parcel_cache.get(parcel_id) if parcel_id else None
    if cad:
        own1 = (cad.get("OWN1") or "").strip()
        own2 = (cad.get("OWN2") or "").strip()
        owner_name = own1 if not own2 else f"{own1} {own2}".strip()
    elif s.get("owner_name") and "against unidentified party" not in s["owner_name"]:
        owner_name = s["owner_name"]   # §17 resolved (DF fallback) — Excess Proceeds path
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


# ---- Synthesize STANDALONE delinquency leads (operator framework decision) ---
# Per the operator framework call: every delinquent account on the SFTP drop
# surfaces as a dashboard row. Estate-titled owners ORIGINATE as probate-
# tagged standalone leads (the estate title in the owner-name field is the
# distress fact). Non-estate delinquent accounts surface as tax_delinquent
# standalone leads, gated client-side by the years_back filter (1/2/3/4/5+).
#
# STAGE BOUNDARY HOLDS: these rows are NOT primary §19 leads. They never
# entered §17 / §18 / §19 / §20 — the §20 verdict above still ran on the
# primary set only. Each row below carries `provenance` distinct from
# "primary_event" so a downstream consumer can filter them. The framework's
# DEPLOY_OK verdict remains a statement about primary leads.
#
# Parcels ALREADY covered by a primary lead are skipped — their delinquency
# enrichment has already attached above (stacked_lead flow).
primary_parcels = {r["parcel_id"] for r in records if r.get("parcel_id")}
synth_records: list = []
drop_label = next((r.get("_drop_label") for r in delinq_cache.values()
                    if r.get("_drop_label")), None)
# Drop label → date (e.g. TaxRoll_Smith_Flat_V1_2026_05_23 → 2026-05-23)
drop_iso = None
if drop_label:
    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", drop_label)
    if m: drop_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

for pid, dlq in delinq_cache.items():
    if pid in primary_parcels:
        continue   # already attached to a primary lead — don't double-count
    years_back = int(dlq.get("years_back") or 0)
    is_estate = bool(dlq.get("estate_titled"))
    owner = (dlq.get("owner_name") or "").strip() or None

    # Owner-type classification (same engine as primary leads)
    if is_estate:
        ot = "ESTATE"
    else:
        ot = classify_owner_type(owner or "")

    # CAD enrichment opportunistic (most delinquent accounts are NOT in our
    # parcel_cache because we only pre-fetched parcels that primary leads
    # carry — pulling CAD for 39K rows on every run would be a 30-second
    # hot path; deferred).
    cad = parcel_cache.get(pid)
    addr = ""
    if cad:
        a = (cad.get("ADDRESS") or "").strip()
        c = (cad.get("POSTAL_CITY") or "").strip()
        z = str(cad.get("ZIPCODE") or "").strip()
        addr = ", ".join(p for p in (a, c, "TX" if (a or c) else "", z) if p).replace(", ,", ",")
    elif dlq.get("owner_street") or dlq.get("owner_city"):
        # MM owner mailing address — note this is OWNER mailing, not SITUS
        # (the property address); we surface it but tag the difference.
        addr = ""    # leave property_full_address blank; mailing surfaced below

    canon = "probate" if is_estate else "tax_delinquent"
    label = "Probate (Estate-Titled Tax Delinquent)" if is_estate else "Tax Delinquent"
    stack_signals_s = [canon]
    if years_back >= 3 and not is_estate:
        stack_signals_s.append("tax_delinquent_3plus")
    stack_class_s = "+".join(sorted(set(stack_signals_s)))
    mailing = ", ".join(p for p in (
        dlq.get("owner_street"), dlq.get("owner_city"),
        dlq.get("owner_state"), dlq.get("owner_zip")) if p
    ) if not cad else ""
    # Compact synth record — only the fields the dashboard renderer uses.
    # 37K full primary-shaped records would balloon data.json past Pages
    # limits; the dashboard's prep() handles missing fields gracefully.
    synth = {
        "lead_id": f"lead_delinquent_{pid}",
        "parcel_id": pid,
        "owner_name": owner or "",
        "owner_type": ot,
        "property_full_address": addr,
        "mailing_full_address": mailing,
        "signal_types": [canon],
        "signals": [{
            "signal_type": canon,
            "signal_label": label,
            "source_id": "smith_delinquent_tax_sftp",
            "recorded_date": drop_iso,
        }],
        "signal_count": 1,
        "latest_event_date": drop_iso,
        "parcel_resolution_status": "APPROVED_FOR_DASHBOARD",
        "epcad_enrichment_status": "ENRICHED" if cad else "UNENRICHED",
        "tax_delinquent": True,
        "tax_delinquent_hot": years_back >= 3,
        "tax_delinquent_balance": float(dlq.get("delinquent_balance") or 0.0),
        "tax_delinquent_years_back": years_back,
        "tax_delinquent_earliest_year": dlq.get("earliest_year"),
        "tax_delinquent_latest_year":   dlq.get("latest_year"),
        "estate_titled": is_estate,
        "stacked_lead": False,
        "stack_class": stack_class_s,
        "stack_signals": sorted(set(stack_signals_s)),
        "provenance": ("estate_titled_delinquency" if is_estate
                       else "tax_roll_delinquency_only"),
    }
    synth_records.append(synth)

# Mark estate-titled status on existing primary leads too (so the stacking
# probate + tax_delinquent_3plus class can be detected when the operator's
# probate-detect criterion holds on the delinquency owner name).
for r in records:
    pid = r.get("parcel_id")
    dlq_e = delinq_cache.get(pid) if pid else None
    r["estate_titled"] = bool(dlq_e and dlq_e.get("estate_titled"))
    if r["estate_titled"] and r["stacked_lead"]:
        # Surface the canonical probate+tax_delinquent stack class explicitly
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
        continue
    d = _parse_iso_date(r.get("latest_event_date"))
    r["is_new"] = bool(d and d == TODAY)
    r["is_last_30_days"] = bool(d and 0 <= (TODAY - d).days <= 30)
    r["recency_age_days"] = (TODAY - d).days if d else None

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

# Provenance + recency + delinquency rollups for the dashboard summary band.
primary_count   = sum(1 for r in records if r["provenance"] == "primary_event")
estate_synth    = sum(1 for r in records if r["provenance"] == "estate_titled_delinquency")
delinq_synth    = sum(1 for r in records if r["provenance"] == "tax_roll_delinquency_only")
tax_delinquent_attached  = sum(1 for r in records if r["tax_delinquent"])
tax_delinquent_hot_count = sum(1 for r in records if r["tax_delinquent_hot"])
stacked_count            = sum(1 for r in records if r["stacked_lead"])
stack_class_counter      = Counter(r["stack_class"] for r in records if r["stack_class"])
new_count                = sum(1 for r in records if r["is_new"])
last_30_count            = sum(1 for r in records if r["is_last_30_days"])
years_back_hist          = Counter(min(r["tax_delinquent_years_back"], 5)
                                    for r in records if r["tax_delinquent"])

payload = {
    "generated_at": NOW, "county": "Smith", "state": "TX",
    "refresh_date": TODAY.isoformat(),
    "build_label": cfg["dashboard"].get("build_label") or "PARTIAL_BUILD",
    "build_label_reason": cfg["dashboard"].get("build_label_reason") or "",
    "sources_active": list(per_source.keys()),
    "enrichment_sources_active": [
        "smith_cad_taxparcels",
        *(["smith_delinquent_tax_sftp"] if delinq_cache else []),
    ],
    "delinquent_tax_drop_label": drop_label,
    "delinquent_tax_drop_date": drop_iso,
    "delinquent_tax_universe": len(delinq_cache),
    "lead_total": len(records),
    "primary_lead_count": primary_count,
    "estate_titled_lead_count": estate_synth,
    "tax_delinquent_only_lead_count": delinq_synth,
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
    "records": records,
}
_compact = (",", ":")
(DASH / "data.json").write_text(json.dumps(payload, separators=_compact, ensure_ascii=False) + "\n")
(DASH / "data.js").write_text("window.LEADS=" + json.dumps(payload, separators=_compact, ensure_ascii=False) + ";\n")
print(f"  dashboard data.json + data.js written")
print(f"  lead_total: {payload['lead_total']}  primary: {primary_count}  "
      f"estate-synth: {estate_synth}  delinq-synth: {delinq_synth}")
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
