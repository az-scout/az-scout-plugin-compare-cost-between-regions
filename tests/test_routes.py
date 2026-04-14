"""Tests for the compare-cost-between-regions API routes."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest
from az_scout.plugin_api import PluginError, PluginValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from az_scout_compare_cost_between_regions.routes import router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(PluginValidationError)
    async def _validation_handler(request: Request, exc: PluginValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(PluginError)
    async def _error_handler(request: Request, exc: PluginError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return TestClient(app, raise_server_exceptions=False)


class TestRegionMappingEndpoint:
    """Tests for GET /region-mapping."""

    def test_returns_both_mappings(self, client: TestClient) -> None:
        resp = client.get("/region-mapping")
        assert resp.status_code == 200
        data = resp.json()
        assert "arm_to_meter" in data
        assert "meter_to_arm" in data
        assert data["arm_to_meter"]["swedencentral"] == "SE Central"
        assert data["meter_to_arm"]["SE Central"] == "swedencentral"


def _make_pricesheet_zip(rows: list[dict[str, str]]) -> bytes:
    """Create a ZIP with a single PriceSheet CSV."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        csv_buf = io.StringIO()
        if rows:
            headers = list(rows[0].keys())
            csv_buf.write(",".join(headers) + "\n")
            for row in rows:
                csv_buf.write(",".join(row.get(h, "") for h in headers) + "\n")
        zf.writestr("PriceSheet_0.csv", csv_buf.getvalue())
    return buf.getvalue()


class TestComparePricesheetEndpoint:
    """Tests for POST /compare-pricesheet."""

    def test_missing_zip_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/compare-pricesheet",
            data={
                "items_json": "[]",
                "source_region": "SE Central",
                "target_region": "EU West",
            },
        )
        assert resp.status_code == 422

    def test_successful_pricesheet_comparison(self, client: TestClient) -> None:
        ps_rows = [
            {
                "MeterId": "abc-123",
                "MeterName": "Test Meter",
                "MeterCategory": "Compute",
                "MeterSubCategory": "",
                "Product": "Compute VMs - Test Meter - SE Central",
                "MeterRegion": "SE Central",
                "PriceType": "Consumption",
                "Term": "",
                "OfferId": "MS-AZR-0017P",
                "UnitPrice": "10.0",
                "UnitOfMeasure": "10 Hours",
                "BasePrice": "15.0",
            },
            {
                "MeterId": "tgt-456",
                "MeterName": "Test Meter",
                "MeterCategory": "Compute",
                "MeterSubCategory": "",
                "Product": "Compute VMs - Test Meter - EU West",
                "MeterRegion": "EU West",
                "PriceType": "Consumption",
                "Term": "",
                "OfferId": "MS-AZR-0017P",
                "UnitPrice": "10.5",
                "UnitOfMeasure": "10 Hours",
                "BasePrice": "15.5",
            },
        ]
        zip_data = _make_pricesheet_zip(ps_rows)

        items = [
            {
                "meter_id": "abc-123",
                "pricing_model": "OnDemand",
                "term": "",
                "offer_id": "MS-AZR-0017P",
                "meter_name": "Test Meter",
                "meter_category": "Compute",
                "meter_sub_category": "",
                "source_cost": 100.0,
                "quantity": 100.0,
            }
        ]

        resp = client.post(
            "/compare-pricesheet",
            data={
                "items_json": json.dumps(items),
                "source_region": "SE Central",
                "target_region": "EU West",
            },
            files={"file": ("PriceSheet.zip", zip_data, "application/zip")},
        )
        assert resp.status_code == 200
        data: dict[str, Any] = resp.json()
        assert data["summary"]["total_source_cost"] == 100.0
        # ratio = (10.5/10) / (10.0/10) = 1.05 → target = 105
        assert data["summary"]["total_estimated_target_cost"] == 105.0
        assert data["summary"]["items_compared"] == 1
        assert data["items"][0]["status"] == "ok"
