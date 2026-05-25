#!/usr/bin/env python3
"""Smith TX v5.4.0 staged pipeline — LGBS PRIMARY + parcel_master ENRICHMENT.

County-side wiring only — no scaffold/ or knowledge_base/ edits.

Flow:
  1. Load LGBS raw_events (PRIMARY_EVENT_SOURCE, 31 records).
  2. Pre-resolve parcel_id by joining LGBS account_nbr -> Smith CAD ACCOUNT
     via a targeted ArcGIS WHERE-IN pull. Cache one parcel_master dict per
     account.
  3. Sequence the staged-pipeline stages explicitly so we can apply ONE
     county-side patch between §19 aggregator and §20 verify:
     rewrite matched_lead.primary_parcel_id from the raw_event lookup so
     the seam's enrichment_provider gets the parcel_id it needs. The
     framework code is unchanged; §17 still reads only raw_event.parties
     and still routes LGBS rows to REVIEW_REQUIRED (correct).
  4. Run §20 semantic verification. Halt on DEPLOY_BLOCKED.
  5. Call scoring_seam.score_matched_leads with the parcel-master
     enrichment_provider — the seam derives attributes inline.
  6. Build the dashboard payload and write dashboard/data.json.

Attribution preserved per lead:
  - event_source        = LGBS tax foreclosure (PRIMARY_EVENT_SOURCE)
  - owner_source        = parcel_master (downstream enrichment, NEVER §17)
  - enrichment_source   = parcel_master / Smith CAD TaxParcels
  - §17 owner_resolution_status stays REVIEW_REQUIRED / owner_not_on_document

Stage boundary: parcel_master is enrichment only — never feeds §17, never
originates a lead. All leads exist because of the LGBS primary event.
"""
from __future__ import annotations
import json, sys, urllib.parse, urllib.request
from collections import defaultdict
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
WORKDIR = REPO / "runs" / "smith_tx" / "build" / "staged_v5_4_0_lgbs_enriched"
WORKDIR.mkdir(parents=True, exist_ok=True)
DASH = REPO / "dashboard" / "data.json"
RAW = REPO / "data" / "raw" / "lgbs_smith_tax_sales.jsonl"
CAD_URL = ("https://www.smithcountymapsite.org/publicgis/rest/services/"
           "Gallery/TaxParcelQuery/MapServer/1/query")
UA = {"User-Agent": "Mozilla/5.0 (xcerebro-smith-tx-enrichment-wire/0.1)",
      "Accept": "application/json"}

punch = []
def P(item): punch.append(item); print(f"  punch: {item}")


# ---- 1. Load LGBS raw_events ----------------------------------------------
print("== load LGBS raw_events ==")
raw_events = [json.loads(l) for l in RAW.open() if l.strip()]
print(f"  {len(raw_events)} raw_events (all source_role=PRIMARY_EVENT_SOURCE)")


# ---- 2. Targeted Smith CAD pull → enrichment cache (parcel_id keyed) -----
print()
print("== Smith CAD targeted enrichment pull ==")
ACCOUNTS = sorted({
    ev["property_refs"]["parcel_id"] for ev in raw_events
    if ev.get("property_refs", {}).get("parcel_id")
})
print(f"  distinct LGBS account_nbrs: {len(ACCOUNTS)}")
quoted = ",".join("'%s'" % a for a in ACCOUNTS)
params = urllib.parse.urlencode({"where": f"ACCOUNT IN ({quoted})",
    "outFields": "*", "returnGeometry": "false", "f": "json"})
with urllib.request.urlopen(
    urllib.request.Request(CAD_URL + "?" + params, headers=UA), timeout=30
) as r:
    cad_feats = json.loads(r.read()).get("features", [])
print(f"  Smith CAD returned {len(cad_feats)} features for the WHERE IN clause")

def _cad_to_parcel(attrs: dict) -> dict:
    """Map Smith CAD TaxParcels attrs -> the parcel-master dict shape the
    scoring seam (`scoring_seam._parcel_display_from` + `normalize.derive_attributes`)
    expects. Both `address`/`situs_address` and `city`/`situs_city` keys are
    populated because the seam falls back across both name conventions."""
    own1 = (attrs.get("OWN1") or "").strip()
    own2 = (attrs.get("OWN2") or "").strip()
    owner = own1 if not own2 else f"{own1} {own2}".strip()
    addr = (attrs.get("ADDRESS") or "").strip().upper() or None
    city = (attrs.get("POSTAL_CITY") or "").strip().upper() or None
    zip_ = str(attrs.get("ZIPCODE") or "").strip() or None
    yr = attrs.get("YRBLT") or 0
    sfla = attrs.get("SFLA") or 0
    acre = attrs.get("Calc_Acre")
    return {
        "parcel_id": (attrs.get("ACCOUNT") or "").strip(),
        "situs_address": addr, "address": addr,
        "situs_city": city,    "city": city,
        "situs_state": "TX",
        "situs_zip": zip_,     "zip": zip_,
        "owner_name": owner or None,
        "year_built": int(yr) if int(yr) > 0 else None,
        "acres": float(acre) if acre is not None else None,
        "building_sqft": int(sfla) if sfla else None,
        "property_use": (attrs.get("Type") or "").strip() or None,
        # GIS layer does NOT carry monetary values or sale history.
        "assessed_value": None, "land_value": None, "improvement_value": None,
        "last_sale_date": None, "last_sale_price": None,
        # county-side attribution
        "_enrichment_source": "smith_cad_taxparcels",
        "_enrichment_source_url": (
            "https://www.smithcountymapsite.org/publicgis/rest/services/"
            f"Gallery/TaxParcelQuery/MapServer/1/query?objectIds={attrs.get('OBJECTID')}&f=json"
        ),
    }

PARCEL_CACHE: dict[str, dict] = {}
for f in cad_feats:
    rec = _cad_to_parcel(f.get("attributes") or {})
    if rec["parcel_id"] and rec["parcel_id"] not in PARCEL_CACHE:
        PARCEL_CACHE[rec["parcel_id"]] = rec
joined = set(PARCEL_CACHE) & set(ACCOUNTS)
missing = sorted(set(ACCOUNTS) - set(PARCEL_CACHE))
print(f"  enrichment cache: {len(PARCEL_CACHE)} distinct parcels")
print(f"  join coverage:    {len(joined)}/{len(ACCOUNTS)} LGBS accounts")
if missing:
    P(f"{len(missing)} LGBS account(s) not found in Smith CAD TaxParcels: "
      f"{missing} — possible reasons: cross-county precinct, retired account "
      f"number, or LGBS using a non-CAD account id format.")

def enrichment_provider(parcel_id):
    """The seam's contract: parcel_id -> parcel dict (or None). None means
    UNENRICHED for that lead — the lead is still scored, never dropped."""
    return PARCEL_CACHE.get(parcel_id) if parcel_id else None


# ---- 3. Replicate staged-pipeline stages with the parcel_id patch --------
print()
print("== §17 -> §18 -> §19 [patch] -> §20 -> seam ==")

# §17 — debtor party engine. Inputs are raw_event.parties only (LGBS has [],
# so every row is correctly routed REVIEW_REQUIRED / owner_not_on_document).
debtor_resolved = [
    debtor_party_engine.resolve_debtor_party(ev) for ev in raw_events
]

# §18 — leads_base writer (per source).
ledger = evidence_ledger_mod.build_evidence_ledger([])
by_source: dict[str, list] = defaultdict(list)
for drr in debtor_resolved:
    by_source[drr.get("source_id") or "unknown"].append(drr)

all_base_records = []
base_paths = []
for source_id, drrs in by_source.items():
    src_base = [leads_base_writer.build_base_record(
        drr, signal_type_labels={}, evidence_ledger=ledger) for drr in drrs]
    all_base_records.extend(src_base)
    base_paths.append(leads_base_writer.write_leads_base(
        source_id, src_base, output_dir=WORKDIR))
print(f"  §17 debtor_resolved: {len(debtor_resolved)}")
print(f"  §18 leads_base:      {len(all_base_records)}")

# §19 — aggregator.
matched_leads_path = WORKDIR / "matched_leads.json"
matched_leads = aggregator.aggregate(base_paths, output_path=matched_leads_path)
evidence_ledger_mod.write_evidence_ledger([], output_dir=WORKDIR)
print(f"  §19 matched_leads:   {len(matched_leads)}")

# === county-side patch ====================================================
# leads_base_writer cascades parcel_resolution_status from debtor_resolution_
# status (framework finding F-1); aggregation_key.parcel_id is then nulled
# even though property_refs.parcel_id is populated. The §13.14 decoupling
# spec calls these statuses independent — the §17 owner being unknown does
# NOT make the parcel itself unresolved. County-side runner-level workaround:
# after aggregate(), rewrite matched_lead.primary_parcel_id from the raw_event
# lookup. §17 / §18 / §19 framework code unchanged.
EV_BY_INSTR = {
    ev.get("instrument_number"): ev["property_refs"].get("parcel_id")
    for ev in raw_events if ev.get("instrument_number")
}
patched = 0
for ml in matched_leads:
    if ml.get("primary_parcel_id"):
        continue
    for sig in ml.get("signals") or []:
        for instr in sig.get("instrument_numbers") or []:
            pid = EV_BY_INSTR.get(instr)
            if pid:
                ml["primary_parcel_id"] = pid
                patched += 1
                break
        if ml.get("primary_parcel_id"):
            break
matched_leads_path.write_text(
    json.dumps(matched_leads, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
print(f"  COUNTY PATCH: primary_parcel_id set on {patched}/{len(matched_leads)} "
      f"matched_leads (was null because §17 routed REVIEW_REQUIRED)")
P("F-1 framework finding (leads_base_writer.py): debtor_resolution_status "
  "REVIEW_REQUIRED cascades to parcel_resolution_status REVIEW_REQUIRED and "
  "nulls aggregation_key.parcel_id, which then nulls matched_lead.primary_parcel_id. "
  "The §13.14 spec calls these statuses independent. Recommend v5.4.x backlog: "
  "leads_base_writer should populate aggregation_key.parcel_id whenever "
  "property_refs.parcel_id is non-null, regardless of debtor_resolution_status. "
  "Workaround applied here is runner-side only — framework code unchanged.")

# §20 — semantic verification.
semantic_report = semantic_verify.run_semantic_verification(
    matched_leads, leads_base_records=all_base_records, evidence_ledger=ledger,
)
verdict = semantic_report.get("verdict")
(WORKDIR / "semantic_verify_report.json").write_text(
    json.dumps(semantic_report, indent=2, ensure_ascii=False, default=str) + "\n")
print(f"  §20 verdict: {verdict}")
if verdict == "DEPLOY_BLOCKED":
    (WORKDIR / "halt_deploy_blocked.json").write_text(
        json.dumps({"verdict": "DEPLOY_BLOCKED", "at": NOW}, indent=2) + "\n")
    print("HALT — §20 DEPLOY_BLOCKED")
    sys.exit(20)


# ---- 4. Seam — score with parcel_master enrichment_provider --------------
scored_leads = scoring_seam.score_matched_leads(
    matched_leads, as_of=date(2026, 5, 25),
    enrichment_provider=enrichment_provider,
)
(WORKDIR / "scored_leads.json").write_text(
    json.dumps(scored_leads, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
enriched = sum(1 for s in scored_leads if s.get("enrichment_status") == "ENRICHED")
print(f"  seam scored:         {len(scored_leads)}")
print(f"  enriched:            {enriched}/{len(scored_leads)}")

if enriched < len(scored_leads):
    P(f"{len(scored_leads) - enriched} lead(s) UNENRICHED — same as the join-miss "
      f"set above; honest UNENRICHED per §13.14 (lead not dropped).")
P("Smith CAD TaxParcels GIS layer does NOT carry assessed_value / last_sale data — "
  "those live in Smith CAD's esearch system. Monetary attribute derivations "
  "(high_equity, free_and_clear, etc.) will be empty even on ENRICHED rows. "
  "Followup: ingest the Smith CAD bulk appraisal roll for value enrichment.")


# ---- 5. Dashboard --------------------------------------------------------
print()
print("== dashboard ==")
cfg = json.load(open(REPO / "config" / "counties" / "smith_tx.json"))
payload = build_dashboard_payload(
    scored_leads, semantic_verdict=verdict,
    county="Smith County", state="TX", mode="production",
    build_label=cfg["dashboard"].get("build_label") or "PARTIAL_BUILD",
)
assert payload["lead_total"] == len(payload["records"]), "Two-Truths drift"
DASH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
print(f"  dashboard data: {DASH.relative_to(REPO)}")
print(f"  lead_total:             {payload['lead_total']}")
print(f"  enrichment_breakdown:   {payload['enrichment_breakdown']}")
print(f"  pattern_counts:         {payload['pattern_counts']}")
print(f"  attribute_counts:       {payload['attribute_counts']}")
print(f"  score_tier_distribution:{payload['score_tier_distribution']}")
print(f"  deal_path_distribution: {payload['deal_path_distribution']}")
print(f"  stack_depth_distribution:{payload['stack_depth_distribution']}")

# Punch list + summary
(WORKDIR / "punch_list.json").write_text(json.dumps({
    "generated_at": NOW, "framework_version": "v5.4.0",
    "county": "smith_tx", "semantic_verdict": verdict,
    "lead_total": payload["lead_total"],
    "lgbs_accounts": len(ACCOUNTS),
    "enrichment_cache_size": len(PARCEL_CACHE),
    "join_coverage": f"{len(joined)}/{len(ACCOUNTS)}",
    "enriched_count": enriched,
    "unenriched_count": len(scored_leads) - enriched,
    "unmatched_accounts": missing,
    "primary_parcel_id_patched": patched,
    "items": punch,
}, indent=2, ensure_ascii=False) + "\n")

print()
print("===== END-TO-END SUMMARY =====")
print(f"§20 verdict:           {verdict}")
print(f"lead_total:            {payload['lead_total']}")
print(f"ENRICHED:              {enriched}")
print(f"UNENRICHED:            {len(scored_leads) - enriched}")
print(f"join coverage:         {len(joined)}/{len(ACCOUNTS)}")
print(f"primary_parcel_id pat: {patched}")
print(f"punch-list items:      {len(punch)}")
print(f"dashboard:             {DASH.relative_to(REPO)}")
