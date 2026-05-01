"""API routes for the Compare Cost Between Regions plugin."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from az_scout.plugin_api import PluginError, PluginValidationError
from fastapi import APIRouter, Form, UploadFile

router = APIRouter()

_MAX_ZIP_SIZE = 500 * 1024 * 1024  # 500 MB


@router.get("/region-mapping")
async def region_mapping() -> dict[str, dict[str, str]]:
    """Return the MeterRegion ↔ ARM region name mappings.

    Available at ``/plugins/compare-cost-between-regions/region-mapping``.
    """
    from az_scout_compare_cost_between_regions.pricing import (
        _ARM_TO_METER_REGION,
        _METER_REGION_TO_ARM,
    )

    return {
        "arm_to_meter": _ARM_TO_METER_REGION,
        "meter_to_arm": _METER_REGION_TO_ARM,
    }


@router.post("/compare-pricesheet")
async def compare_with_pricesheet(
    file: UploadFile,
    items_json: str = Form(...),
    source_region: str = Form(...),
    target_region: str = Form(...),
) -> dict[str, Any]:
    """Upload a PriceSheet ZIP and compare costs between regions.

    Available at ``/plugins/compare-cost-between-regions/compare-pricesheet``.

    The request is ``multipart/form-data`` with:

    - ``file``: PriceSheet ZIP archive containing CSV files
    - ``items_json``: JSON array of aggregated usage items from step 2
    - ``source_region``: Source MeterRegion (e.g. ``SE Central``)
    - ``target_region``: Target MeterRegion (e.g. ``EU West``)
    """
    # Validate file
    if not file.filename:
        raise PluginValidationError("No file provided")
    if not file.filename.lower().endswith(".zip"):
        raise PluginValidationError("File must be a .zip archive")

    content_length_str = file.headers.get("content-length")
    try:
        if content_length_str and int(content_length_str) > _MAX_ZIP_SIZE:
            raise PluginValidationError("ZIP file exceeds 500 MB limit")
    except ValueError:
        pass  # Ignore malformed Content-Length; the post-read check will catch oversized files
    contents = await file.read()
    if len(contents) > _MAX_ZIP_SIZE:
        raise PluginValidationError("ZIP file exceeds 500 MB limit")
    if len(contents) == 0:
        raise PluginValidationError("Uploaded file is empty")

    # Parse items JSON
    try:
        items_raw = json.loads(items_json)
    except json.JSONDecodeError as exc:
        raise PluginValidationError(f"Invalid items JSON: {exc}") from exc

    if not isinstance(items_raw, list) or not items_raw:
        raise PluginValidationError("items_json must be a non-empty JSON array")

    if not source_region or not target_region:
        raise PluginValidationError("Both source and target regions are required")

    from az_scout_compare_cost_between_regions.pricing import (
        arm_region_to_meter_region,
        compute_comparison,
        index_pricesheet_zip,
    )

    # Map ARM region names to PriceSheet MeterRegion format
    ps_source = arm_region_to_meter_region(source_region)
    ps_target = arm_region_to_meter_region(target_region)

    try:
        pricesheet_data = await asyncio.to_thread(index_pricesheet_zip, contents, ps_target)
    except Exception as exc:
        raise PluginError(f"Failed to process PriceSheet ZIP: {exc}") from exc

    return await asyncio.to_thread(
        compute_comparison,
        items_raw,
        ps_source,
        ps_target,
        pricesheet_data,
    )
