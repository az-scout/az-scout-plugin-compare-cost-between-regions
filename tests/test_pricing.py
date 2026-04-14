"""Tests for the pricing module."""

from __future__ import annotations

import io
import zipfile

from az_scout_compare_cost_between_regions.pricing import (
    compute_comparison,
    index_pricesheet_zip,
)


def _make_pricesheet_zip(rows: list[dict[str, str]]) -> bytes:
    """Create a ZIP with a single PriceSheet CSV from dicts."""
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


class TestIndexPricesheetZip:
    """Tests for index_pricesheet_zip."""

    def test_builds_both_indexes(self) -> None:
        rows = [
            {
                "MeterId": "src-meter-1",
                "MeterName": "Test Meter",
                "MeterCategory": "Compute",
                "MeterSubCategory": "VMs",
                "Product": "VMs - Test Meter - SE Central",
                "MeterRegion": "SE Central",
                "PriceType": "Consumption",
                "Term": "",
                "OfferId": "MS-AZR-0017P",
                "UnitPrice": "10.0",
                "UnitOfMeasure": "10 Hours",
                "BasePrice": "15.0",
            },
            {
                "MeterId": "tgt-meter-1",
                "MeterName": "Test Meter",
                "MeterCategory": "Compute",
                "MeterSubCategory": "VMs",
                "Product": "VMs - Test Meter - EU West",
                "MeterRegion": "EU West",
                "PriceType": "Consumption",
                "Term": "",
                "OfferId": "MS-AZR-0017P",
                "UnitPrice": "12.0",
                "UnitOfMeasure": "10 Hours",
                "BasePrice": "18.0",
            },
        ]
        source_idx, target_idx = index_pricesheet_zip(_make_pricesheet_zip(rows), "EU West")
        # Source index has both MeterIds
        assert "src-meter-1" in source_idx
        assert "tgt-meter-1" in source_idx
        # Target index has one product key entry (list of entries)
        assert len(target_idx) == 1
        key = list(target_idx.keys())[0]
        assert len(target_idx[key]) == 1
        assert target_idx[key][0] == (12.0, 10.0, 18.0)

    def test_empty_zip(self) -> None:
        source_idx, target_idx = index_pricesheet_zip(_make_pricesheet_zip([]), "EU West")
        assert source_idx == {}
        assert target_idx == {}


class TestComputeComparison:
    """Tests for compute_comparison."""

    def test_zero_cost_no_pricesheet(self) -> None:
        items = [{"meter_id": "abc-123", "source_cost": 0.0, "quantity": 0.0}]
        result = compute_comparison(items, "SE Central", "EU West")
        assert result["items"][0]["status"] == "zero_cost"
        assert result["summary"]["items_compared"] == 1

    def test_not_found_no_pricesheet(self) -> None:
        items = [
            {
                "meter_id": "abc-123",
                "pricing_model": "OnDemand",
                "term": "",
                "offer_id": "MS-AZR-0017P",
                "meter_name": "Test",
                "meter_category": "Compute",
                "meter_sub_category": "",
                "source_cost": 100.0,
                "quantity": 10.0,
            }
        ]
        result = compute_comparison(items, "SE Central", "EU West")
        assert result["items"][0]["status"] == "not_found"
        assert result["summary"]["items_not_found"] == 1

    def test_matched_with_uom_normalization(self) -> None:
        """Full 2-step match: MeterId→source row→product key→target."""
        from az_scout_compare_cost_between_regions.pricing import _make_product_key

        # Source PS row (indexed by MeterId)
        source_index: dict[str, list[dict[str, str]]] = {
            "abc-123": [
                {
                    "MeterId": "abc-123",
                    "MeterName": "D4s v5",
                    "Product": "VMs Dsv5 Series - D4s v5 - SE Central",
                    "MeterRegion": "SE Central",
                    "PriceType": "Consumption",
                    "Term": "",
                    "OfferId": "MS-AZR-0017P",
                    "UnitPrice": "1.60",
                    "UnitOfMeasure": "10 Hours",
                    "BasePrice": "2.20",
                },
            ],
        }

        # Target PS entry: same product, different UoM (list)
        key = _make_product_key(
            "VMs Dsv5 Series - D4s v5",
            "D4s v5",
            "Consumption",
            "",
            "MS-AZR-0017P",
        )
        target_index = {key: [(16.80, 100.0, 23.10)]}  # 100 Hours UoM

        items = [
            {
                "meter_id": "abc-123",
                "pricing_model": "OnDemand",
                "term": "",
                "offer_id": "MS-AZR-0017P",
                "meter_name": "D4s v5",
                "meter_category": "Compute",
                "meter_sub_category": "",
                "source_cost": 100.0,
                "quantity": 625.0,
            }
        ]

        result = compute_comparison(items, "SE Central", "EU West", (source_index, target_index))
        s = result["summary"]
        assert s["items_compared"] == 1
        assert s["items_not_found"] == 0

        item = result["items"][0]
        assert item["status"] == "ok"
        # src_rate = 1.60/10 = 0.16, tgt_rate = 16.80/100 = 0.168
        # ratio = 0.168/0.16 = 1.05, est = 100 * 1.05 = 105
        assert abs(item["estimated_target_cost"] - 105.0) < 0.01
        assert abs(item["price_ratio"] - 1.05) < 0.001
