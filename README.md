# az-scout-plugin-compare-cost-between-regions

An [az-scout](https://github.com/az-scout/az-scout) plugin for comparing Azure costs between regions using Enterprise Agreement billing exports.

## What it does

Upload your **Detail Enrollment CSV** (usage details) and optionally your **PriceSheet ZIP** to:

1. **Analyse usage** — Aggregate monthly costs per SKU for a selected MeterRegion, with a billing summary breakdown by service category
2. **Compare regions** — Upload your EA PriceSheet ZIP and select a target region to estimate what the same workload would cost in a different Azure region

## 3-step workflow

| Step | Name | Description |
|------|------|-------------|
| **1** | Prerequisites | Select billing account type (EA or MCA) and follow download instructions for the required files |
| **2** | Usage Analysis | Upload the Detail Enrollment CSV, select a source MeterRegion, view aggregated SKU costs and billing summary |
| **3** | Region Comparison | Upload the PriceSheet ZIP, select a target region, compare costs side-by-side |

## Key features

- **2-step SKU matching** — MeterId → source PriceSheet row → region-agnostic product key → target region lookup
- **UoM normalization** — Handles different UnitOfMeasure formats across regions (e.g. `1 TB/Month` vs `100 GB/Month`)
- **BasePrice disambiguation** — Correctly matches pricing tiers when the same product has multiple SkuIDs
- **ARM ↔ MeterRegion mapping** — 65+ region mappings between ARM slugs and PriceSheet abbreviations
- **Sortable tables** — via simpleDatatables with numeric column sorting
- **CSV export** — Download usage analysis and comparison results
- **EA/MCA documentation** — Step-by-step download instructions aligned with Microsoft documentation

## Supported billing account types

- **Enterprise Agreement (EA)** — fully supported
- **MCA / MPA** — download instructions shown, but analysis not yet validated

## Setup

```bash
# Install the plugin (editable mode for development)
cd az-scout-plugin-compare-cost-between-regions
uv sync --group dev
uv pip install -e .

# Start az-scout — the plugin is auto-discovered
az-scout
```

## Structure

```
src/az_scout_compare_cost_between_regions/
├── __init__.py      # Plugin class + module-level instance
├── _log.py          # Logger helper
├── pricing.py       # PriceSheet matching, UoM normalization, cost comparison engine
├── routes.py        # FastAPI routes: /compare-pricesheet, /region-mapping
├── tools.py         # MCP tool: compare_cost_between_regions
└── static/
    ├── css/         # Plugin styles (dark/light theme support)
    ├── html/        # HTML fragment (3-step wizard)
    └── js/          # Tab UI logic, CSV parsing, aggregation
```

## API routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/compare-pricesheet` | Upload PriceSheet ZIP + items JSON, returns comparison results |
| `GET` | `/region-mapping` | Returns ARM ↔ MeterRegion mapping dictionaries |

## MCP tool

- `compare_cost_between_regions(file_path, meter_region, source_arm_region, target_arm_region)` — Analyse a Detail Enrollment CSV and return a comparison structure

## Quality checks

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest
```

## CI/CD

- **CI** (`.github/workflows/ci.yml`): Runs lint and tests on push/PR to `main`
- **Publish** (`.github/workflows/publish.yml`): Triggered on version tags (`v*`), builds package, creates GitHub Release, publishes to PyPI via trusted publishing (OIDC)

## Versioning

Version is derived from git tags via `hatch-vcs`. Tags follow CalVer: `v2026.4.0`, `v2026.4.1`, etc.
