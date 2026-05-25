#!/usr/bin/env python3
"""Smith TX — render the production payload in the El Paso dashboard shape.

County-side transform: NO scaffold/ or knowledge_base/ edits, NO pipeline
changes. Reads the existing v5.4.0 staged-pipeline artifacts (scored_leads
+ matched_leads + raw LGBS events + a fresh Smith CAD parcel cache) and
writes:
  - dashboard/data.json   (El Paso schema, HTTP-fetched)
  - dashboard/data.js     (`window.LEADS = {...};` for file:// loading)

Field map — Smith staged-pipeline -> El Paso renderer field names:
  scored_lead.lead_id                          -> record.lead_id
  scored_lead.lead_status                      -> record.parcel_resolution_status
  scored_lead.enrichment_status                -> record.epcad_enrichment_status
  matched_lead.filer_entity                    -> record.filer_entity
  scored_lead.primary_parcel_id                -> record.parcel_id
  parcel_master OWN1+OWN2 (re-derived)         -> record.owner_name
  derived from owner_name (word-boundary §17)  -> record.owner_type
  parcel_master situs_address (composed)       -> record.property_full_address
  parcel_master assessed/last_sale (NULL)      -> record.assessed_value etc.
  matched_lead.signals -> El Paso signal shape -> record.signals[]
  signal sale_date_only (for the 9 SCHEDULED)  -> signal.sale_date

Attribution preserved per earlier operator rule:
  event_source       = LGBS tax foreclosure (PRIMARY_EVENT_SOURCE)
  owner_source       = parcel_master (downstream enrichment, NEVER §17)
  enrichment_source  = parcel_master / Smith CAD TaxParcels
"""
from __future__ import annotations
import json, re, sys, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, date, timezone
from pathlib import Path

REPO = Path("/Users/quentinflores/Dev/xcerebro/counties/smith-tx")
WORKDIR = REPO / "runs" / "smith_tx" / "build" / "staged_v5_4_0_lgbs_enriched"
RAW = REPO / "data" / "raw" / "lgbs_smith_tax_sales.jsonl"
DASH = REPO / "dashboard"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- Load inputs ---------------------------------------------------------
scored = json.load(open(WORKDIR / "scored_leads.json"))
matched = json.load(open(WORKDIR / "matched_leads.json"))
raw = [json.loads(l) for l in RAW.open() if l.strip()]
print(f"loaded: scored={len(scored)} matched={len(matched)} raw={len(raw)}")

raw_by_event = {ev["raw_event_id"]: ev for ev in raw}
raw_by_instr = {ev.get("instrument_number"): ev for ev in raw
                if ev.get("instrument_number")}
matched_by_lead = {m["lead_id"]: m for m in matched}

# ---- Targeted Smith CAD pull for the 31 LGBS parcels ---------------------
ACCOUNTS = sorted({ev["property_refs"]["parcel_id"] for ev in raw
                   if ev.get("property_refs", {}).get("parcel_id")})
quoted = ",".join("'%s'" % a for a in ACCOUNTS)
URL = ("https://www.smithcountymapsite.org/publicgis/rest/services/"
       "Gallery/TaxParcelQuery/MapServer/1/query")
UA = {"User-Agent": "Mozilla/5.0 (xcerebro-smith-tx-render/0.1)",
      "Accept": "application/json"}
params = urllib.parse.urlencode({"where": f"ACCOUNT IN ({quoted})",
    "outFields": "*", "returnGeometry": "false", "f": "json"})
with urllib.request.urlopen(urllib.request.Request(URL + "?" + params, headers=UA),
                            timeout=30) as r:
    cad_feats = json.loads(r.read()).get("features", [])
parcel_cache = {}
for f in cad_feats:
    a = f.get("attributes") or {}
    acct = (a.get("ACCOUNT") or "").strip()
    if acct and acct not in parcel_cache:
        parcel_cache[acct] = a
print(f"parcel_cache: {len(parcel_cache)} parcels / {len(ACCOUNTS)} accounts")

# ---- §17-style owner_type classifier (word-boundary, county-side) --------
_ENTITY_RE = re.compile(
    r'\b(LLC|L\.L\.C\.|INC\b|INCORPORATED|CORP(?:ORATION)?|LP\b|LLP|LLLP|PLLC|'
    r'PA\b|LTD\b|COMPANY|CO\.|HOLDINGS|PROPERTIES|VENTURES|INVESTMENTS|'
    r'PARTNERS(?:HIP)?|GROUP|ASSOCIATES|ENTERPRISE(?:S)?|CHURCH|'
    r'SCHOOL\s+DISTRICT|\bISD\b|CITY\s+OF|COUNTY\s+OF|STATE\s+OF|'
    r'INDEPENDENT\s+SCHOOL|TRUSTEE\s+OF)\b'
)
_ESTATE_RE = re.compile(
    r'\b(ESTATE\s+OF|ESTATE\b|EST\b|DECEASED|DEC\'?D|DCSD|'
    r"HEIRS\s+OF|HEIRS\s*&)\b"
)
_TRUST_RE = re.compile(
    r'\bTRUST\b|\bREVOCABLE\b|\bIRREVOCABLE\b|\bLIVING\s+TRUST\b|\bFAMILY\s+TRUST\b'
)
def classify_owner_type(name: str) -> str:
    if not name or not name.strip():
        return "UNKNOWN"
    n = name.upper()
    if _ESTATE_RE.search(n):
        return "ESTATE"
    if _TRUST_RE.search(n):
        return "TRUST"
    if _ENTITY_RE.search(n):
        return "ENTITY"
    return "INDIVIDUAL"


# ---- Address / mailing helpers ------------------------------------------
def compose_full_address(parts: dict) -> str:
    one = (parts.get("addr") or "").strip()
    city = (parts.get("city") or "").strip()
    state = (parts.get("state") or "").strip()
    zip_ = (parts.get("zip") or "").strip()
    if not one:
        return ""
    csz = " ".join(p for p in (city, ", " + state if state else state, zip_) if p).strip()
    csz = csz.replace(", ,", ",")
    return (one + (", " + csz if csz else "")).strip(", ")


def parse_situs_from_lgbs(ev: dict) -> dict:
    refs = ev.get("property_refs") or {}
    s = (refs.get("situs_address") or "")
    # LGBS situs is "<street>, <city>, <state>, <zip>" or similar
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 4:
        return {"addr": parts[0], "city": parts[1],
                "state": parts[2], "zip": parts[3]}
    if len(parts) == 3:
        return {"addr": parts[0], "city": parts[1], "state": parts[2], "zip": ""}
    return {"addr": s, "city": "", "state": "TX", "zip": ""}


# ---- Build El Paso–shaped records ---------------------------------------
records: list = []
enriched_n = 0
unenriched_n = 0
sale_date_format = "%m/%d/%Y"

for s in scored:
    lead_id = s["lead_id"]
    ml = matched_by_lead.get(lead_id, {})
    parcel_id = s.get("primary_parcel_id") or ""
    enrichment_status = "ENRICHED" if s.get("enrichment_status") == "ENRICHED" \
                        else "UNENRICHED"

    # Recover the originating raw_event via signals[].instrument_numbers
    ev = None
    for sig in ml.get("signals") or []:
        for instr in sig.get("instrument_numbers") or []:
            if instr in raw_by_instr:
                ev = raw_by_instr[instr]
                break
        if ev:
            break

    # ---- owner_name (from parcel_master enrichment, NOT §17) ----
    cad = parcel_cache.get(parcel_id) if parcel_id else None
    if cad:
        own1 = (cad.get("OWN1") or "").strip()
        own2 = (cad.get("OWN2") or "").strip()
        owner_name = own1 if not own2 else f"{own1} {own2}".strip()
    else:
        owner_name = ""

    owner_type = classify_owner_type(owner_name)

    # ---- property address — prefer parcel_master (post-canonical) over LGBS ----
    if cad:
        property_full_address = compose_full_address({
            "addr": (cad.get("ADDRESS") or "").strip(),
            "city": (cad.get("POSTAL_CITY") or "").strip(),
            "state": "TX",
            "zip": str(cad.get("ZIPCODE") or "").strip(),
        })
    elif ev:
        property_full_address = compose_full_address(parse_situs_from_lgbs(ev))
    else:
        property_full_address = ""

    # Smith CAD GIS layer has no monetary or sale-history fields
    assessed_value = None
    appraised_value = None
    homestead = None

    # legal_description: synthesize from instrument + cause (skip-trace handle)
    if ev:
        cause = ev.get("instrument_number") or ""
        legal = f"Smith County District Court Cause No. {cause}" if cause else ""
    else:
        legal = ""

    # ---- signals[] (El Paso shape) ----
    out_signals = []
    out_signal_types = []
    source_urls = []
    latest_event_date = None
    for sig in ml.get("signals") or []:
        # canonical "tax_foreclosure_notice" -> stay lowercase; renderer
        # styling falls to the default chip — adequate for a single-signal
        # county build (Tyler ISD scope).
        st = "tax_foreclosure_notice"
        label = sig.get("signal_type") or "Tax Foreclosure Notice"
        instr = (sig.get("instrument_numbers") or [None])[0]
        urls = sig.get("source_urls") or []
        # sale_date — pull from the originating raw_event's event_date.
        ev_for_sig = None
        for ii in sig.get("instrument_numbers") or []:
            ev_for_sig = raw_by_instr.get(ii) or ev_for_sig
        sale_date = (ev_for_sig or {}).get("event_date") if ev_for_sig else None
        recorded_date = sale_date  # LGBS doesn't carry a separate recorded_date

        out_signals.append({
            "signal_type": st,
            "signal_label": "Tax Foreclosure Notice",
            "signal_confidence": "HIGH",
            "source_id": (sig.get("source_ids") or ["lgbs_smith_tax_sales"])[0],
            "count": sig.get("count", 1),
            "source_urls": urls,
            "evidence_ids": sig.get("evidence_ids", []),
            "instrument_numbers": sig.get("instrument_numbers", []),
            "doc_type_raw": (ev_for_sig or {}).get("raw_doc_type") if ev_for_sig else None,
            "recorded_date": recorded_date,
            "sale_date": sale_date,
        })
        out_signal_types.append(st)
        source_urls.extend(urls)
        if sale_date and (latest_event_date is None or sale_date > latest_event_date):
            latest_event_date = sale_date

    if enrichment_status == "ENRICHED":
        enriched_n += 1
    else:
        unenriched_n += 1

    records.append({
        "lead_id": lead_id,
        "parcel_resolution_status": s.get("lead_status", "REVIEW_REQUIRED"),
        "epcad_enrichment_status": enrichment_status,
        "filer_entity": ml.get("filer_entity") or "",
        "parcel_id": parcel_id,
        "owner_name": owner_name,
        "owner_type": owner_type,
        "owners": ml.get("owners", []),
        "property_full_address": property_full_address,
        "property_street": (cad.get("ADDRESS") or "").strip() if cad else "",
        "property_city": (cad.get("POSTAL_CITY") or "").strip() if cad else "",
        "property_state": "TX",
        "property_zip": (str(cad.get("ZIPCODE") or "").strip() if cad else ""),
        "mailing_full_address": "",
        "mailing_city": "",
        "mailing_state": "",
        "assessed_value": assessed_value,
        "appraised_value": appraised_value,
        "homestead": homestead,
        "absentee_owner_flag": False,
        "out_of_state_owner_flag": False,
        "legal_description": legal,
        "year_built": (int(cad.get("YRBLT")) if cad and cad.get("YRBLT") else None),
        "signals": out_signals,
        "signal_types": list(dict.fromkeys(out_signal_types)),
        "source_urls": list(dict.fromkeys(source_urls)),
        "signal_count": len(out_signals),
        "latest_event_date": latest_event_date,
    })

# ---- Top-level payload (El Paso shape) ----------------------------------
cfg = json.load(open(REPO / "config" / "counties" / "smith_tx.json"))
review_required = sum(1 for r in records
                      if r["parcel_resolution_status"] == "REVIEW_REQUIRED")
actionable = len(records) - sum(
    1 for r in records if r["parcel_resolution_status"] == "CANCELLED"
)

payload = {
    "generated_at": NOW,
    "county": "Smith",
    "state": "TX",
    "build_label": cfg.get("dashboard", {}).get("build_label") or "PARTIAL_BUILD",
    "build_label_reason": cfg.get("dashboard", {}).get("build_label_reason")
                          or "Single primary source (lgbs_smith_tax_sales). "
                             "Clerk + court + RealAuction + tax-portal sources "
                             "still need browser+reCAPTCHA (ESC-002).",
    "sources_active": ["lgbs_smith_tax_sales"],
    "lead_total": len(records),
    "epcad_enrichment_resolved": enriched_n,
    "epcad_enrichment_unresolved": unenriched_n,
    "review_required": review_required,
    "actionable_leads": actionable,
    "records": records,
}

# ---- Write data.json + data.js ------------------------------------------
DASH.mkdir(parents=True, exist_ok=True)
data_json = DASH / "data.json"
data_js = DASH / "data.js"
data_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
data_js.write_text("window.LEADS = "
                   + json.dumps(payload, ensure_ascii=False) + ";\n",
                   encoding="utf-8")
print(f"\nwrote {data_json.relative_to(REPO)} ({data_json.stat().st_size:,} bytes)")
print(f"wrote {data_js.relative_to(REPO)} ({data_js.stat().st_size:,} bytes)")
print(f"\nrecords={payload['lead_total']}  ENRICHED={enriched_n}  "
      f"UNENRICHED={unenriched_n}  review_required={review_required}")
print(f"owner_type breakdown: "
      f"{dict(Counter(r['owner_type'] for r in records))}")
print(f"signal_types: {dict(Counter(t for r in records for t in r['signal_types']))}")
