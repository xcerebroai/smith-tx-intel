#!/usr/bin/env python3
"""Smith TX end-to-end v5.4.0 staged pipeline driver — county-scoped runner.

Stop conditions (only):
  - The pipeline crashes and cannot produce a dashboard  -> exit 1
  - §20 returns DEPLOY_BLOCKED                            -> exit 20
Everything else (REVIEW_REQUIRED, AMBIGUOUS / NEEDS_OPERATOR_REVIEW, thin
sources, missing adapters) is logged to the punch-list and the run continues.
"""
from __future__ import annotations
import json, sys, traceback
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path("/Users/quentinflores/Dev/xcerebro/counties/smith-tx")
sys.path.insert(0, str(REPO))

from scaffold.pipeline import run_pipeline_staged
from scaffold.pipeline import scoring_seam

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
WORKDIR = REPO / "runs" / "smith_tx" / "build" / "staged_v5_4_0"
WORKDIR.mkdir(parents=True, exist_ok=True)
RAW = REPO / "data" / "raw"
DASH_DATA = REPO / "dashboard" / "data.json"

punch: list[str] = []
def P(item: str) -> None:
    punch.append(item)
    print(f"  punch-list: {item}")

# ---- Load raw events ------------------------------------------------------
# The parcel_master adapter was built against the §4.32 wrapped raw-record
# shape (v5.1.2). v5.4.0 raw_event_record.schema.json requires top-level
# raw_event_id / source_role / canonical_doc_type / parties / property_refs.
# This driver bridges in-place — county-scoped data adaptation at the call
# site, NOT a harness edit. Each enrichment record is emitted with
# source_role=ENRICHMENT_SOURCE so §13 / §17 will refuse to originate a lead
# from it (correct behavior; routes to REVIEW_REQUIRED).
SOURCE_ROLE_MAP = {
    "clerk_recordings": "PRIMARY_EVENT_SOURCE",
    "district_court": "PRIMARY_EVENT_SOURCE",
    "sheriff_tax_auctions": "BLOCKED_SOURCE",
    "tax_collector": "BLOCKED_SOURCE",
    "parcel_master": "ENRICHMENT_SOURCE",
    "gis_parcels": "ENRICHMENT_SOURCE",
}
CANONICAL_DOC_TYPE_BY_SOURCE = {
    "parcel_master": "PARCEL_MASTER",
    "gis_parcels": "GIS_PARCEL",
}

def bridge_to_v540_raw_event(rec: dict) -> dict:
    """Map §4.32 wrapped raw record -> v5.4.0 raw_event_record shape."""
    sid = rec.get("source_id") or "unknown"
    payload = rec.get("raw_payload") or {}
    out = {
        "raw_event_id": rec.get("raw_record_id") or f"{sid}-{id(rec)}",
        "source_id": sid,
        "source_role": SOURCE_ROLE_MAP.get(sid, "ENRICHMENT_SOURCE"),
        "canonical_doc_type": CANONICAL_DOC_TYPE_BY_SOURCE.get(sid, "UNKNOWN_DOC_TYPE"),
        "source_url": rec.get("source_url") or "about:blank",
        "recorded_date": None,
        "instrument_number": None,
        "parties": [],
        "property_refs": {
            "parcel_id": payload.get("parcel_id"),
            "situs_address": payload.get("address"),
            "legal_description": payload.get("legal_description"),
            "case_number": None,
        },
        "raw_doc_type": None,
        "event_date": None,
        "amounts": [],
        "evidence_ids": [],
        "parser_name": "scrapers/parcel_master.py",
        "parser_version": None,
        "parser_confidence": rec.get("parser_confidence"),
        "captured_at": rec.get("source_fetched_at"),
        "document_body_text": None,
    }
    return out

raw_events: list[dict] = []
sources_loaded: list[tuple[str, int]] = []
print("== load raw events ==")
if not RAW.exists():
    P("data/raw/ does not exist — no scraper output present")
else:
    for jp in sorted(RAW.glob("*.jsonl")):
        n = 0
        with jp.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    P(f"malformed JSONL line in {jp.name}: {e}")
                    continue
                # County-side bridge: §4.32 wrapped -> v5.4.0 raw_event
                raw_events.append(bridge_to_v540_raw_event(rec))
                n += 1
        sources_loaded.append((jp.name, n))
        print(f"  loaded {n:>6} records from {jp.name}")

print(f"  total raw_events: {len(raw_events)} from {len(sources_loaded)} file(s)")
P("source adapters built: only parcel_master (ENRICHMENT). The 4 primary-event "
  "adapters (clerk_recordings, district_court, sheriff_tax_auctions, "
  "tax_collector) require browser + reCAPTCHA infrastructure not present in "
  "this environment — see ESC-002. Per §13 the dashboard CANNOT carry active "
  "lead rows from enrichment alone.")
P("scrapers/parcel_master.py emits the §4.32 wrapped shape (pre-v5.4.0). "
  "Bridged to v5.4.0 raw_event_record shape in this driver "
  "(canonical_doc_type=PARCEL_MASTER, source_role=ENRICHMENT_SOURCE). The "
  "framework parcel_master translator under scaffold/pipeline/translators/ "
  "is NOT yet wired into the staged orchestrator for direct §4.32 ingest.")

# Punch-list: count of source adapters declared in the county config vs
# adapters that actually produced raw data.
cfg = json.load((REPO / "config" / "counties" / "smith_tx.json").open())
declared_sources = list(cfg.get("sources", {}).keys())
loaded_source_ids = {ev.get("source_id") for ev in raw_events if ev.get("source_id")}
missing = [s for s in declared_sources if s not in loaded_source_ids]
for s in missing:
    src = cfg["sources"][s]
    role = src.get("source_role", "?")
    P(f"NO RAW DATA for declared source `{s}` (role={role}); adapter not built or not run")

# ---- Run the staged pipeline ---------------------------------------------
print()
print("== §17 -> §18 -> §19 -> §20 -> seam -> scored leads ==")
try:
    result = run_pipeline_staged.run_staged_pipeline(
        raw_events,
        evidence_entries=[],
        workdir=WORKDIR,
        as_of=date(2026, 5, 23),
        approve_needs_review=True,   # operator rule: AMBIGUOUS -> continue
    )
except scoring_seam.SemanticGateBlocked as exc:
    print()
    print(f"HALT — §20 DEPLOY_BLOCKED: {exc}")
    report = WORKDIR / "halt_deploy_blocked.json"
    report.write_text(json.dumps({"verdict": "DEPLOY_BLOCKED",
                                  "exception": str(exc)},
                                 indent=2) + "\n", encoding="utf-8")
    sys.exit(20)
except Exception as exc:  # noqa: BLE001 — top-level catch is the point
    print()
    print(f"PIPELINE CRASH — {type(exc).__name__}: {exc}")
    traceback.print_exc()
    sys.exit(1)

verdict = result["semantic_verdict"]
print(f"  §20 verdict: {verdict}")

# ---- Pipeline-level metrics ----------------------------------------------
debtor_resolved = result["debtor_resolved"]
leads_base = result["leads_base"]
matched_leads = result["matched_leads"]
scored_leads = result["scored_leads"]

def pct(n, d): return f"{(100*n//max(d,1))}%"

drr_status = Counter(
    d.get("parcel_resolution_status") or d.get("status") or "UNKNOWN"
    for d in debtor_resolved
)
lb_status = Counter(
    b.get("parcel_resolution_status") or b.get("status") or "UNKNOWN"
    for b in leads_base
)
ml_status = Counter(
    m.get("parcel_resolution_status") or m.get("status") or "UNKNOWN"
    for m in matched_leads
)
review_required_count = ml_status.get("REVIEW_REQUIRED", 0)

print(f"  §17 debtor_resolved: {len(debtor_resolved)}  status -> {dict(drr_status)}")
print(f"  §18 leads_base:      {len(leads_base)}  status -> {dict(lb_status)}")
print(f"  §19 matched_leads:   {len(matched_leads)}  status -> {dict(ml_status)}")
print(f"  seam scored_leads:   {len(scored_leads)}")

# §20 detail
sem_report = result["semantic_report"]
print(f"  §20 report keys: {list(sem_report)[:8]}...")
if isinstance(sem_report, dict):
    checks = sem_report.get("checks") or sem_report.get("check_results") or []
    if isinstance(checks, list):
        by_outcome = Counter(c.get("outcome", "?") for c in checks if isinstance(c, dict))
        print(f"  §20 check outcomes: {dict(by_outcome)}")
        for c in checks:
            if not isinstance(c, dict):
                continue
            if c.get("outcome") in ("INVALID", "AMBIGUOUS"):
                P(f"§20 {c.get('outcome')}: {c.get('name') or c.get('check')} — "
                  f"{c.get('detail') or c.get('reason') or ''}")

# Punch-list per-§17 routing
if review_required_count:
    P(f"§17 routed {review_required_count} matched_leads to REVIEW_REQUIRED "
      f"({pct(review_required_count, len(matched_leads))} of total)")

# Punch-list if no scored leads
if not scored_leads:
    P("scored_leads is empty — dashboard will have zero lead rows "
      "(enrichment alone cannot originate leads; primary-event adapters missing).")

# ---- Dashboard build ------------------------------------------------------
print()
print("== dashboard build ==")
payload = run_pipeline_staged.build_dashboard_payload(
    scored_leads, semantic_verdict=verdict,
    county="Smith County", state="TX",
    mode="production",
    build_label=cfg.get("dashboard", {}).get("build_label") or "PARTIAL_BUILD",
)
# Two-Truths: payload['lead_total'] == len(payload['records'])
assert payload["lead_total"] == len(payload["records"]), "Two-Truths drift"
DASH_DATA.parent.mkdir(parents=True, exist_ok=True)
DASH_DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
print(f"  dashboard data: {DASH_DATA.relative_to(REPO)}")
print(f"  lead_total: {payload['lead_total']}")
print(f"  enrichment_breakdown: {payload['enrichment_breakdown']}")
print(f"  pattern_counts: {payload['pattern_counts']}")
print(f"  score_tier_distribution: {payload['score_tier_distribution']}")
print(f"  deal_path_distribution: {payload['deal_path_distribution']}")

# Save punch-list
PUNCH = WORKDIR / "punch_list.json"
PUNCH.write_text(json.dumps({
    "generated_at": NOW,
    "framework_version": "v5.4.0",
    "county": "smith_tx",
    "semantic_verdict": verdict,
    "lead_total": payload["lead_total"],
    "review_required_count": review_required_count,
    "raw_events_loaded": len(raw_events),
    "sources_loaded": sources_loaded,
    "declared_sources": declared_sources,
    "sources_missing_raw_data": missing,
    "items": punch,
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"  punch-list saved: {PUNCH.relative_to(REPO)}  ({len(punch)} items)")

# Summary
print()
print("===== END-TO-END SUMMARY =====")
print(f"§20 verdict:         {verdict}")
print(f"lead_total:          {payload['lead_total']}")
print(f"REVIEW_REQUIRED:     {review_required_count}")
print(f"punch-list items:    {len(punch)}")
print(f"dashboard data.json: {DASH_DATA.relative_to(REPO)}")
print(f"staged workdir:      {WORKDIR.relative_to(REPO)}")
