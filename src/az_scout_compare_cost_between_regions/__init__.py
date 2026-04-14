"""az-scout plugin for comparing Azure costs between regions.

Upload an Azure Cost Management export CSV, select a source region and month,
then compare pricing against another Azure region using the public Retail Prices API.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from az_scout.plugin_api import ChatMode, TabDefinition
    from fastapi import APIRouter

_STATIC_DIR = Path(__file__).parent / "static"

try:
    __version__ = _pkg_version("az-scout-plugin-compare-cost-between-regions")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


class CompareCostBetweenRegionsPlugin:
    """Compare Azure costs between regions using Cost Management export data."""

    name = "compare-cost-between-regions"
    version = __version__

    def get_router(self) -> APIRouter | None:
        from az_scout_compare_cost_between_regions.routes import router

        return router

    def get_mcp_tools(self) -> list[Callable[..., Any]] | None:
        from az_scout_compare_cost_between_regions.tools import compare_cost_between_regions

        return [compare_cost_between_regions]

    def get_static_dir(self) -> Path | None:
        return _STATIC_DIR

    def get_tabs(self) -> list[TabDefinition] | None:
        from az_scout.plugin_api import TabDefinition

        return [
            TabDefinition(
                id="compare-cost-between-regions",
                label="Cost Comparison",
                icon="bi bi-currency-exchange",
                js_entry="js/compare-cost-between-regions-tab.js",
                css_entry="css/compare-cost-between-regions.css",
            )
        ]

    def get_chat_modes(self) -> list[ChatMode] | None:
        return None

    def get_system_prompt_addendum(self) -> str | None:
        return (
            "The `compare_cost_between_regions` tool analyses an Azure Cost Management "
            "export CSV to compare costs between two Azure regions. Provide a CSV file "
            "path, year/month, source MeterRegion, and both source and target ARM region "
            "names. It queries the Azure Retail Prices API to estimate target-region costs."
        )


# Module-level instance — referenced by the entry point
plugin = CompareCostBetweenRegionsPlugin()
