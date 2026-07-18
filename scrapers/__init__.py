"""
County-specific scraper adapters for the Smith County, TX (smith_tx) build.

Each module here drives one source declared in
`config/counties/smith_tx.json`. The modules are intentionally thin
wrappers that delegate protocol handling (ArcGIS pagination, retries,
error envelopes, etc.) to the framework-shared adapters under
`scaffold/scrapers/`, and own only the Smith-County-specific field
normalization. The split keeps the framework code county-agnostic while
the county wiring stays here.

Adapters:
  - parcel_master.py — ENRICHMENT FOUNDATION. Smith County GIS "Tax
    Parcels" ArcGIS REST layer. Emits parcel records only; never a lead.

Phase 3+ primary-event-source adapters (clerk recordings, district
court) are added here as Build Mode progresses.

Translators:
  - raw_event_translator.py — registers the "custom" translator that
    bridges scraper rows already in canonical raw_event_record shape
    (e.g. lgbs_smith_tax_sales) into pipeline signals. Imported here so
    the registration runs on `import scrapers`.
"""

# Register county-side translators on package import so build_leads can
# resolve `translator: "custom"` sources.
from scrapers import raw_event_translator  # noqa: E402,F401
