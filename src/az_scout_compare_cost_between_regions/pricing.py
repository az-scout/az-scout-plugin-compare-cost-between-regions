"""PriceSheet-based cost comparison logic for Azure regions."""

from __future__ import annotations

import contextlib
import csv
import io
import re
import zipfile
from typing import Any

from az_scout_compare_cost_between_regions._log import logger

# PricingModel (enrollment) → PriceType (PriceSheet) mapping
_PRICING_MODEL_TO_PRICE_TYPE: dict[str, str] = {
    "OnDemand": "Consumption",
    "Reservation": "Reservation",
    "SavingsPlan": "SavingsPlan",
    "Spot": "Consumption",
}

# ARM region name → PriceSheet MeterRegion mapping.
# ARM uses lowercase slugs (e.g. "westeurope"), PriceSheet uses abbreviated
# display names (e.g. "EU West").
_ARM_TO_METER_REGION: dict[str, str] = {
    "australiacentral": "AU Central",
    "australiacentral2": "AU Central 2",
    "australiaeast": "AU East",
    "australiasoutheast": "AU Southeast",
    "austriaeast": "AT East",
    "belgiumcentral": "BE Central",
    "brazilsouth": "BR South",
    "brazilsoutheast": "BR Southeast",
    "canadacentral": "CA Central",
    "canadaeast": "CA East",
    "centralindia": "IN Central",
    "centralus": "US Central",
    "chilecentral": "CL Central",
    "denmarkeast": "DK East",
    "eastasia": "AP East",
    "eastus": "US East",
    "eastus2": "US East 2",
    "francecentral": "FR Central",
    "francesouth": "FR South",
    "germanywestcentral": "DE West Central",
    "germanynorth": "DE North",
    "indonesiacentral": "ID Central",
    "israelcentral": "IL Central",
    "italynorth": "IT North",
    "japaneast": "JA East",
    "japanwest": "JA West",
    "koreacentral": "KR Central",
    "koreasouth": "KR South",
    "malaysiasouth": "MY West",
    "mexicocentral": "MX Central",
    "newzealandnorth": "NZ North",
    "northcentralus": "US North Central",
    "northeurope": "EU North",
    "norwayeast": "NO East",
    "norwaywest": "NO West",
    "polandcentral": "PL Central",
    "qatarcentral": "QA Central",
    "southafricanorth": "ZA North",
    "southafricawest": "ZA West",
    "southcentralus": "US South Central",
    "southeastasia": "AP Southeast",
    "southindia": "IN South",
    "spaincentral": "ES Central",
    "swedencentral": "SE Central",
    "swedensouth": "SE South",
    "switzerlandnorth": "CH North",
    "switzerlandwest": "CH West",
    "taiwannorth": "TW North",
    "taiwannorthwest": "TW Northwest",
    "uaecentral": "AE Central",
    "uaenorth": "AE North",
    "uksouth": "UK South",
    "ukwest": "UK West",
    "westcentralus": "US West Central",
    "westeurope": "EU West",
    "westindia": "IN West",
    "westus": "US West",
    "westus2": "US West 2",
    "westus3": "US West 3",
}

# Reverse mapping: MeterRegion → ARM region name
_METER_REGION_TO_ARM: dict[str, str] = {v: k for k, v in _ARM_TO_METER_REGION.items()}


def arm_region_to_meter_region(arm_name: str) -> str:
    """Convert an ARM region name to PriceSheet MeterRegion format.

    Falls through unchanged if no mapping is found (allows passing
    MeterRegion values directly).
    """
    return _ARM_TO_METER_REGION.get(arm_name.lower().strip(), arm_name)


# ─────────────────────────────────────────────────────────────────────────────
# PriceSheet-based matching
#
# Matching strategy (2-step MeterId → Product-key):
#
# 1. **Source lookup** — Use the enrollment MeterId (which is region-specific)
#    to find the corresponding row in the PriceSheet for the source region.
#    Match on MeterId + PriceType + OfferId.
#
# 2. **Build product key** — From that source PriceSheet row, extract a
#    region-agnostic key by stripping the region suffix from the ``Product``
#    column (e.g. "Files v2 - ZRS - Read Operations - SE Central" →
#    "Files v2 - ZRS - Read Operations").  The full key is:
#    (product_base, MeterName, PriceType, Term, OfferId)
#
# 3. **Target lookup** — Find the same product key in the target region's
#    PriceSheet rows to get the target UnitPrice.
#
# 4. **UoM normalization** — UnitOfMeasure can differ between regions both
#    in the numeric prefix (``"10 Hours"`` vs ``"100 Hours"``) **and** in
#    the unit type (``"1 TB/Month"`` vs ``"100 GB/Month"``).  We normalise
#    the full UoM string to a single canonical multiplier that accounts for
#    both the numeric prefix and the unit-type scale factor
#    (e.g. 1 TB = 1024 GB, 1 PiB = 1024 TiB).
#    The target cost is: source_cost × (tgt_rate / src_rate)
#    where rate = UnitPrice / canonical_multiplier.
# ─────────────────────────────────────────────────────────────────────────────

# Unit-type scale factors to a canonical base.
# Groups: data sizes → bytes, time → hours, counts → 1.
# We only need *relative* factors within the same dimension so the absolute
# value does not matter — only the ratio between source and target matters.
_UNIT_SCALE: dict[str, float] = {
    # Data sizes (base: GB)
    "mb": 1e-3,
    "gb": 1.0,
    "tb": 1e3,
    "pb": 1e6,
    "gib": 1.073741824,  # 1 GiB = 1.073… GB
    "tib": 1.073741824e3,  # 1 TiB ≈ 1099.51 GB
    "pib": 1.073741824e6,  # 1 PiB
    # Time (base: hours)
    "second": 1 / 3600,
    "seconds": 1 / 3600,
    "minute": 1 / 60,
    "minutes": 1 / 60,
    "hour": 1.0,
    "hours": 1.0,
    "day": 24.0,
    "days": 24.0,
    "month": 730.0,  # average month
    "months": 730.0,
    "year": 8760.0,
    # Counts
    "rotations": 1.0,
    "count": 1.0,
    "unit": 1.0,
    "api calls": 1.0,
    "iops": 1.0,
}


def _parse_uom(uom: str) -> float:
    """Parse a UnitOfMeasure string into a canonical multiplier.

    The UoM format is ``"<number> <unit_parts>"`` where unit_parts can be
    compound like ``"GB/Month"`` or ``"TB Hours"``.

    Returns a single float representing the canonical scale so that
    ``UnitPrice / _parse_uom(UoM)`` gives a comparable per-base-unit rate.

    Examples:
        ``"10 Hours"``     → 10 × 1 = 10
        ``"100 GB/Month"`` → 100 × 1 × 730 = 73000
        ``"1 TB/Month"``   → 1 × 1000 × 730 = 730000
        ``"10000"``        → 10000
    """
    if not uom:
        return 1.0

    s = uom.strip()

    # Extract numeric prefix
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(.*)", s)
    if not m:
        return 1.0

    multiplier = float(m.group(1))
    unit_str = m.group(2).strip()

    if not unit_str:
        return multiplier

    # Split compound units: "GB/Month" → ["GB", "Month"]
    #                       "TB Hours" → ["TB", "Hours"]
    #                       "GB Seconds" → ["GB", "Seconds"]
    parts = re.split(r"[/\s]+", unit_str)

    scale = 1.0
    for part in parts:
        part_lower = part.lower()
        factor = _UNIT_SCALE.get(part_lower)
        if factor is not None:
            scale *= factor
        # Unknown unit parts are ignored (scale factor = 1)

    return multiplier * scale


def _strip_region_suffix(product: str, region: str) -> str:
    """Remove ``' - <region>'`` suffix (and optional ``' - Expired'``) from Product."""
    s = product.strip()
    if s.endswith(" - Expired"):
        s = s[: -len(" - Expired")]
    suffix = " - " + region
    if s.endswith(suffix):
        s = s[: -len(suffix)]
    return s


def _make_product_key(
    product_base: str,
    meter_name: str,
    price_type: str,
    term: str,
    offer_id: str,
) -> str:
    """Build the region-agnostic key used to match PriceSheet rows across regions."""
    return "|".join(
        [
            product_base.strip().lower(),
            meter_name.strip().lower(),
            price_type.strip().lower(),
            term.strip().lower(),
            offer_id.strip().lower(),
        ]
    )


# Dataclass-like tuple for PriceSheet entries
_PsEntry = tuple[float, float, float]  # (unit_price, uom_multiplier, base_price)


def index_pricesheet_zip(
    zip_data: bytes,
    target_region: str,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[_PsEntry]]]:
    """Parse PriceSheet CSVs from a ZIP and build two indexes.

    Returns ``(source_by_meter_id, target_by_product_key)`` where:

    - **source_by_meter_id**: ``{meter_id: [row_dicts]}`` — all rows,
      used to look up the source-region row by enrollment MeterId.
    - **target_by_product_key**: ``{product_key: [(unit_price, uom_mult, base_price), ...]}``
      — target-region rows indexed by the region-agnostic product key.
      Multiple entries per key are kept to allow disambiguation by
      ``BasePrice`` when the same product has different pricing tiers.
    """
    source_index: dict[str, list[dict[str, str]]] = {}
    target_index: dict[str, list[_PsEntry]] = {}
    target_lower = target_region.strip().lower()

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        csv_names = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
        logger.debug("PriceSheet ZIP contains %d CSV files", len(csv_names))

        for csv_name in csv_names:
            with zf.open(csv_name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8-sig")
                reader = csv.DictReader(text)
                for row in reader:
                    mid = (row.get("MeterId") or "").strip()
                    region = (row.get("MeterRegion") or "").strip()

                    # Source index: all rows by MeterId
                    if mid:
                        source_index.setdefault(mid, []).append(row)

                    # Target index: only target region rows
                    if region.lower() == target_lower:
                        product = row.get("Product", "")
                        product_base = _strip_region_suffix(product, region)
                        key = _make_product_key(
                            product_base,
                            row.get("MeterName", ""),
                            row.get("PriceType", ""),
                            row.get("Term", ""),
                            row.get("OfferId", ""),
                        )
                        with contextlib.suppress(ValueError, TypeError):
                            uom = _parse_uom(row.get("UnitOfMeasure", ""))
                            base_price = float(row.get("BasePrice", 0) or 0)
                            target_index.setdefault(key, []).append(
                                (
                                    float(row.get("UnitPrice", 0)),
                                    uom,
                                    base_price,
                                )
                            )

    logger.debug(
        "PriceSheet indexed: %d MeterIds, %d target entries for %r",
        len(source_index),
        len(target_index),
        target_region,
    )
    return source_index, target_index


def compute_comparison(
    items: list[dict[str, Any]],
    source_region: str,
    target_region: str,
    pricesheet_data: (
        tuple[dict[str, list[dict[str, str]]], dict[str, list[_PsEntry]]] | None
    ) = None,
) -> dict[str, Any]:
    """Compute a side-by-side cost comparison using PriceSheet data.

    *items* are aggregated enrollment rows (from step 2).
    *pricesheet_data* is the ``(source_index, target_index)`` tuple
    returned by ``index_pricesheet_zip``, or ``None`` if no PriceSheet
    was uploaded (all items marked ``not_found``).

    For each item:
    1. Look up the enrollment MeterId in the source PriceSheet index
    2. From the matched source row, strip the region from Product and
       build a product key
    3. Look up that key in the target index to get target UnitPrice
    4. Normalize both prices by their UoM multiplier and compute the ratio
    5. ``target_cost = source_cost × (tgt_rate / src_rate)``
    """
    source_index: dict[str, list[dict[str, str]]] = {}
    target_index: dict[str, list[_PsEntry]] = {}
    if pricesheet_data is not None:
        source_index, target_index = pricesheet_data

    results: list[dict[str, Any]] = []
    total_source = 0.0
    total_source_all = 0.0
    total_target = 0.0
    found = 0
    not_found = 0

    for item in items:
        source_cost = float(item.get("source_cost", 0))
        total_source_all += source_cost

        pricing_model = item.get("pricing_model", "")
        price_type = _PRICING_MODEL_TO_PRICE_TYPE.get(pricing_model, pricing_model)
        meter_id = item.get("meter_id", "")

        row: dict[str, Any] = {
            "meter_id": meter_id,
            "pricing_model": pricing_model,
            "term": item.get("term", ""),
            "offer_id": item.get("offer_id", ""),
            "meter_name": item.get("meter_name", ""),
            "meter_category": item.get("meter_category", ""),
            "meter_sub_category": item.get("meter_sub_category", ""),
            "part_number": item.get("part_number", ""),
            "source_cost": round(source_cost, 4),
            "quantity": round(float(item.get("quantity", 0)), 6),
        }

        # ── Step A: find source PriceSheet row via MeterId ──────────────
        src_ps_row = _find_source_ps_row(
            source_index, meter_id, price_type, item.get("offer_id", "")
        )

        # ── Step B: build product key and find target entry ─────────────
        tgt_entry: _PsEntry | None = None
        src_uom_mult = 1.0
        if src_ps_row:
            product = src_ps_row.get("Product", "")
            region = src_ps_row.get("MeterRegion", "")
            product_base = _strip_region_suffix(product, region)
            key = _make_product_key(
                product_base,
                src_ps_row.get("MeterName", ""),
                src_ps_row.get("PriceType", ""),
                src_ps_row.get("Term", ""),
                src_ps_row.get("OfferId", ""),
            )
            src_uom_mult = _parse_uom(src_ps_row.get("UnitOfMeasure", ""))

            # Pick the best target entry — disambiguate by BasePrice
            tgt_entries = target_index.get(key, [])
            if len(tgt_entries) == 1:
                tgt_entry = tgt_entries[0]
            elif len(tgt_entries) > 1:
                src_base = float(src_ps_row.get("BasePrice", 0) or 0)
                tgt_entry = _pick_best_target(tgt_entries, src_base, src_uom_mult)

        # ── Step C: compute target cost ─────────────────────────────────
        if source_cost == 0 and tgt_entry is None:
            found += 1
            total_source += source_cost
            row.update(
                target_unit_price=None,
                estimated_target_cost=0.0,
                price_ratio=None,
                difference=0.0,
                status="zero_cost",
            )
        elif tgt_entry is not None and src_ps_row is not None:
            tgt_unit, tgt_uom_mult, _tgt_base = tgt_entry
            src_unit = float(src_ps_row.get("UnitPrice", 0) or 0)

            # Normalize to per-base-unit rates
            src_rate = src_unit / src_uom_mult if src_uom_mult else src_unit
            tgt_rate = tgt_unit / tgt_uom_mult if tgt_uom_mult else tgt_unit

            if src_rate > 0:
                ratio = tgt_rate / src_rate
                est = source_cost * ratio
            else:
                ratio = None
                est = 0.0

            total_target += est
            found += 1
            total_source += source_cost
            row.update(
                target_unit_price=round(tgt_rate, 8),
                estimated_target_cost=round(est, 4),
                price_ratio=round(ratio, 6) if ratio is not None else None,
                difference=round(est - source_cost, 4),
                status="ok",
            )
        else:
            not_found += 1
            row.update(
                target_unit_price=None,
                estimated_target_cost=None,
                price_ratio=None,
                difference=None,
                status="not_found",
            )

        results.append(row)

    pct = round((total_target - total_source) / total_source * 100, 2) if total_source else 0.0

    return {
        "summary": {
            "source_region": source_region,
            "target_region": target_region,
            "total_source_cost": round(total_source, 2),
            "total_source_cost_all": round(total_source_all, 2),
            "total_estimated_target_cost": round(total_target, 2),
            "total_difference": round(total_target - total_source, 2),
            "percentage_change": pct,
            "items_compared": found,
            "items_not_found": not_found,
            "total_items": len(items),
        },
        "items": results,
    }


def _pick_best_target(
    entries: list[_PsEntry],
    src_base_price: float,
    src_uom_mult: float,
) -> _PsEntry:
    """Pick the best target entry when multiple match the same product key.

    When the same product has multiple pricing tiers (different SkuIDs)
    that share the same product-level matching key, we disambiguate by
    comparing ``BasePrice`` values.  We normalise each entry's BasePrice
    by its UoM multiplier and pick the one closest to the source's
    normalised BasePrice.
    """
    src_norm = src_base_price / src_uom_mult if src_uom_mult else src_base_price

    best: _PsEntry | None = None
    best_dist = float("inf")
    for entry in entries:
        _unit, uom, base = entry
        norm = base / uom if uom else base
        dist = abs(norm - src_norm)
        if dist < best_dist:
            best_dist = dist
            best = entry

    # best is guaranteed non-None because entries is non-empty
    return best  # type: ignore[return-value]


def _find_source_ps_row(
    source_index: dict[str, list[dict[str, str]]],
    meter_id: str,
    price_type: str,
    offer_id: str,
) -> dict[str, str] | None:
    """Find the best matching PriceSheet row for an enrollment MeterId."""
    ps_rows = source_index.get(meter_id)
    if not ps_rows:
        return None

    # Best match: PriceType + OfferId
    for psr in ps_rows:
        if psr.get("PriceType", "") == price_type and psr.get("OfferId", "") == offer_id:
            return psr

    # Fallback: PriceType only
    for psr in ps_rows:
        if psr.get("PriceType", "") == price_type:
            return psr

    # Last resort: first row
    return ps_rows[0]
