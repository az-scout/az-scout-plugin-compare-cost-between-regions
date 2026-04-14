"""Tests for plugin wiring and metadata."""

from __future__ import annotations

from az_scout_compare_cost_between_regions import CompareCostBetweenRegionsPlugin
from az_scout_compare_cost_between_regions.tools import compare_cost_between_regions


class TestCompareCostBetweenRegionsPlugin:
    """Unit tests for CompareCostBetweenRegionsPlugin."""

    def test_name_and_version(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        assert plugin.name == "compare-cost-between-regions"
        assert isinstance(plugin.version, str)

    def test_get_router_returns_router(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        router = plugin.get_router()
        assert router is not None

    def test_get_mcp_tools_includes_tool(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        tools = plugin.get_mcp_tools()
        assert tools is not None
        assert compare_cost_between_regions in tools

    def test_get_static_dir_exists(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        static_dir = plugin.get_static_dir()
        assert static_dir is not None
        assert static_dir.is_dir()

    def test_tab_id_matches_plugin_slug(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        tabs = plugin.get_tabs()
        assert tabs is not None
        assert len(tabs) == 1
        assert tabs[0].id == "compare-cost-between-regions"

    def test_get_chat_modes_returns_none(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        assert plugin.get_chat_modes() is None

    def test_system_prompt_addendum(self) -> None:
        plugin = CompareCostBetweenRegionsPlugin()
        addendum = plugin.get_system_prompt_addendum()
        assert addendum is not None
        assert "compare_cost_between_regions" in addendum
