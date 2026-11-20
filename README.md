# garmin-locations

Reads your Garmin Connect activities and groups/sorts them by where they started.

## Step-by-step install on Windows (no experience needed)

You only need to do steps 1–3 once.

### 1. Install Python

1. Go to https://www.python.org/downloads/ and click the big yellow **Download Python** button.
2. Open the file you downloaded.
3. **Important:** on the first screen, tick the box at the bottom that says
   **"Add python.exe to PATH"**.
4. Click **Install Now**, wait for it to finish, then click **Close**.

### 2. Download this program

1. Go to https://github.com/R0x7/garminactivitylocation
2. Click the green **Code** button, then **Download ZIP**.
3. Open your **Downloads** folder, right-click `garminactivitylocation-main.zip` and choose
   **Extract All…**, then click **Extract**.
4. A new folder opens. Double-click into it until you see a file named `garmin_locations.py`.

### 3. Open a command window in that folder and install the helper

1. In that folder window, click once on the address bar at the top (where it shows the folder path).
2. Type `cmd` and press **Enter**. A black window opens.
3. Copy this line, right-click inside the black window to paste it, and press **Enter**:

   ```
   py -m pip install garminconnect
   ```

   Wait until the text stops scrolling and you see the blinking cursor again.

### 4. Run it

In the same black window, type this and press **Enter**:

```
py garmin_locations.py --csv activities.csv --map map.html
```

- It asks for your **Garmin email** — type it and press Enter.
- It asks for your **Garmin password** — type it and press Enter. **Nothing will appear on screen
  while you type the password.** That's normal; it's hidden on purpose.
- If Garmin sends you a code by email or text, type it when it asks for the **MFA code**.

After a minute you'll see a list of your locations with how many activities you did at each.
It also creates two files in the same folder:

- `activities.csv` — double-click to open every activity in Excel, with its location.
- `map.html` — double-click to see all your activities on a map in your web browser.

You only have to log in the first time. Next time, just do step 3 parts 1–2 (open the black
window in the folder) and step 4.

### If something goes wrong

| What you see | What to do |
|---|---|
| `'py' is not recognized…` | Use `python` instead of `py` in the commands. If that also fails, re-run the Python installer from step 1, choose **Modify** → **Next**, and tick **Add Python to environment variables**. |
| `can't open file … garmin_locations.py` | The black window is in the wrong folder. Close it and redo step 3 from the folder that contains `garmin_locations.py`. |
| A login error | Double-check your email/password at https://connect.garmin.com. If it still fails, run `py -m pip install -U garminconnect` and try again. |
| You want fresh data later | Add `--refresh` to the end of the step 4 command. |

## Setup (for people who already use Python)

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
