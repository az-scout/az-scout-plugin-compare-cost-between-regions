import csv, glob, os, re

PS_DIR = "/Users/lrivallain/OneDrive - Microsoft/Documents/Customers/Opella/2025_04_Multi region thinking/ArmPriceSheet_Enrollment_8607656_202603/"

# Collect all UoMs and find pairs where the same product-key has different unit types
# across regions
uom_by_key = {}  # (product_base, meter_name, ...) -> {region: uom}

def strip_region(product, region):
    s = product.strip()
    if s.endswith(" - Expired"):
        s = s[:-len(" - Expired")]
    suffix = " - " + region
    if s.endswith(suffix):
        s = s[:-len(suffix)]
    return s

def make_key(product_base, meter_name, price_type, term, offer_id):
    return (product_base.lower(), meter_name.lower(), price_type.lower(),
            term.lower(), offer_id.lower())

def parse_uom(uom):
    """Parse UoM into (multiplier, base_unit)."""
    if not uom:
        return 1.0, ""
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(.*)", uom.strip())
    if m:
        return float(m.group(1)), m.group(2).strip()
    return 1.0, uom.strip()

for fn in sorted(glob.glob(os.path.join(PS_DIR, "*.csv"))):
    with open(fn, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            region = row.get("MeterRegion", "").strip()
            if not region:
                continue
            product = row.get("Product", "")
            pbase = strip_region(product, region)
            key = make_key(pbase, row.get("MeterName",""),
                          row.get("PriceType",""), row.get("Term",""),
                          row.get("OfferId",""))
            uom = row.get("UnitOfMeasure", "")
            mult, base = parse_uom(uom)
            uom_by_key.setdefault(key, {})[region] = (mult, base, uom,
                                                        float(row.get("UnitPrice",0) or 0))

# Find keys where unit TYPE differs across regions
diffs = []
unit_pairs = set()
for key, regions in uom_by_key.items():
    bases = set(b for _, b, _, _ in regions.values())
    if len(bases) > 1:
        diffs.append((key, regions))
        for b in bases:
            for b2 in bases:
                if b != b2 and b < b2:
                    unit_pairs.add((b, b2))

print("Keys with different unit types across regions: %d" % len(diffs))
print("\nDistinct unit-type pairs:")
for a, b in sorted(unit_pairs):
    print("  %s  <->  %s" % (repr(a), repr(b)))

# Check specific outliers
print("\n\n=== GRS Data Stored (all variants) ===")
for key, regions in uom_by_key.items():
    if key[1] == "grs data stored" and "consumption" in key[2]:
        print("  Key: %s" % (key,))
        for r in ("SE Central", "EU West"):
            if r in regions:
                mult, base, raw, price = regions[r]
                print("    %s: UoM=%s  Price=%.4f" % (r, raw, price))

print("\n=== ZRS Data Stored (all variants) ===")
for key, regions in uom_by_key.items():
    if key[1] == "zrs data stored" and "consumption" in key[2]:
        print("  Key: %s" % (key,))
        for r in ("SE Central", "EU West"):
            if r in regions:
                mult, base, raw, price = regions[r]
                print("    %s: UoM=%s  Price=%.4f" % (r, raw, price))
