"""Exploration script: validate 2-step matching between enrollment and PriceSheet.

Matching strategy:
1. From enrollment, get MeterId for each SKU (region-specific identifier)
2. Look up MeterId in PriceSheet to find the source-region row
3. From that source row, extract the region-agnostic key:
   - Product with region suffix stripped
   - MeterName, PriceType, Term, OfferId
4. Look up that key in the target region's PriceSheet rows
5. Compute target cost using the price ratio, normalized by UnitOfMeasure:
   target_cost = source_cost × (tgt_UnitPrice / tgt_UoM) / (src_UnitPrice / src_UoM)
"""
import csv
import glob
import os
import re
import statistics

ENROLLMENT = "/Users/lrivallain/OneDrive - Microsoft/Documents/Customers/Opella/2025_04_Multi region thinking/Detail_Enrollment_8607656_202603_en.csv"
PS_DIR = "/Users/lrivallain/OneDrive - Microsoft/Documents/Customers/Opella/2025_04_Multi region thinking/ArmPriceSheet_Enrollment_8607656_202603/"
TARGET_REGION = "EU West"

PRICING_MODEL_MAP = {
    "OnDemand": "Consumption",
    "SavingsPlan": "SavingsPlan",
    "Reservation": "Reservation",
}


def extract_uom_multiplier(uom: str) -> float:
    """Full UoM normalizer matching the production _parse_uom logic."""
    if not uom:
        return 1.0
    s = uom.strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(.*)", s)
    if not m:
        return 1.0
    multiplier = float(m.group(1))
    unit_str = m.group(2).strip()
    if not unit_str:
        return multiplier

    UNIT_SCALE = {
        "mb": 1e-3, "gb": 1.0, "tb": 1e3, "pb": 1e6,
        "gib": 1.073741824, "tib": 1.073741824e3, "pib": 1.073741824e6,
        "second": 1/3600, "seconds": 1/3600,
        "minute": 1/60, "minutes": 1/60,
        "hour": 1.0, "hours": 1.0,
        "day": 24.0, "days": 24.0,
        "month": 730.0, "months": 730.0,
        "year": 8760.0,
        "rotations": 1.0, "count": 1.0, "unit": 1.0,
        "api calls": 1.0, "iops": 1.0,
    }

    parts = re.split(r"[/\s]+", unit_str)
    scale = 1.0
    for part in parts:
        factor = UNIT_SCALE.get(part.lower())
        if factor is not None:
            scale *= factor
    return multiplier * scale


def strip_region_from_product(product: str, region: str) -> str:
    """Remove ' - Region' suffix (and optional ' - Expired') from Product."""
    s = product.strip()
    if s.endswith(" - Expired"):
        s = s[: -len(" - Expired")]
    suffix = " - " + region
    if s.endswith(suffix):
        s = s[: -len(suffix)]
    return s


def make_key(product_base, meter_name, price_type, term, offer_id):
    return (
        product_base.strip().lower(),
        meter_name.strip().lower(),
        price_type.strip().lower(),
        term.strip().lower(),
        offer_id.strip().lower(),
    )


# ── Step 1: Load enrollment ────────────────────────────────────────────
print("=" * 80)
print("STEP 1: Load enrollment data for SE Central")
print("=" * 80)

enrollment = {}
with open(ENROLLMENT, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if row.get("MeterRegion") != "SE Central":
            continue
        mid = row.get("MeterId", "").strip()
        if not mid:
            continue
        if mid not in enrollment:
            enrollment[mid] = {
                "meter_name": row.get("MeterName", ""),
                "meter_category": row.get("MeterCategory", ""),
                "pricing_model": row.get("PricingModel", ""),
                "term": row.get("Term", ""),
                "offer_id": row.get("OfferId", ""),
                "cost": 0.0,
                "quantity": 0.0,
            }
        enrollment[mid]["cost"] += float(row.get("Cost", 0) or 0)
        enrollment[mid]["quantity"] += float(row.get("Quantity", 0) or 0)

print("Unique MeterIds: %d" % len(enrollment))

# ── Step 2: Index PriceSheet by MeterId (source) ───────────────────────
print("\n" + "=" * 80)
print("STEP 2: Index PriceSheet by MeterId (source lookup)")
print("=" * 80)

ps_by_mid = {}  # meter_id -> list of rows
all_ps_rows = []  # all rows for target indexing

for fn in sorted(glob.glob(os.path.join(PS_DIR, "*.csv"))):
    with open(fn, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            mid = row.get("MeterId", "").strip()
            if mid:
                ps_by_mid.setdefault(mid, []).append(row)
            all_ps_rows.append(row)

print("Total PriceSheet rows: %d" % len(all_ps_rows))

# ── Step 3: MeterId → source PS row → matching key ─────────────────────
print("\n" + "=" * 80)
print("STEP 3: Build source keys via MeterId lookup")
print("=" * 80)

source_keys = {}  # enrollment mid -> {key, src_unit_price, src_uom_mult}

for mid, ei in enrollment.items():
    ps_rows = ps_by_mid.get(mid, [])
    if not ps_rows:
        continue

    price_type = PRICING_MODEL_MAP.get(ei["pricing_model"], ei["pricing_model"])

    # Match by PriceType + OfferId
    matched = None
    for psr in ps_rows:
        if psr.get("PriceType", "") == price_type and psr.get("OfferId", "") == ei["offer_id"]:
            matched = psr
            break
    if not matched:
        for psr in ps_rows:
            if psr.get("PriceType", "") == price_type:
                matched = psr
                break
    if not matched:
        matched = ps_rows[0]

    product = matched.get("Product", "")
    region = matched.get("MeterRegion", "")
    product_base = strip_region_from_product(product, region)

    key = make_key(
        product_base,
        matched.get("MeterName", ""),
        matched.get("PriceType", ""),
        matched.get("Term", ""),
        matched.get("OfferId", ""),
    )

    src_unit = float(matched.get("UnitPrice", 0) or 0)
    src_uom = extract_uom_multiplier(matched.get("UnitOfMeasure", ""))

    source_keys[mid] = {
        "key": key,
        "src_unit_price": src_unit,
        "src_uom_mult": src_uom,
        "product_base": product_base,
    }

print("Source keys built: %d / %d" % (len(source_keys), len(enrollment)))

# ── Step 4: Index target region ─────────────────────────────────────────
print("\n" + "=" * 80)
print("STEP 4: Index target region (%s)" % TARGET_REGION)
print("=" * 80)

target_index = {}  # key -> (unit_price, uom_mult)

for row in all_ps_rows:
    region = row.get("MeterRegion", "").strip()
    if region != TARGET_REGION:
        continue

    product = row.get("Product", "")
    product_base = strip_region_from_product(product, region)
    key = make_key(
        product_base,
        row.get("MeterName", ""),
        row.get("PriceType", ""),
        row.get("Term", ""),
        row.get("OfferId", ""),
    )

    try:
        uom_mult = extract_uom_multiplier(row.get("UnitOfMeasure", ""))
        target_index[key] = (float(row.get("UnitPrice", 0)), uom_mult)
    except (ValueError, TypeError):
        pass

print("Target entries: %d" % len(target_index))

# ── Step 5: Match and compute ───────────────────────────────────────────
print("\n" + "=" * 80)
print("STEP 5: Cross-region comparison with UoM normalization")
print("=" * 80)

matched_count = 0
not_matched = 0
all_pcts = []
total_src = 0.0
total_tgt = 0.0

for mid, sk in source_keys.items():
    key = sk["key"]
    ei = enrollment[mid]
    src_cost = ei["cost"]
    total_src += src_cost

    tgt = target_index.get(key)
    if tgt is None:
        not_matched += 1
        continue

    matched_count += 1
    tgt_unit, tgt_uom = tgt
    src_unit = sk["src_unit_price"]
    src_uom = sk["src_uom_mult"]

    # Normalized per-base-unit price
    src_rate = src_unit / src_uom if src_uom else src_unit
    tgt_rate = tgt_unit / tgt_uom if tgt_uom else tgt_unit

    if src_rate > 0:
        ratio = tgt_rate / src_rate
        tgt_cost = src_cost * ratio
    else:
        ratio = None
        tgt_cost = 0.0

    total_tgt += tgt_cost

    if src_rate > 0 and ratio is not None:
        pct = (ratio - 1) * 100
        all_pcts.append(pct)
        if abs(pct) > 50:
            ei = enrollment[mid]
            sk_data = source_keys[mid]
            tgt_uom_raw = ""
            src_uom_raw = ""
            if "_ps_src_row" in sk_data:
                src_uom_raw = sk_data["_ps_src_row"].get("UnitOfMeasure", "")
            # find target UoM
            print("  OUTLIER: %s pct=%.1f%% src_rate=%.8f tgt_rate=%.8f" % (
                ei["meter_name"], pct, src_rate, tgt_rate))
            print("    src: unit=%.6f uom_canon=%.2f" % (src_unit, src_uom))
            print("    tgt: unit=%.6f uom_canon=%.2f" % (tgt_unit, tgt_uom))

print("Matched: %d / %d" % (matched_count, len(source_keys)))
print("Not found in target: %d" % not_matched)
print("Total source cost: %.2f" % total_src)
print("Total target cost: %.2f" % total_tgt)
if total_src:
    print("Overall change: %.2f%%" % ((total_tgt - total_src) / total_src * 100))

if all_pcts:
    print("\nPer-item price diff distribution:")
    print("  Min: %.2f%%" % min(all_pcts))
    print("  Max: %.2f%%" % max(all_pcts))
    print("  Median: %.2f%%" % statistics.median(all_pcts))
    print("  Mean: %.2f%%" % statistics.mean(all_pcts))

    extreme = [p for p in all_pcts if abs(p) > 50]
    print("\n  Items with >50%% diff: %d" % len(extreme))

    buckets = {"<-10%%": 0, "-10 to -1%%": 0, "-1 to 1%%": 0, "1 to 10%%": 0, "10 to 50%%": 0, ">50%%": 0}
    for d in all_pcts:
        if d < -10:
            buckets["<-10%%"] += 1
        elif d < -1:
            buckets["-10 to -1%%"] += 1
        elif d <= 1:
            buckets["-1 to 1%%"] += 1
        elif d <= 10:
            buckets["1 to 10%%"] += 1
        elif d <= 50:
            buckets["10 to 50%%"] += 1
        else:
            buckets[">50%%"] += 1
    print("\n  Distribution:")
    for b, c in buckets.items():
        print("    %s: %d" % (b, c))
