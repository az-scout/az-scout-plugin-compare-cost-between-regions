"""Debug: investigate GRS Data Stored matching issue for SE Central → SE Central."""
import csv
import glob
import os
import re

PS_DIR = "/Users/lrivallain/OneDrive - Microsoft/Documents/Customers/Opella/2025_04_Multi region thinking/ArmPriceSheet_Enrollment_8607656_202603/"
ENROLLMENT = "/Users/lrivallain/OneDrive - Microsoft/Documents/Customers/Opella/2025_04_Multi region thinking/Detail_Enrollment_8607656_202603_en.csv"

# Step 1: Find the enrollment MeterId for "GRS Data Stored" in Backup category
print("=== Enrollment: GRS Data Stored in Backup ===")
with open(ENROLLMENT, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if (row.get("MeterRegion") == "SE Central"
            and row.get("MeterName") == "GRS Data Stored"
            and row.get("MeterCategory") == "Backup"):
            print("  MeterId=%s OfferId=%s PricingModel=%s UnitPrice=%s UoM=%s" % (
                row["MeterId"], row["OfferId"], row["PricingModel"],
                row["UnitPrice"], row["UnitOfMeasure"]))
            break

meter_id = None
with open(ENROLLMENT, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if (row.get("MeterRegion") == "SE Central"
            and row.get("MeterName") == "GRS Data Stored"
            and row.get("MeterCategory") == "Backup"):
            meter_id = row["MeterId"]
            break

# Step 2: Find ALL PriceSheet rows matching this MeterId
print("\n=== PriceSheet: rows for MeterId=%s ===" % meter_id)
for fn in sorted(glob.glob(os.path.join(PS_DIR, "*.csv"))):
    with open(fn, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("MeterId") == meter_id:
                print("  Region=%-12s Product=%s" % (row["MeterRegion"], row["Product"]))
                print("    PriceType=%s OfferId=%s UnitPrice=%s UoM=%s" % (
                    row["PriceType"], row["OfferId"], row["UnitPrice"], row["UnitOfMeasure"]))

# Step 3: Find what product key is built and what it matches
def strip_region(product, region):
    s = product.strip()
    if s.endswith(" - Expired"):
        s = s[:-len(" - Expired")]
    suffix = " - " + region
    if s.endswith(suffix):
        s = s[:-len(suffix)]
    return s

# Find the source PS row (same logic as _find_source_ps_row)
print("\n=== Source PS row lookup ===")
source_row = None
for fn in sorted(glob.glob(os.path.join(PS_DIR, "*.csv"))):
    with open(fn, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("MeterId") == meter_id and row.get("PriceType") == "Consumption" and row.get("OfferId") == "MS-AZR-0017P":
                source_row = row
                break
    if source_row:
        break

if source_row:
    print("  Matched: Product=%s" % source_row["Product"])
    print("  UnitPrice=%s UoM=%s" % (source_row["UnitPrice"], source_row["UnitOfMeasure"]))
    product_base = strip_region(source_row["Product"], source_row["MeterRegion"])
    print("  ProductBase=%s" % product_base)

    # Step 4: Find all SE Central rows matching this product base
    key = (
        product_base.lower(),
        source_row["MeterName"].strip().lower(),
        source_row["PriceType"].strip().lower(),
        source_row.get("Term", "").strip().lower(),
        source_row["OfferId"].strip().lower(),
    )
    print("  Key=%s" % (key,))

    print("\n=== Target lookup: SE Central rows matching this key ===")
    for fn in sorted(glob.glob(os.path.join(PS_DIR, "*.csv"))):
        with open(fn, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("MeterRegion") != "SE Central":
                    continue
                product = row.get("Product", "")
                pb = strip_region(product, "SE Central")
                rkey = (
                    pb.lower(),
                    row.get("MeterName", "").strip().lower(),
                    row.get("PriceType", "").strip().lower(),
                    row.get("Term", "").strip().lower(),
                    row.get("OfferId", "").strip().lower(),
                )
                if rkey == key:
                    print("  MATCH: Product=%s UnitPrice=%s UoM=%s MeterId=%s" % (
                        product, row["UnitPrice"], row["UnitOfMeasure"], row["MeterId"]))
