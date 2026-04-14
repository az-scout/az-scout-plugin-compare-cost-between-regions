"""Tests for the tools module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from az_scout_compare_cost_between_regions.tools import _parse_cost, compare_cost_between_regions


class TestParseCost:
    """Tests for _parse_cost."""

    def test_simple_usd(self) -> None:
        assert _parse_cost("1.23") == 1.23

    def test_euro_symbol(self) -> None:
        assert _parse_cost("€ 67.99") == 67.99

    def test_negative_euro(self) -> None:
        assert _parse_cost("-€ 0.21") == -0.21

    def test_dollar_with_commas(self) -> None:
        assert _parse_cost("$1,234.56") == 1234.56

    def test_european_format(self) -> None:
        assert _parse_cost("1.234,56") == 1234.56

    def test_empty(self) -> None:
        assert _parse_cost("") == 0.0

    def test_dash(self) -> None:
        assert _parse_cost("-") == 0.0

    def test_zero(self) -> None:
        assert _parse_cost("€ 0.00") == 0.0


class TestCompareCostTool:
    """Tests for the MCP tool function."""

    def test_file_not_found(self) -> None:
        result = compare_cost_between_regions(
            "/nonexistent.csv", "SE Central", "swedencentral", "eastus"
        )
        assert "error" in result

    @patch("az_scout_compare_cost_between_regions.pricing.compute_comparison")
    def test_reads_csv(self, mock_compare: MagicMock) -> None:
        import tempfile
        from pathlib import Path

        csv_content = (
            "Date,MeterCategory,MeterSubCategory,MeterName,MeterRegion,"
            "MeterId,PartNumber,PricingModel,Term,OfferId,Cost,Quantity\n"
            "03/15/2025,Storage,Files v2,ZRS Read Ops,SE Central,"
            "abc-123,AAM-85286,OnDemand,,MS-AZR-0017P,0.10,1.0\n"
            "03/16/2025,Storage,Files v2,ZRS Read Ops,SE Central,"
            "abc-123,AAM-85286,OnDemand,,MS-AZR-0017P,0.04,0.5\n"
            "03/15/2025,Storage,Files v2,ZRS Read Ops,Virginia,"
            "abc-123,AAM-85286,OnDemand,,MS-AZR-0017P,0.20,2.0\n"
            "04/01/2025,Storage,Files v2,ZRS Read Ops,SE Central,"
            "abc-123,AAM-85286,OnDemand,,MS-AZR-0017P,0.07,0.7\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            csv_path = f.name

        mock_compare.return_value = {"summary": {}, "items": []}

        try:
            compare_cost_between_regions(csv_path, "SE Central", "swedencentral", "eastus")
            args = mock_compare.call_args
            items = args[0][0]
            # Three SE Central rows (March + April) → aggregated into 1 item
            assert len(items) == 1
            assert items[0]["meter_id"] == "abc-123"
            assert items[0]["pricing_model"] == "OnDemand"
            assert abs(items[0]["source_cost"] - 0.21) < 1e-9
            assert abs(items[0]["quantity"] - 2.2) < 1e-9
        finally:
            Path(csv_path).unlink()

    def test_no_matching_rows(self) -> None:
        import tempfile
        from pathlib import Path

        csv_content = (
            "Date,MeterCategory,MeterSubCategory,MeterName,MeterRegion,"
            "MeterId,PartNumber,PricingModel,Term,OfferId,Cost,Quantity\n"
            "03/15/2025,Storage,,P10,SE Central,"
            "abc-123,AAD-18125,OnDemand,,MS-AZR-0017P,0.14,1.0\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            result = compare_cost_between_regions(csv_path, "Virginia", "swedencentral", "eastus")
            assert "error" in result
        finally:
            Path(csv_path).unlink()
