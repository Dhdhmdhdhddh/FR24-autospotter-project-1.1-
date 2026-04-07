"""
FR24 Squawk Scanner — Lightweight emergency monitor
Zone-based scan, only posts 7500/7600/7700 squawks.
Triggered every 3 minutes via cron-job.org.
"""

import os
import time
import logging
import requests
from datetime import datetime, timezone
from FlightRadar24 import FlightRadar24API

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FR24_USERNAME           = os.environ.get("FR24_USERNAME", "")
FR24_PASSWORD           = os.environ.get("FR24_PASSWORD", "")
DISCORD_WEBHOOK_SQUAWK  = os.environ.get("DISCORD_WEBHOOK_SQUAWK", "")

SQUAWK_WATCH = ["7500", "7600", "7700"]
SQUAWK_MEANINGS = {
    "7500": "✈️ Hijacking",
    "7600": "📻 Radio Failure",
    "7700": "🆘 Emergency",
}


def get_all_zones(zones, parent_name=""):
    result = []
    for name, data in zones.items():
        if name == "subzones":
            continue
        if not isinstance(data, dict):
            continue
        full_name = f"{parent_name}/{name}" if parent_name else name
        subzones = data.get("subzones", {})
        if subzones:
            result.extend(get_all_zones(subzones, full_name))
        else:
            result.append((full_name, data))
    return result


def fetch_squawks():
    try:
        fr24 = FlightRadar24API(FR24_USERNAME, FR24_PASSWORD)
        zones = fr24.get_zones()
        zone_list = get_all_zones(zones)

        seen_ids = set()
        found = []

        for zone_name, bounds in zone_list:
            try:
                bounds_str = f"{bounds['tl_y']},{bounds['br_y']},{bounds['tl_x']},{bounds['br_x']}"
                flights = fr24.get_flights(bounds=bounds_str)
                for f in flights:
                    squawk = (getattr(f, "squawk", "") or "")
                    if squawk not in SQUAWK_WATCH:
                        continue
                    fid = getattr(f, "id", None)
                    if fid and fid not in seen_ids:
                        seen_ids.add(fid)
                        found.append(f)
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"Zone {zone_name} failed: {e}")
                continue

        log.info(f"Found {len(found)} emergency squawks")
        return found
    except Exception as e:
        log.error(f"Fetch failed: {e}")
        return []


def send_discord(webhook_url, content=None, embed=None):
    if not webhook_url:
        return
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)))
            requests.post(webhook_url, json=payload, timeout=10)
        elif r.status_code not in (200, 204):
            log.error(f"Discord error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"Discord send failed: {e}")


def fmt(v):
    return str(v) if v not in [None, "", "None", "N/A"] else "N/A"


def build_squawk_embed(flight):
    reg      = fmt(getattr(flight, "registration",           None))
    ftype    = fmt(getattr(flight, "aircraft_code",          None))
    callsign = fmt(getattr(flight, "callsign",               None))
    airline  = fmt(getattr(flight, "airline_icao",           None))
    origin   = fmt(getattr(flight, "origin_airport_iata",       None))
    dest     = fmt(getattr(flight, "destination_airport_iata",  None))
    squawk   = fmt(getattr(flight, "squawk",                 None))
    alt      = getattr(flight, "altitude",     None)
    spd      = getattr(flight, "ground_speed", None)
    lat      = getattr(flight, "latitude",     None)
    lon      = getattr(flight, "longitude",    None)

    try:
        alt_str = f"{int(alt):,} ft" if alt and int(alt) > 0 else "N/A"
    except Exception:
        alt_str = "N/A"
    try:
        spd_str = f"{int(spd)} kts" if spd and int(spd) > 0 else "N/A"
    except Exception:
        spd_str = "N/A"
    try:
        pos_str = f"{float(lat):.4f}, {float(lon):.4f}" if lat and lon else "N/A"
    except Exception:
        pos_str = "N/A"

    meaning  = SQUAWK_MEANINGS.get(squawk, "🆘 Emergency")
    flight_id = getattr(flight, "id", "") or ""
    fr24_link = f"https://www.flightradar24.com/{callsign}/{flight_id}" if callsign != "N/A" else f"https://www.flightradar24.com/{flight_id}"

    return {
        "title": f"⚠️ SQUAWK {squawk} — {reg}",
        "description": f"**{meaning}**",
        "color": 0xFFD700,
        "fields": [
            {"name": "Registration", "value": reg,                 "inline": True},
            {"name": "Type",         "value": ftype,               "inline": True},
            {"name": "Callsign",     "value": callsign,            "inline": True},
            {"name": "Airline",      "value": airline,             "inline": True},
            {"name": "Route",        "value": f"{origin} → {dest}","inline": True},
            {"name": "Altitude",     "value": alt_str,             "inline": True},
            {"name": "Speed",        "value": spd_str,             "inline": True},
            {"name": "Position",     "value": pos_str,             "inline": True},
            {"name": "FR24 Live",    "value": f"[Track]({fr24_link})", "inline": True},
        ],
        "footer": {"text": f"FR24 Squawk Scanner • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


def main():
    log.info("Squawk scanner starting...")
    flights = fetch_squawks()

    for flight in flights:
        embed = build_squawk_embed(flight)
        send_discord(DISCORD_WEBHOOK_SQUAWK, content="@", embed=embed)
        time.sleep(1.5)

    log.info("Done.")


if __name__ == "__main__":
    main()
