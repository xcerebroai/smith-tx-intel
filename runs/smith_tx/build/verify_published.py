#!/usr/bin/env python3
"""Verify the published Smith TX dashboard against known-good thresholds.

Catches the "silent-drop" failure mode where CI re-pulls some sources but
not others (e.g. Playwright source fails, parcel CAD enrichment quietly
times out), and the workflow "passes" while publishing a degraded board.

Two distinct checks:

  1. PER-SOURCE LEAD-COUNT THRESHOLDS — every primary source must produce
     at least its expected minimum count of dashboard rows. A regression
     below the floor fails the build.

  2. ENRICHMENT SANITY — the percentage of primary leads with a resolved
     owner_name AND with a property_full_address must each clear a
     minimum. This catches the Greene failure mode (numerically-correct
     board with all-Unknown owners because the CAD enrichment dropped).

Exit codes:
  0  all checks pass
  1  one or more checks failed (prints the failures)
  2  data file missing / unreadable

Usage: python verify_published.py [path/to/data.json]
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

# Per-source minimums — known-good floors as of 2026-05-25. Set ~10-20%
# below the typical observed count so a few records dropping doesn't
# false-alarm, but a complete source failure (zero rows) trips immediately.
SOURCE_MINIMUMS = {
    "lgbs_smith_tax_sales":    25,   # observed 31  (Linebarger taxsales API)
    "pbfcm_smith_tax_resale":    2,   # observed  3  (PBFCM Tyler-ISD struck-off PDF)
    "publicsearch_clerk":      150,   # observed 194 (FC sweep + RP keyword)
}

# Enrichment thresholds applied to PRIMARY leads only.
# Floors are set just above the catastrophic-drop level — not at the
# observed average. The observed averages are:
#   owner_name resolved   ~57%  (LP/AOJ via §17 GR/GE→PL/DF + LGBS/PBFCM via CAD)
#   address    resolved   ~16%  (only LGBS/PBFCM parcel-id rows + FC w/ situs)
# A regression to single-digit % means CAD enrichment silently dropped
# (the Greene failure mode). Threshold catches that without false-positive
# on a small drift.
ENRICHMENT_MINIMUMS = {
    "owner_name_min_pct":   30.0,   # catches CAD + §17 drop
    "address_min_pct":      10.0,   # catches CAD address-join drop
}

# Total-floor checks — defense in depth on top of per-source counts.
TOTAL_MINIMUMS = {
    "lead_total_min":        35000,  # observed 39,453 (synth + primary)
    "default_view_min":      28000,  # observed 31,285 (excl. low-priority)
    "primary_lead_min":         200, # observed 257 (clerk + LGBS + PBFCM)
}

# Delinquent-tax SFTP — separate floor on the enrichment universe so a
# silent SFTP failure (creds missing, drop file empty) is caught even though
# the SOURCES list doesn't include this adapter.
DELINQUENT_TAX_MIN_ACCOUNTS = 35000   # observed 39,592 countywide accounts


def fail(msg: str, errs: list) -> None:
    print(f"  FAIL :: {msg}")
    errs.append(msg)


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1
                 else "dashboard/data.json").resolve()
    if not path.exists():
        print(f"FATAL: {path} does not exist", file=sys.stderr)
        return 2
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FATAL: cannot parse {path}: {exc}", file=sys.stderr)
        return 2

    records = payload.get("records") or []
    errs: list = []

    print(f"verify_published — {path.name}")
    print(f"  records loaded: {len(records):,}")
    print(f"  refresh_date:   {payload.get('refresh_date')}")
    print(f"  drop_label:     {payload.get('delinquent_tax_drop_label')}")

    # ----- Per-source primary-lead counts -----
    # Tally by signals[0].source_id since each record's primary signal
    # carries the source provenance.
    print("\n[1] Per-source primary-lead counts:")
    src_counts: dict = Counter()
    for r in records:
        sigs = r.get("signals") or []
        if not sigs:
            continue
        src = sigs[0].get("source_id") or "unknown"
        src_counts[src] += 1
    for src, expect_min in sorted(SOURCE_MINIMUMS.items()):
        got = src_counts.get(src, 0)
        ok = got >= expect_min
        marker = "PASS" if ok else "FAIL"
        print(f"  {marker} :: {src:<30}  got {got:>5,}  min {expect_min:>5,}")
        if not ok:
            errs.append(f"source {src} below minimum: {got} < {expect_min}")

    # ----- Total-floor checks -----
    print("\n[2] Total-floor checks:")
    for key, expect_min in TOTAL_MINIMUMS.items():
        actual_field = {
            "lead_total_min":   "lead_total",
            "default_view_min": "default_view_lead_count",
            "primary_lead_min": "primary_lead_count",
        }[key]
        got = payload.get(actual_field) or 0
        ok = got >= expect_min
        marker = "PASS" if ok else "FAIL"
        print(f"  {marker} :: {actual_field:<30}  got {got:>6,}  min {expect_min:>6,}")
        if not ok:
            errs.append(f"{actual_field} below minimum: {got} < {expect_min}")

    # ----- Enrichment sanity (Greene failure-mode guard) -----
    print("\n[3] Enrichment sanity (primary leads with resolved owner + address):")
    primary = [r for r in records if r.get("provenance") == "primary_event"]
    n_prim  = len(primary)
    if n_prim == 0:
        fail("no primary_event leads at all — primary pipeline broken", errs)
    else:
        n_owner = sum(1 for r in primary if (r.get("owner_name") or "").strip())
        n_addr  = sum(1 for r in primary
                       if (r.get("property_full_address") or "").strip())
        pct_owner = 100.0 * n_owner / n_prim
        pct_addr  = 100.0 * n_addr  / n_prim
        ok_owner = pct_owner >= ENRICHMENT_MINIMUMS["owner_name_min_pct"]
        ok_addr  = pct_addr  >= ENRICHMENT_MINIMUMS["address_min_pct"]
        print(f"  {'PASS' if ok_owner else 'FAIL'} :: owner_name resolved:        "
              f"{n_owner:>4,}/{n_prim:<4,} = {pct_owner:>5.1f}%  "
              f"(min {ENRICHMENT_MINIMUMS['owner_name_min_pct']}%)")
        print(f"  {'PASS' if ok_addr  else 'FAIL'} :: property_address resolved:  "
              f"{n_addr:>4,}/{n_prim:<4,} = {pct_addr:>5.1f}%  "
              f"(min {ENRICHMENT_MINIMUMS['address_min_pct']}%)")
        if not ok_owner:
            errs.append(f"owner_name resolution {pct_owner:.1f}% below "
                        f"min {ENRICHMENT_MINIMUMS['owner_name_min_pct']}% "
                        f"— CAD enrichment likely dropped")
        if not ok_addr:
            errs.append(f"property_address resolution {pct_addr:.1f}% below "
                        f"min {ENRICHMENT_MINIMUMS['address_min_pct']}% "
                        f"— CAD enrichment likely dropped")

    # ----- Delinquent-tax SFTP floor (separate enrichment channel) -----
    print("\n[4] Delinquent-tax SFTP coverage:")
    dlq_universe = payload.get("delinquent_tax_universe") or 0
    ok = dlq_universe >= DELINQUENT_TAX_MIN_ACCOUNTS
    marker = "PASS" if ok else "FAIL"
    print(f"  {marker} :: delinquent_tax_universe   got {dlq_universe:>7,}  "
          f"min {DELINQUENT_TAX_MIN_ACCOUNTS:>7,}")
    if not ok:
        errs.append(f"delinquent_tax_universe below minimum: "
                    f"{dlq_universe} < {DELINQUENT_TAX_MIN_ACCOUNTS} "
                    f"— SFTP pull likely failed (check secret)")

    # ----- Verdict -----
    print()
    if errs:
        print(f"VERIFY FAILED — {len(errs)} issue(s):")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("VERIFY OK — all thresholds met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
