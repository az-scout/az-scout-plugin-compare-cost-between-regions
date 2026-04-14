"""MCP tools for comparing Azure costs between regions."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


def compare_cost_between_regions(
    file_path: str,
    meter_region: str,
    source_arm_region: str,
    target_arm_region: str,
) -> dict[str, Any]:
    """Compare Azure resource costs between two regions using a detailed usage CSV export.

    Reads a detailed enrollment/usage CSV exported from Azure Cost
    Management, filters rows by ``meter_region``, aggregates by the
    composite key (MeterId, PricingModel, Term, OfferId), then returns
    a comparison structure.  The billing month is auto-detected from
    the ``Date`` column.

    Args:
        file_path: Path to the Azure Cost Management detailed usage CSV file.
        meter_region: Source MeterRegion value exactly as it appears in the CSV
            (e.g. ``SE Central``).
        source_arm_region: ARM region name for the source
            (e.g. ``swedencentral``).
        target_arm_region: ARM region name for the comparison target
            (e.g. ``eastus``).

    Returns:
        A dict with ``summary`` (totals, difference, percentage change)
        and ``items`` (per-SKU pricing comparison).
    """
    from az_scout_compare_cost_between_regions.pricing import compute_comparison

    path = Path(file_path)
    if not path.is_file():
        return {"error": f"File not found: {file_path}"}

    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())

    # Aggregate by composite key
    agg: dict[str, dict[str, Any]] = {}
    for row in reader:
        if row.get("MeterRegion") != meter_region:
            continue

        meter_id = (row.get("MeterId") or "").strip()
        if not meter_id:
            continue

        pricing_model = (row.get("PricingModel") or "").strip()
        term = (row.get("Term") or "").strip()
        offer_id = (row.get("OfferId") or "").strip()
        key = f"{meter_id}|{pricing_model}|{term}|{offer_id}"

        if key not in agg:
            agg[key] = {
                "meter_id": meter_id,
                "pricing_model": pricing_model,
                "term": term,
                "offer_id": offer_id,
                "meter_name": row.get("MeterName", ""),
                "meter_category": row.get("MeterCategory", ""),
                "meter_sub_category": row.get("MeterSubCategory", ""),
                "part_number": row.get("PartNumber", ""),
                "source_cost": 0.0,
                "quantity": 0.0,
            }

        agg[key]["source_cost"] += _parse_cost(row.get("Cost", "0"))
        agg[key]["quantity"] += float(row.get("Quantity") or 0)

    items = list(agg.values())
    if not items:
        return {"error": f"No items found for MeterRegion={meter_region}"}

    return compute_comparison(items, source_arm_region, target_arm_region)


def _parse_cost(value: str) -> float:
    """Parse a cost string that may contain currency symbols."""
    cleaned = re.sub(r"[€$£¥\xa0\s]", "", value.strip())
    if not cleaned or cleaned == "-":
        return 0.0
    # European format: comma as decimal separator (1.234,56)
    if re.search(r",\d{1,2}$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # US format: period as decimal (1,234.56)
        cleaned = cleaned.replace(",", "")
    return float(cleaned)
