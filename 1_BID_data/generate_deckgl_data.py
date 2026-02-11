"""
Generate per-parcel assessment data for 3D deck.gl visualization.

Fetches NYC PLUTO lot-level data from the Socrata API, spatially filters
to the 11 BIDs near Gowanus using ray-casting point-in-polygon, and
exports a JSON file for the deck.gl ColumnLayer map.
"""

import csv
import json
import math
import re
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BID_CSV = "DATA/NYC_BIDS_09112015.csv"
OUTPUT = "DATA/gowanus_parcels.json"

PLUTO_API = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
PLUTO_FIELDS = (
    "bbl,address,latitude,longitude,assesstot,assessland,"
    "bldgclass,landuse,yearbuilt,numfloors,lotarea"
)
PAGE_SIZE = 50000

BROOKLYN_BIDS = [
    "86th Street Bay Ridge",
    "Atlantic Avenue",
    "Bay Ridge 5th Avenue",
    "Bed-Stuy Gateway",
    "Brighton Beach",
    "Church Flatbush Community Alliance",
    "Court-Livingston-Schermerhorn",
    "Cypress Hills Fulton",
    "DUMBO",
    "East Brooklyn",
    "Flatbush-Nostrand Junction",
    "Fulton Area Business (FAB) Alliance",
    "Fulton Mall Improvement Association",
    "Gowanus BID (Proposed)",
    "Graham Avenue",
    "Grand Street",
    "Kings Highway",
    "MetroTech",
    "Montague Street",
    "Myrtle Avenue Brooklyn Partnership",
    "North Flatbush",
    "Park Slope 5th Avenue",
    "Pitkin Avenue",
    "Sunset Park",
]

# Placeholder colors — the front-end assigns diverging colors dynamically
BID_COLORS = {name: [128, 128, 128] for name in BROOKLYN_BIDS}

# Gowanus BID (Proposed) boundary polygon — coordinates from brooklyn_bids.html
GOWANUS_BOUNDARY = [
    (-73.98871236113611, 40.6852235692749),
    (-73.98656632686861, 40.684387901353176),
    (-73.98699969227908, 40.683765500363144),
    (-73.98645689115888, 40.68355803207488),
    (-73.98666481900734, 40.68325429733605),
    (-73.98500577364807, 40.68259869031278),
    (-73.98436666910332, 40.6835430943332),
    (-73.9820772740561, 40.68265014324907),
    (-73.98185949699375, 40.6829862461299),
    (-73.97982727586435, 40.68216797788509),
    (-73.98387639712381, 40.67614435139574),
    (-73.98570616219023, 40.67397312303486),
    (-73.98800431209425, 40.67508032553716),
    (-73.98874190877774, 40.674180621155706),
    (-73.9903232547831, 40.674983217807416),
    (-73.99044582277797, 40.67536168816061),
    (-73.99097986904138, 40.67549199434205),
    (-73.99192101614494, 40.674349109154754),
    (-73.99482325116658, 40.67583311313964),
    (-73.99534854257324, 40.675454645462594),
    (-73.99649542881106, 40.67406691226546),
    (-73.99776488304373, 40.674704343540796),
    (-73.99649105138268, 40.67744655650161),
    (-73.99458577567648, 40.67657344282233),
    (-73.9937551586398, 40.67783165243714),
    (-73.991865203933, 40.67694775436462),
    (-73.99042393563609, 40.67867819171676),
    (-73.98827461829725, 40.68186174712512),
    (-73.99042393563607, 40.68269744671996),
    (-73.98871236113611, 40.6852235692749),
]


# ---------------------------------------------------------------------------
# Step A: Parse BID boundaries from the CSV's WKT column
# ---------------------------------------------------------------------------

def parse_wkt_multipolygon(wkt):
    """Parse a WKT MULTIPOLYGON string into a list of polygons.

    Each polygon is a list of rings, where each ring is a list of (lon, lat)
    tuples. Only the exterior ring (first ring) of each polygon is kept.
    """
    # Strip the MULTIPOLYGON wrapper
    inner = wkt.strip()
    if inner.upper().startswith("MULTIPOLYGON"):
        inner = inner[len("MULTIPOLYGON"):].strip()
    # Remove outermost parens
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()

    polygons = []
    # Split into individual polygon blocks  ((ring), (ring)), ...
    # We look for top-level ((...)) groups
    depth = 0
    start = None
    for i, ch in enumerate(inner):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                block = inner[start:i + 1]
                polygons.append(block)
                start = None

    result = []
    for poly_block in polygons:
        # Strip outer parens of the polygon block
        poly_block = poly_block.strip()
        if poly_block.startswith("("):
            poly_block = poly_block[1:]
        if poly_block.endswith(")"):
            poly_block = poly_block[:-1]

        # Extract rings — take only the first (exterior) ring
        ring_depth = 0
        ring_start = None
        for i, ch in enumerate(poly_block):
            if ch == "(":
                if ring_depth == 0:
                    ring_start = i
                ring_depth += 1
            elif ch == ")":
                ring_depth -= 1
                if ring_depth == 0 and ring_start is not None:
                    ring_str = poly_block[ring_start + 1:i]
                    coords = []
                    for pair in ring_str.split(","):
                        parts = pair.strip().split()
                        if len(parts) >= 2:
                            coords.append((float(parts[0]), float(parts[1])))
                    if coords:
                        result.append(coords)
                    break  # only exterior ring
    return result


def load_bid_boundaries(csv_path, bid_names):
    """Load BID boundaries from CSV, returning dict of {name: [rings]}."""
    bid_set = set(bid_names)
    boundaries = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("F_ALL_BI_2", "").strip()
            if name in bid_set:
                wkt = row.get("the_geom", "")
                rings = parse_wkt_multipolygon(wkt)
                if rings:
                    boundaries[name] = rings
    return boundaries


def bounding_box(boundaries):
    """Compute the overall bounding box of all boundary rings."""
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    for rings in boundaries.values():
        for ring in rings:
            for lon, lat in ring:
                min_lon = min(min_lon, lon)
                max_lon = max(max_lon, lon)
                min_lat = min(min_lat, lat)
                max_lat = max(max_lat, lat)
    # Add small buffer (~200m)
    buf = 0.002
    return (min_lon - buf, min_lat - buf, max_lon + buf, max_lat + buf)


# ---------------------------------------------------------------------------
# Step B: Fetch PLUTO data from Socrata API
# ---------------------------------------------------------------------------

def fetch_pluto(bbox):
    """Fetch Brooklyn PLUTO lots within bounding box, paginated."""
    min_lon, min_lat, max_lon, max_lat = bbox
    where_clause = (
        f"borough='BK' AND latitude IS NOT NULL AND longitude IS NOT NULL "
        f"AND latitude >= {min_lat} AND latitude <= {max_lat} "
        f"AND longitude >= {min_lon} AND longitude <= {max_lon}"
    )

    all_rows = []
    offset = 0
    while True:
        params = {
            "$select": PLUTO_FIELDS,
            "$where": where_clause,
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "bbl",
        }
        print(f"  Fetching PLUTO offset={offset} ...")
        resp = requests.get(PLUTO_API, params=params, timeout=120)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        print(f"    got {len(batch)} rows (total so far: {len(all_rows)})")
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    print(f"  Total PLUTO rows fetched: {len(all_rows)}")
    return all_rows


# ---------------------------------------------------------------------------
# Step C: Point-in-polygon (ray casting)
# ---------------------------------------------------------------------------

def point_in_ring(lon, lat, ring):
    """Ray-casting algorithm: returns True if (lon, lat) is inside the ring."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def find_bid(lon, lat, boundaries):
    """Return the BID name if (lon, lat) falls inside any BID boundary."""
    for name, rings in boundaries.items():
        for ring in rings:
            if point_in_ring(lon, lat, ring):
                return name
    return None


# ---------------------------------------------------------------------------
# Step D: Assemble and export
# ---------------------------------------------------------------------------

def build_geojson_boundaries(boundaries):
    """Convert boundary rings to GeoJSON features for the overlay layer."""
    features = []
    for name, rings in boundaries.items():
        color = BID_COLORS.get(name, [128, 128, 128])
        # Build MultiPolygon coordinates: each ring becomes a polygon
        polys = [[[list(coord) for coord in ring]] for ring in rings]
        features.append({
            "type": "Feature",
            "properties": {"name": name, "color": color},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": polys,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    print("Step A: Loading BID boundaries...")
    boundaries = load_bid_boundaries(BID_CSV, BROOKLYN_BIDS)
    # Gowanus BID (Proposed) isn't in the CSV — inject its boundary directly
    boundaries["Gowanus BID (Proposed)"] = [GOWANUS_BOUNDARY]
    print(f"  Loaded {len(boundaries)} BID boundaries:")
    for name in boundaries:
        print(f"    - {name} ({len(boundaries[name])} polygon part(s))")

    bbox = bounding_box(boundaries)
    print(f"  Bounding box: lon [{bbox[0]:.4f}, {bbox[2]:.4f}], lat [{bbox[1]:.4f}, {bbox[3]:.4f}]")

    print("\nStep B: Fetching PLUTO data...")
    raw_lots = fetch_pluto(bbox)

    print("\nStep C: Spatial filtering (point-in-polygon)...")
    parcels = []
    bid_counts = {}
    for row in raw_lots:
        try:
            lon = float(row.get("longitude", 0))
            lat = float(row.get("latitude", 0))
        except (ValueError, TypeError):
            continue
        if lon == 0 or lat == 0:
            continue

        bid_name = find_bid(lon, lat, boundaries)
        if bid_name is None:
            continue

        assesstot = 0
        try:
            assesstot = float(row.get("assesstot", 0) or 0)
        except (ValueError, TypeError):
            pass

        assessland = 0
        try:
            assessland = float(row.get("assessland", 0) or 0)
        except (ValueError, TypeError):
            pass

        numfloors = 0
        try:
            numfloors = float(row.get("numfloors", 0) or 0)
        except (ValueError, TypeError):
            pass

        yearbuilt = 0
        try:
            yearbuilt = int(float(row.get("yearbuilt", 0) or 0))
        except (ValueError, TypeError):
            pass

        lotarea = 0
        try:
            lotarea = float(row.get("lotarea", 0) or 0)
        except (ValueError, TypeError):
            pass

        parcels.append({
            "lat": lat,
            "lon": lon,
            "assesstot": assesstot,
            "assessland": assessland,
            "address": row.get("address", ""),
            "bbl": row.get("bbl", ""),
            "bid_name": bid_name,
            "bldgclass": row.get("bldgclass", ""),
            "landuse": row.get("landuse", ""),
            "yearbuilt": yearbuilt,
            "numfloors": numfloors,
            "lotarea": lotarea,
            "color": BID_COLORS.get(bid_name, [128, 128, 128]),
        })
        bid_counts[bid_name] = bid_counts.get(bid_name, 0) + 1

    print(f"  Matched {len(parcels)} lots across {len(bid_counts)} BIDs:")
    for name, count in sorted(bid_counts.items(), key=lambda x: -x[1]):
        print(f"    - {name}: {count} lots")

    print("\nStep D: Exporting JSON...")
    bid_geojson = build_geojson_boundaries(boundaries)

    output = {
        "parcels": parcels,
        "bid_boundaries": bid_geojson,
    }
    with open(OUTPUT, "w") as f:
        json.dump(output, f)

    file_size_mb = len(json.dumps(output)) / (1024 * 1024)
    print(f"  Saved {OUTPUT} ({len(parcels)} parcels, {file_size_mb:.1f} MB)")
    print("Done!")


if __name__ == "__main__":
    main()
