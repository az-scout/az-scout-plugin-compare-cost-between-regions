"""Build mapping between ARM region displayName and PriceSheet MeterRegion."""
import csv
import glob
import os

PS_DIR = "/Users/lrivallain/OneDrive - Microsoft/Documents/Customers/Opella/2025_04_Multi region thinking/ArmPriceSheet_Enrollment_8607656_202603/"

# Collect all unique MeterRegion values
regions = set()
for fn in sorted(glob.glob(os.path.join(PS_DIR, "*.csv"))):
    with open(fn, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            r = (row.get("MeterRegion") or "").strip()
            if r:
                regions.add(r)

print("PriceSheet MeterRegion values (%d):" % len(regions))
for r in sorted(regions):
    print("  %s" % r)
