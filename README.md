# garmin-locations

Reads your Garmin Connect activities and groups/sorts them by where they started.

## Setup

```
pip install garminconnect
```

Python 3.10+.

## Use

```
python garmin_locations.py                      # log in, download up to 1000 activities, group by place
python garmin_locations.py --sort distance      # groups ordered by total km instead of count
python garmin_locations.py --type running       # only runs (substring match on activity type)
python garmin_locations.py --by cluster --radius 2   # pure coordinate clustering, 2 km radius
python garmin_locations.py --geocode            # name unnamed spots via OpenStreetMap
python garmin_locations.py --near "Pasadena, CA" --top 30   # closest activities to a place
python garmin_locations.py --near 34.15,-118.14
python garmin_locations.py --csv out.csv --map map.html     # export everything + clustered map
python garmin_locations.py --refresh            # re-download instead of using the cache
```

First run asks for your Garmin email, password and MFA code (if enabled). You can also set
`GARMIN_EMAIL` / `GARMIN_PASSWORD`. Login tokens are saved to `~/.garminconnect`, so later runs
don't need your password. Downloaded activities are cached in `data/activities_cache.json`.

## How "location" is decided (`--by place`)

1. Garmin's own location name for the activity (e.g. "Pasadena").
2. If missing, the name of the nearest Garmin-named activity within `--radius` km.
3. If still missing: a reverse-geocoded city with `--geocode`, otherwise a coordinate cluster ("Area 3").
4. Indoor/treadmill activities without GPS go under "No GPS".

## No-login option: Garmin data export

Request your data at https://www.garmin.com/account/datamanagement/ → *Export Your Data*.
When the zip arrives, unzip it and run:

```
python garmin_locations.py --export path/to/unzipped-export
```

It finds the `*_summarizedActivities.json` files automatically.

## Notes

- `garminconnect` is an unofficial library that talks to Garmin Connect's web API. Garmin
  sometimes changes its login flow; if login breaks, `pip install -U garminconnect` usually fixes it,
  or use the export option.
- Geocoding uses OpenStreetMap Nominatim at 1 request/second, rounded to ~1 km and cached in
  `data/geocode_cache.json`, so only the first run is slow.
