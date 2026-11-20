#!/usr/bin/env python3
"""
garmin_locations.py - read your Garmin Connect activities and sort/group them by location.

Data sources (pick one):
  * Live from Garmin Connect (default) using the unofficial `garminconnect` library.
    First run asks for email/password (+ MFA code if enabled) and saves tokens to
    ~/.garminconnect so later runs don't need your password.
  * A Garmin data export (--export PATH): the *_summarizedActivities.json file (or the
    whole unzipped export folder) from https://www.garmin.com/account/datamanagement/

Grouping modes:
  --by place     (default) Garmin's location name, else reverse-geocoded city (--geocode),
                 else a coordinate cluster
  --by cluster   cluster start points within --radius km of each other
  --near X       sort every activity by distance from X ("lat,lon" or a place name)

Examples:
  python garmin_locations.py
  python garmin_locations.py --limit 500 --csv activities.csv --map map.html
  python garmin_locations.py --by cluster --radius 2
  python garmin_locations.py --near "Pasadena, CA" --type running
  python garmin_locations.py --export ~/Downloads/garmin-export
"""
from __future__ import annotations

import argparse
import csv
import getpass
import html
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

TOKEN_DIR = Path(os.getenv("GARMINTOKENS", "~/.garminconnect")).expanduser()
DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_FILE = DATA_DIR / "activities_cache.json"
GEOCODE_CACHE = DATA_DIR / "geocode_cache.json"
USER_AGENT = "garmin-locations-script/1.0 (personal use)"


# --------------------------------------------------------------------------- model
@dataclass
class Activity:
    id: str
    name: str
    type: str
    start: str            # ISO local time
    distance_km: float
    duration_min: float
    lat: float | None
    lon: float | None
    garmin_location: str  # Garmin's own locationName, may be ""
    place: str = ""       # filled in by grouping
    dist_from_ref_km: float | None = None

    @property
    def has_gps(self) -> bool:
        return self.lat is not None and self.lon is not None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- loading: live
def garmin_client():
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("Missing dependency: pip install garminconnect")

    # 1) try saved tokens
    if TOKEN_DIR.exists():
        try:
            g = Garmin()
            g.login(str(TOKEN_DIR))
            return g
        except Exception as e:  # stale tokens -> fall through to password login
            print(f"Saved login didn't work ({e.__class__.__name__}); logging in again.")

    # 2) credentials (env vars or prompt)
    email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")
    g = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    g.login(str(TOKEN_DIR))  # saves tokens here for next time
    print(f"Logged in. Tokens saved to {TOKEN_DIR}")
    return g


def fetch_live(limit: int, refresh: bool) -> list[dict]:
    if CACHE_FILE.exists() and not refresh:
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if len(cached) >= limit:
            print(f"Using cached activities from {CACHE_FILE} (--refresh to re-download)")
            return cached[:limit]

    g = garmin_client()
    raw, page = [], 100
    while len(raw) < limit:
        batch = g.get_activities(start=len(raw), limit=min(page, limit - len(raw)))
        if not batch:
            break
        raw.extend(batch)
        print(f"  fetched {len(raw)} activities...", end="\r")
    print(f"Fetched {len(raw)} activities from Garmin Connect.   ")
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def parse_live(a: dict) -> Activity:
    t = a.get("activityType") or {}
    return Activity(
        id=str(a.get("activityId", "")),
        name=a.get("activityName") or "",
        type=t.get("typeKey", "") if isinstance(t, dict) else str(t),
        start=(a.get("startTimeLocal") or "").replace(" ", "T"),
        distance_km=round((a.get("distance") or 0) / 1000, 2),        # meters
        duration_min=round((a.get("duration") or 0) / 60, 1),         # seconds
        lat=a.get("startLatitude"),
        lon=a.get("startLongitude"),
        garmin_location=a.get("locationName") or "",
    )


# --------------------------------------------------------------------------- loading: export
def load_export(path: Path) -> list[Activity]:
    files = [path] if path.is_file() else sorted(path.rglob("*summarizedActivities*.json"))
    if not files:
        sys.exit(f"No *summarizedActivities*.json found under {path}")
    out = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        items = []
        for block in data if isinstance(data, list) else [data]:
            items.extend(block.get("summarizedActivitiesExport", []) if isinstance(block, dict) else [])
        out.extend(parse_export(a) for a in items)
    print(f"Loaded {len(out)} activities from export ({len(files)} file(s)).")
    return out


def parse_export(a: dict) -> Activity:
    # Export units: distance in centimeters, duration in milliseconds, time in epoch ms.
    ts = a.get("startTimeLocal") or a.get("beginTimestamp")
    start = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if ts else ""
    return Activity(
        id=str(a.get("activityId", "")),
        name=a.get("name") or "",
        type=str(a.get("activityType") or a.get("sportType") or ""),
        start=start,
        distance_km=round((a.get("distance") or 0) / 100_000, 2),
        duration_min=round((a.get("duration") or 0) / 60_000, 1),
        lat=a.get("startLatitude"),
        lon=a.get("startLongitude"),
        garmin_location=a.get("locationName") or "",
    )


# --------------------------------------------------------------------------- geocoding
class Geocoder:
    """OpenStreetMap Nominatim, cached on disk, rate-limited to 1 request/second."""

    def __init__(self):
        self.cache = json.loads(GEOCODE_CACHE.read_text(encoding="utf-8")) if GEOCODE_CACHE.exists() else {}
        self._last = 0.0

    def _get(self, url: str):
        wait = 1.05 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    def save(self):
        DATA_DIR.mkdir(exist_ok=True)
        GEOCODE_CACHE.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")

    def reverse(self, lat: float, lon: float) -> str:
        key = f"{lat:.2f},{lon:.2f}"  # ~1 km grid, keeps request count low
        if key not in self.cache:
            try:
                q = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "json", "zoom": 10})
                addr = self._get(f"https://nominatim.openstreetmap.org/reverse?{q}").get("address", {})
                city = next((addr[k] for k in ("city", "town", "village", "hamlet", "county") if k in addr), "")
                region = addr.get("state") or addr.get("country", "")
                self.cache[key] = ", ".join(x for x in (city, region) if x)
            except Exception as e:
                print(f"  geocode failed for {key}: {e}")
                return ""
        return self.cache[key]

    def forward(self, query: str) -> tuple[float, float]:
        q = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
        res = self._get(f"https://nominatim.openstreetmap.org/search?{q}")
        if not res:
            sys.exit(f"Couldn't find a location called {query!r}")
        return float(res[0]["lat"]), float(res[0]["lon"])


# --------------------------------------------------------------------------- grouping
def cluster(acts: list[Activity], radius_km: float) -> None:
    """Greedy clustering: each activity joins the first cluster center within radius."""
    centers: list[list[float]] = []  # [lat, lon, count]
    for a in sorted((a for a in acts if a.has_gps), key=lambda a: a.start):
        for i, c in enumerate(centers):
            if haversine_km(a.lat, a.lon, c[0], c[1]) <= radius_km:
                c[0] = (c[0] * c[2] + a.lat) / (c[2] + 1)  # running mean center
                c[1] = (c[1] * c[2] + a.lon) / (c[2] + 1)
                c[2] += 1
                a.place = f"#{i + 1}"
                break
        else:
            centers.append([a.lat, a.lon, 1])
            a.place = f"#{len(centers)}"
    labels = {f"#{i + 1}": f"Area {i + 1} ({c[0]:.3f}, {c[1]:.3f})" for i, c in enumerate(centers)}
    for a in acts:
        a.place = labels.get(a.place, "No GPS")


def assign_places(acts: list[Activity], mode: str, geocode: bool, radius_km: float) -> None:
    if mode == "cluster":
        cluster(acts, radius_km)
        return
    geo = Geocoder() if geocode else None
    # Borrow the name of the nearest Garmin-named activity within the radius.
    named = [a for a in acts if a.garmin_location and a.has_gps]
    for a in acts:
        if not a.garmin_location and a.has_gps and named:
            best = min(named, key=lambda n: haversine_km(a.lat, a.lon, n.lat, n.lon))
            if haversine_km(a.lat, a.lon, best.lat, best.lon) <= radius_km:
                a.garmin_location = best.garmin_location
    missing = [a for a in acts if not a.garmin_location and a.has_gps]
    if missing and not geo:
        cluster(missing, radius_km)  # offline fallback for ones Garmin didn't name
    for a in acts:
        if a.garmin_location:
            a.place = a.garmin_location
        elif not a.has_gps:
            a.place = "No GPS"
        elif geo:
            a.place = geo.reverse(a.lat, a.lon) or f"({a.lat:.2f}, {a.lon:.2f})"
    if geo:
        geo.save()


# --------------------------------------------------------------------------- output
def print_groups(acts: list[Activity], sort: str) -> None:
    groups: dict[str, list[Activity]] = defaultdict(list)
    for a in acts:
        groups[a.place].append(a)
    keyf = {
        "count": lambda kv: (-len(kv[1]), kv[0]),
        "distance": lambda kv: (-sum(a.distance_km for a in kv[1]), kv[0]),
        "name": lambda kv: (kv[0] == "No GPS", kv[0].lower()),
    }[sort]
    print(f"\n{'Location':<40} {'Acts':>5} {'Total km':>9} {'Hours':>6}  Last activity")
    print("-" * 80)
    for place, items in sorted(groups.items(), key=keyf):
        km = sum(a.distance_km for a in items)
        hrs = sum(a.duration_min for a in items) / 60
        last = max(a.start for a in items)[:10]
        print(f"{place[:40]:<40} {len(items):>5} {km:>9.1f} {hrs:>6.1f}  {last}")
    print(f"\n{len(acts)} activities in {len(groups)} locations.")


def print_near(acts: list[Activity], ref_label: str, top: int) -> None:
    print(f"\nClosest activities to {ref_label}:\n")
    print(f"{'km away':>8}  {'Date':<10}  {'Type':<16} {'Dist km':>7}  Name / place")
    print("-" * 80)
    for a in acts[:top]:
        d = f"{a.dist_from_ref_km:.1f}" if a.dist_from_ref_km is not None else "-"
        print(f"{d:>8}  {a.start[:10]:<10}  {a.type[:16]:<16} {a.distance_km:>7.1f}  {a.name[:22]} @ {a.place[:20]}")


def write_csv(acts: list[Activity], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(acts[0]).keys()))
        w.writeheader()
        for a in acts:
            w.writerow(asdict(a))
    print(f"Wrote {path}")


def write_map(acts: list[Activity], path: Path) -> None:
    pts = [
        {"lat": a.lat, "lon": a.lon,
         "t": html.escape(f"{a.start[:10]} · {a.type} · {a.distance_km} km — {a.name} ({a.place})")}
        for a in acts if a.has_gps
    ]
    path.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Garmin activities by location</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>html,body,#m{{height:100%;margin:0}}</style></head><body><div id="m"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const pts={json.dumps(pts)};
const m=L.map('m');L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
 {{attribution:'&copy; OpenStreetMap'}}).addTo(m);
const g=L.markerClusterGroup();pts.forEach(p=>g.addLayer(L.marker([p.lat,p.lon]).bindPopup(p.t)));
m.addLayer(g);if(pts.length)m.fitBounds(g.getBounds(),{{padding:[20,20]}});else m.setView([0,0],2);
</script></body></html>""", encoding="utf-8")
    print(f"Wrote {path} ({len(pts)} points)")


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", type=Path, help="Garmin export folder or *_summarizedActivities.json (skips login)")
    ap.add_argument("--limit", type=int, default=1000, help="max activities to download (default 1000)")
    ap.add_argument("--refresh", action="store_true", help="ignore the local cache and re-download")
    ap.add_argument("--type", help="only this activity type, e.g. running, cycling, hiking (substring match)")
    ap.add_argument("--by", choices=["place", "cluster"], default="place", help="how to group (default place)")
    ap.add_argument("--radius", type=float, default=1.0, help="cluster radius in km (default 1)")
    ap.add_argument("--geocode", action="store_true", help="name unnamed spots via OpenStreetMap (slow first time)")
    ap.add_argument("--sort", choices=["count", "distance", "name"], default="count", help="group sort order")
    ap.add_argument("--near", help='sort by distance from "lat,lon" or a place name')
    ap.add_argument("--top", type=int, default=50, help="rows to show with --near (default 50)")
    ap.add_argument("--csv", type=Path, help="write every activity with its location to this CSV")
    ap.add_argument("--map", type=Path, help="write an HTML map of activity start points")
    args = ap.parse_args()

    if args.export:
        acts = load_export(args.export.expanduser())
    else:
        acts = [parse_live(a) for a in fetch_live(args.limit, args.refresh)]

    if args.type:
        acts = [a for a in acts if args.type.lower() in a.type.lower()]
    if not acts:
        sys.exit("No activities found.")

    assign_places(acts, args.by, args.geocode, args.radius)

    if args.near:
        try:
            lat, lon = (float(x) for x in args.near.split(","))
        except ValueError:
            lat, lon = Geocoder().forward(args.near)
        for a in acts:
            a.dist_from_ref_km = round(haversine_km(lat, lon, a.lat, a.lon), 2) if a.has_gps else None
        acts.sort(key=lambda a: (a.dist_from_ref_km is None, a.dist_from_ref_km or 0, a.start))
        print_near(acts, args.near, args.top)
    else:
        acts.sort(key=lambda a: (a.place == "No GPS", a.place.lower(), a.start))
        print_groups(acts, args.sort)

    if args.csv:
        write_csv(acts, args.csv)
    if args.map:
        write_map(acts, args.map)


if __name__ == "__main__":
    main()
