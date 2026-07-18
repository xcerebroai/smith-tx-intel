"""
raw_event_passthrough translator — registered under the "custom" name.

Some county scrapers (e.g. `scrapers/lgbs_smith_tax_sales.py`) already emit
rows in the framework-canonical `raw_event_record` shape declared by the
v5.4.0 staged pipeline, rather than the older WRAPPED RAW RECORD shape
(`{raw_record_id, raw_payload}`) that translators like `csv_static_list`
consume. Those sources declare `translator: "custom"` in the county config.

This module supplies that "custom" translator. It is a thin, county-agnostic
bridge: it reads ONLY canonical `raw_event_record` fields (documented in the
staged pipeline's §17 input contract) and the per-source `doc_type_synonyms`
map from county config, and returns the framework signal / parcel / metadata
tuple every translator returns. It contains no county, state, or vendor
literal — the source-specific knowledge stays in the scraper and in config.

Input record shape (raw_event_record, produced by the scraper):

    {
      "raw_event_id": "...",
      "source_id": "...",
      "raw_doc_type": "STRUCK OFF",          # source's literal label
      "canonical_doc_type": "TAX_DEED",       # scraper's best canonical guess
      "instrument_number": "24,171-B",
      "event_date": "2026-06-02",
      "recorded_date": null,
      "source_url": "...",
      "property_refs": {
          "parcel_id": "...", "situs_address": "...",
          "legal_description": null, "case_number": "..."
      },
      "amounts": [{"label": "minimum_bid", "value": 1234.0}, ...],
      "parties": [],
      "parser_confidence": 95
    }

Doc-type resolution (in priority order):
  1. `raw_doc_type` mapped through the source's `doc_type_synonyms` (the
     framework-sanctioned per-county override path).
  2. the record's own `canonical_doc_type`.
The chosen value must be a registry-aligned canonical that
`normalize.normalize_doc_type` recognises; otherwise `_signal_to_raw_event`
downstream would drop the record. The signal therefore carries the resolved
canonical as its `doc_type` and does NOT set a `doc_type_subtype_label`
(which would make the orchestrator re-normalize the raw label and drop it).

Returns: (signals, parcels, per_signal_meta_by_url)
"""

from __future__ import annotations

import hashlib

from scaffold.pipeline.translators import register


def _synonym_lookup(raw_doc_type: str, synonyms: dict) -> str | None:
    """Case-insensitive lookup of a source's literal doc-type label."""
    if not raw_doc_type:
        return None
    for key, val in (synonyms or {}).items():
        if str(key).upper() == raw_doc_type.upper():
            return val
    return None


def _placeholder_parcel_id(address: str, prefix: str) -> str:
    h = hashlib.sha1(address.upper().encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}{h}" if prefix.endswith("-") else f"{prefix}-{h}"


def _split_situs(situs: str) -> tuple[str, str, str]:
    """Split a one-line composite situs into (street, city, zip5).

    Scrapers that fill `property_refs.situs_address` as a single string
    typically compose it as "STREET, CITY, STATE, ZIP" (the parcel-master
    matcher, by contrast, indexes street / city / zip separately, so the
    passthrough must decompose). Returns empty strings for any part that
    can't be recovered; the matcher degrades to a lower-confidence tier or
    to UNENRICHED, never an error.
    """
    if not situs:
        return "", "", ""
    parts = [p.strip() for p in situs.split(",") if p.strip()]
    street = parts[0] if parts else ""
    # ZIP: last part whose leading token is a 5-digit code (ignore +4).
    zip5 = ""
    for p in reversed(parts):
        tok = p.split("-")[0].strip()
        if len(tok) == 5 and tok.isdigit():
            zip5 = tok
            break
    # City: the part after street, when there is a street + city + state/zip.
    city = parts[1] if len(parts) >= 3 else ""
    return street, city, zip5


@register("custom")
def translate_raw_event_passthrough(
    raw_records: list[dict],
    county_config: dict,
    source_config: dict,
) -> tuple[list[dict], list[dict], dict[str, dict]]:
    """Bridge canonical raw_event_record rows into pipeline signals/parcels."""
    synonyms = source_config.get("doc_type_synonyms", {}) or {}
    parcel_id_prefix = source_config.get("parcel_id_prefix", "PARCEL-")
    source_id = source_config.get("_source_id", "custom_source")

    signals: list[dict] = []
    parcels: list[dict] = []
    per_signal_meta_by_url: dict[str, dict] = {}
    seen_parcels: set[str] = set()

    for raw in raw_records:
        refs = raw.get("property_refs") or {}
        address = (refs.get("situs_address") or "").strip()
        street, city, zip5 = _split_situs(address)
        raw_doc_type = (raw.get("raw_doc_type") or "").strip()

        # Resolve the canonical doc type: config synonyms first, then the
        # scraper's own canonical_doc_type as a fallback.
        canonical = (
            _synonym_lookup(raw_doc_type, synonyms)
            or (raw.get("canonical_doc_type") or "").strip()
            or None
        )
        if not canonical:
            # No usable doc type — the staged engine could not route it.
            continue

        doc_number = (
            raw.get("instrument_number")
            or refs.get("case_number")
            or ""
        )
        source_url = (
            raw.get("source_url")
            or f"about:blank/{source_id}/{raw.get('raw_event_id')}"
        )

        # Placeholder parcel (address-keyed) so the parcel-master matcher can
        # attach the real BCAD parcel + owner downstream. If the address is
        # missing we still emit the signal (it scores UNENRICHED).
        parcel_id = None
        if street:
            parcel_id = _placeholder_parcel_id(f"{street}|{zip5}", parcel_id_prefix)
            if parcel_id not in seen_parcels:
                seen_parcels.add(parcel_id)
                parcels.append({
                    "parcel_id": parcel_id,
                    "address": street,
                    "city": city,
                    "zip": zip5,
                    "owner_name": None,
                    "parcel_master_status": "placeholder_pending_enrichment",
                })

        signal_id = "sig_" + hashlib.sha1(
            f"{source_id}|{raw.get('raw_event_id')}|{canonical}".encode("utf-8")
        ).hexdigest()[:16]

        # First amount (e.g. minimum_bid) surfaces on the lead if numeric.
        amount = None
        for a in (raw.get("amounts") or []):
            v = a.get("value")
            if isinstance(v, (int, float)):
                amount = v
                break

        signal = {
            "signal_id": signal_id,
            "raw_record_id": raw.get("raw_event_id"),
            "source_id": source_id,
            "source_url": source_url,
            "doc_type": canonical,
            "doc_number": doc_number,
            "primary_parcel_id": parcel_id,
            "address": street or (address or None),
            "city": city or None,
            "zip": zip5 or None,
            "legal_description": refs.get("legal_description"),
            "filing_date": raw.get("event_date") or raw.get("recorded_date"),
            "parser_confidence": raw.get("parser_confidence", 95),
        }
        if amount is not None:
            signal["amount"] = amount
        signals.append(signal)

        per_signal_meta_by_url[source_url] = {
            "preset_review_flags": [],
            "expected_sale_date": raw.get("event_date"),
            "match_confidence": 0,
            "match_method": "placeholder",
            "address": address,
            "primary_parcel_id": parcel_id,
        }

    return signals, parcels, per_signal_meta_by_url
