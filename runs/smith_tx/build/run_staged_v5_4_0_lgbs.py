#!/usr/bin/env python3
"""Wire the LGBS source into smith_tx.json, then run the v5.4.0 staged
pipeline end-to-end with LGBS as the PRIMARY EVENT SOURCE (no parcel_master
feeding §17 — operator rule)."""
from __future__ import annotations
import copy, json, sys, traceback
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path("/Users/quentinflores/Dev/xcerebro/counties/smith-tx")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scaffold" / "ops"))
from write_county_config import write_county_config  # noqa: E402
from scaffold.pipeline import run_pipeline_staged, scoring_seam  # noqa: E402

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
WORKDIR = REPO / "runs" / "smith_tx" / "build" / "staged_v5_4_0_lgbs"
WORKDIR.mkdir(parents=True, exist_ok=True)
DASH_DATA = REPO / "dashboard" / "data.json"

punch: list[str] = []
def P(item): punch.append(item); print(f"  punch: {item}")

# ====================================================================
# 1. UPDATE config/counties/smith_tx.json — add lgbs_smith_tax_sales source
# ====================================================================
cfg_path = REPO / "config" / "counties" / "smith_tx.json"
cfg = json.load(open(cfg_path))
# Use existing parcel_master block as the 78-key skeleton; override.
skel = copy.deepcopy(cfg["sources"]["parcel_master"])
src = copy.deepcopy(skel)
src.update({
    "category": "lead", "subtype": "sheriff_sales",
    "url": "https://taxsales.lgbs.com/api/property_sales/?county=SMITH+COUNTY&state=TX",
    "access_pattern": "open_api",
    "translator": "custom",
    "scraper_module": "scrapers/lgbs_smith_tax_sales.py",
    "recommended_adapter": "scrapers/lgbs_smith_tax_sales.py",
    "official_status": "OFFICIAL_VENDOR_PORTAL",
    "lead_value": "LEAD_GENERATING",
    "operator_override": False,
    "source_reliability_grade": "A",
    "source_priority": "P0",
    "build_priority": "mvp_required",
    "source_freshness": "WEEKLY",
    "refresh_cadence": "weekly",
    "auth_required": False,
    "rate_limit_rpm": 60,
    "ttl_days": 365,
    "verified_from_url": "https://www.smith-county.com/358/Delinquent-Tax-Sales",
    "verification_method": "official_vendor_link",
    "official_entity": ("Linebarger Goggan Blair & Sampson, LLP — delinquent-tax "
        "attorney for Smith County and most taxing units (Tyler ISD is handled "
        "separately by Perdue Brandon)."),
    "portal_type": ("Django REST Framework JSON API (same-origin to the "
        "taxsales.lgbs.com SPA, discovered from the SPA bundle)"),
    "portal_family": "Django REST Framework / LGBS",
    "records_available": ["tax foreclosure sale listings",
        "struck-off resale inventory", "scheduled online tax auctions"],
    "search_fields": ["county", "state", "cause_nbr", "account_nbr"],
    "access_method": "API_ENDPOINT",
    "public_access_status": "FULL_PUBLIC_ACCESS",
    "document_access_status": "DOCUMENTS_PUBLIC",
    "source_role": "PRIMARY_LEAD_SOURCE",
    "verification_confidence": "HIGH",
    "verification_note": ("Stdlib-reachable JSON API. Probe 2026-05-25 returned "
        "31 Smith County records (22 STRUCK OFF + 9 SALE; 100% with "
        "account_nbr + prop_address_one + cause_nbr — property attachment "
        "proven for every record per the Duval JUDGMENT standard). The LGBS "
        "API carries NO party names; §17 routes every record to "
        "REVIEW_REQUIRED with the §17.D placeholder owner — that is correct "
        "framework behavior when expected_debtor is missing from the event "
        "document. Owner enrichment attaches downstream from parcel_master "
        "via the account_nbr / parcel_id join."),
    "open_questions": [],
    "known_limitations": [
        "Linebarger handles general Smith County + most ISDs; Tyler ISD tax "
        "sales (handled by Perdue Brandon) are NOT covered by this source.",
        "API carries no party names — debtor is REVIEW_REQUIRED at §17.",
    ],
    "doc_type_synonyms": {
        "SALE": "TAX_FORECLOSURE_SALE",
        "STRUCK OFF": "TAX_FORECLOSURE_SALE",
    },
    "sample_record_path_confirmed": True,
    "sample_record_type": "api_endpoint",
    "sample_search_possible": True,
    "sample_document_view_possible": False,
    "blocker": "", "next_access_strategy": "", "blocker_type": "",
    "blocked_unblock_paths": [],
    "auto_resolve_status": "NOT_ATTEMPTED",
    "final_resolution_status": "",
    "auto_resolve_attempts": [],
    "estimated_cost_category": "FREE",
    "estimated_runtime_minutes": 5,
    "portal_fingerprint_id": "smith_tx_lgbs_smith_tax_sales",
    "fingerprint_confidence": "HIGH",
    "fingerprint_summary": ("Django REST Framework, JSON, unauthenticated, "
        "paginated via limit/offset and `next` URL. No CAPTCHA, no SPA gating."),
    "fingerprinted_at": NOW,
    "expected_refresh_cadence": "WEEKLY",
    "stale_after_hours": 240,
    "stale_record_policy": "EXPIRE_IF_NOT_SEEN",
    "expire_if_not_seen_runs": 2,
    "record_ttl_days": 365,
    "credentials_required_kind": "",
    "credentials_declared": False,
    "last_verified_at": NOW,
    "source_freshness_status": "FRESH",
    "fields": {},
})
cfg["sources"]["lgbs_smith_tax_sales"] = src

# Update dashboard build_label
cfg["dashboard"]["build_label"] = "PARTIAL_BUILD"
cfg["dashboard"]["build_label_reason"] = (
    "First stdlib-reachable PRIMARY EVENT SOURCE wired: lgbs_smith_tax_sales "
    "(Linebarger tax-foreclosure sales). publicsearch.us clerk and the other "
    "primary sources still need browser+reCAPTCHA per ESC-002.")

# Pre-validate then write
import jsonschema
schema = json.load(open(REPO / "config" / "counties" / "_schema.json"))
errs = sorted(jsonschema.Draft7Validator(schema).iter_errors(cfg),
              key=lambda e: list(e.absolute_path))
if errs:
    print(f"PRE-VAL FAIL: {len(errs)} errors")
    for e in errs[:20]: print("  -", list(e.absolute_path), "::", e.message)
    sys.exit(2)
r = write_county_config(config_dict=cfg, target_path=str(cfg_path),
    schema_path=str(REPO / "config" / "counties" / "_schema.json"), overwrite=True)
print(f"config write: status={r.status}  schema_validation={r.schema_validation}")
if not r.is_ok():
    print(r.summary()); sys.exit(1)

# ====================================================================
# 2. LOAD raw_events — LGBS ONLY (operator rule: parcel_master never feeds §17)
# ====================================================================
print()
print("== load raw_events (PRIMARY only — no parcel_master) ==")
raw_events: list[dict] = []
src_path = REPO / "data" / "raw" / "lgbs_smith_tax_sales.jsonl"
if not src_path.exists():
    P(f"missing {src_path.relative_to(REPO)} — run scrapers/lgbs_smith_tax_sales.py first")
else:
    with src_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            raw_events.append(json.loads(line))
    print(f"  loaded {len(raw_events)} LGBS raw_events from {src_path.relative_to(REPO)}")

P("parcel_master.jsonl (300 ENRICHMENT records) intentionally NOT loaded as "
  "raw_events — per operator rule, enrichment never feeds §17 as an event "
  "document. Enrichment attachment is a downstream seam concern.")
P("Coverage: LGBS = general Smith County + most ISDs. Tyler ISD tax sales "
  "(Perdue Brandon, smithcountytaxresale.pdf — also stdlib-reachable PDF) "
  "are NOT in this run; punch-list for a second adapter.")
P("clerk_recordings (publicsearch.us): still ESC-002-blocked — reCAPTCHA + "
  "runtime-injected ko-search-api endpoint require Playwright + a reCAPTCHA "
  "path. Not addressed by this run.")
P("district_court (portal.smith-county.com/Public): also reCAPTCHA-gated.")

# ====================================================================
# 3. RUN STAGED PIPELINE
# ====================================================================
print()
print("== §17 -> §18 -> §19 -> §20 -> seam -> scored leads ==")
try:
    result = run_pipeline_staged.run_staged_pipeline(
        raw_events, evidence_entries=[], workdir=WORKDIR,
        as_of=date(2026, 5, 25), approve_needs_review=True,
    )
except scoring_seam.SemanticGateBlocked as exc:
    print(f"\nHALT — §20 DEPLOY_BLOCKED: {exc}")
    (WORKDIR/"halt_deploy_blocked.json").write_text(
        json.dumps({"verdict":"DEPLOY_BLOCKED","exception":str(exc),
                    "at":NOW},indent=2)+"\n")
    sys.exit(20)
except Exception as exc:
    print(f"\nPIPELINE CRASH — {type(exc).__name__}: {exc}")
    traceback.print_exc()
    sys.exit(1)

verdict = result["semantic_verdict"]
matched = result["matched_leads"]
scored = result["scored_leads"]
print(f"  §20 verdict: {verdict}")
print(f"  §17 debtor_resolved: {len(result['debtor_resolved'])}")
print(f"  §18 leads_base:      {len(result['leads_base'])}")
print(f"  §19 matched_leads:   {len(matched)}")
print(f"  seam scored_leads:   {len(scored)}")

review_required = sum(
    1 for m in matched
    if any(o.get("resolution_status") == "REVIEW_REQUIRED" for o in m.get("owners", []))
)
print(f"  REVIEW_REQUIRED:     {review_required}")

# ====================================================================
# 4. DASHBOARD BUILD (only if §20 didn't block)
# ====================================================================
print()
print("== dashboard build ==")
payload = run_pipeline_staged.build_dashboard_payload(
    scored, semantic_verdict=verdict,
    county="Smith County", state="TX", mode="production",
    build_label=cfg["dashboard"]["build_label"],
)
assert payload["lead_total"] == len(payload["records"]), "Two-Truths drift"
DASH_DATA.parent.mkdir(parents=True, exist_ok=True)
DASH_DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+"\n")
print(f"  dashboard data: {DASH_DATA.relative_to(REPO)}")
print(f"  lead_total: {payload['lead_total']}")
print(f"  pattern_counts: {payload['pattern_counts']}")
print(f"  score_tier_distribution: {payload['score_tier_distribution']}")
print(f"  deal_path_distribution: {payload['deal_path_distribution']}")
print(f"  enrichment_breakdown: {payload['enrichment_breakdown']}")
print(f"  build_label: {payload['build_label']}")

# ====================================================================
# 5. PUNCH LIST + summary
# ====================================================================
punch_path = WORKDIR / "punch_list.json"
punch_path.write_text(json.dumps({
    "generated_at": NOW, "framework_version": "v5.4.0", "county": "smith_tx",
    "semantic_verdict": verdict, "lead_total": payload["lead_total"],
    "review_required_count": review_required,
    "raw_events_loaded": len(raw_events),
    "primary_source": "lgbs_smith_tax_sales",
    "items": punch,
}, indent=2, ensure_ascii=False)+"\n")
print(f"  punch-list saved: {punch_path.relative_to(REPO)} ({len(punch)} items)")

print()
print("===== END-TO-END SUMMARY =====")
print(f"§20 verdict:         {verdict}")
print(f"lead_total:          {payload['lead_total']}")
print(f"REVIEW_REQUIRED:     {review_required}")
print(f"punch-list items:    {len(punch)}")
print(f"dashboard data.json: {DASH_DATA.relative_to(REPO)}")
print(f"staged workdir:      {WORKDIR.relative_to(REPO)}")
