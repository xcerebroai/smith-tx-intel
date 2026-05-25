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
SOURCES = ["lgbs_smith_tax_sales", "pbfcm_smith_tax_resale", "county_excess_proceeds"]
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
        # event_date from originating raw_event
        ev_for_sig = None
        for ii in sig.get("instrument_numbers") or []:
            ev_for_sig = raw_by_instr.get(ii) or ev_for_sig
        sale_date = (ev_for_sig or {}).get("event_date") if ev_for_sig else None
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
            "recorded_date": sale_date,
            "sale_date": sale_date,
        })

    signal_types = list(dict.fromkeys(sig["signal_type"] for sig in out_signals))
    source_urls = list(dict.fromkeys(u for sig in out_signals for u in sig["source_urls"]))
    latest_event = max((sig["sale_date"] for sig in out_signals if sig.get("sale_date")), default=None)

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
    })

cfg = json.load(open(REPO / "config" / "counties" / "smith_tx.json"))
review_required = sum(1 for r in records if r["parcel_resolution_status"] == "REVIEW_REQUIRED")
payload = {
    "generated_at": NOW, "county": "Smith", "state": "TX",
    "build_label": cfg["dashboard"].get("build_label") or "PARTIAL_BUILD",
    "build_label_reason": cfg["dashboard"].get("build_label_reason") or "",
    "sources_active": list(per_source.keys()),
    "lead_total": len(records),
    "epcad_enrichment_resolved": sum(1 for r in records if r["epcad_enrichment_status"] == "ENRICHED"),
    "epcad_enrichment_unresolved": sum(1 for r in records if r["epcad_enrichment_status"] == "UNENRICHED"),
    "review_required": review_required,
    "actionable_leads": len(records),
    "records": records,
}
(DASH / "data.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
(DASH / "data.js").write_text("window.LEADS = " + json.dumps(payload, ensure_ascii=False) + ";\n")
print(f"  dashboard data.json + data.js written")
print(f"  lead_total: {payload['lead_total']}  enriched: {payload['epcad_enrichment_resolved']}")
print(f"  signal_types: {dict(Counter(t for r in records for t in r['signal_types']))}")
print(f"  owner_type:   {dict(Counter(r['owner_type'] for r in records))}")
print(f"  per source:   {dict(Counter(r['signals'][0]['source_id'] for r in records if r['signals']))}")

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
