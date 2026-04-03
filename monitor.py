"""
FR24 Rare Plane Monitor
Uses the FlightRadar24 Python library to fetch live flights.
Sends Discord embeds hourly via GitHub Actions.
"""

import os
import time
import logging
import requests
from datetime import datetime, timezone
from FlightRadar24 import FlightRadar24API

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

FR24_USERNAME        = os.environ.get("FR24_USERNAME", "")
FR24_PASSWORD        = os.environ.get("FR24_PASSWORD", "")
DISCORD_WEBHOOK_URL  = os.environ.get("DISCORD_WEBHOOK_URL", "")
DISCORD_MESSAGE_DELAY = 1.5

# ── Aircraft type watchlist ───────────────────────────────────
WATCHLIST_TYPES = [
    "L188", "ZZZZ", "B2",
    "B52",
    "A124", "A148", "A310", "A3ST",
    "AN12", "AN22", "AN26", "AN30", "AN32", "AN72", "AN74",
    "B779", "B74S", "B742", "B741", "B732", "B722", "B703", "B720",
    "B717", "B733", "B734", "B735", "B736",
    "B1",
    "DC6", "DC5", "DC4", "DC3", "DC2", "DC10", "DC1", "DC7", "DC87", "DC91", "DC9",
    "C144", "BSCA", "CONC", "BER2", "BER1", "BALL",
    "F1", "F104", "F11", "F12", "F14", "F2", "F22", "F35", "F4", "F5", "F16", "F15", "F18",
    "IL62", "IL76", "IL18",
    "L101", "L410",
    "MD10", "MD11", "MD81", "MD82", "MD83", "MD87", "MD88", "MD90",
    "NIM",
    "P3",
    "SGUP",
    "YK50", "YK42", "YK40",
    "VT23", "WHK2", "VC10",
    "V22", "U2",
    "TRID", "T45", "T204", "T2", "T154", "T134",
    "SLCH", "SHIP",
    "733",
    "BTB2", "RFAL", "CORS",
    "E6", "E3", "E4", "E8",
    "VC25",
    "F27", "F28", "F100", "F70",
    "D328",
    "WB57",
]

# ── Registration watchlist ────────────────────────────────────
WATCHLIST_REGS = [
    "N990XB",
]

# ── Airline watchlist ─────────────────────────────────────────
WATCHLIST_AIRLINES = [
    "IGY",  # NASA
]

# ── Squawk codes to flag ──────────────────────────────────────
SQUAWK_WATCH = ["7500", "7600", "7700"]

# ── Rare tier — triggers @everyone ───────────────────────────
RARE_TYPES = ["E4", "VC25", "WB57", "CONC", "BSCA"]

# ── Excluded airlines (always filtered out) ───────────────────
EXCLUDED_AIRLINES = [
    "AVJ",  # Avia Traffic Company
    "HYH",  # Hayways
    "SHY",  # Shirak Avia
    "UTA",  # UTair
    "AFG",  # Ariana Afghan Airlines
    "FJO",  # Fly Jordan
    "SWT",  # Swiftair
    "DHK",  # DHL Air
    "DHL",  # DHL
    "EXC",  # Express Cargo Airlines
    "SJY",  # Sriwijaya Air
    "LBZ",  # Nam Air
    "RBW",  # Rimbun Air
    "ANU",  # Aero Nusantara Cargo
    "MJT",  # MJets
    "SNK",  # Sin-Kung Airways
    "ARY",  # Airnesia Royal Cargo
    "TGN",  # Trigana Air
    "XPR",  # Xpress Air
    "EID",  # Eastindo
    "CGD",  # Cardig Air
    "AZG",  # Silk Way Airlines
    "KMF",  # Kam Air
    "EAF",  # East African
    "PCE",  # Peace Air
    "CLY",  # Cally Air
    "AAH",  # Aloha Air Cargo
]

# ── Excluded type+airline combos ──────────────────────────────
EXCLUDED_COMBOS = [
    {"type": "F100", "airline": "UTY"},  # Alliance Airlines F100
    {"type": "F100", "airline": "QJE"},  # QantasLink F100
    {"type": "B717", "airline": "DAL"},  # Delta B717
    {"type": "B717", "airline": "HAL"},  # Hawaiian B717
    {"type": "MD11", "airline": "FDX"},  # FedEx MD-11
    {"type": "MD11", "airline": "WGN"},  # Western Global MD-11
]

# ─────────────────────────────────────────────────────────────
# FR24 FETCHING
# ─────────────────────────────────────────────────────────────

def get_all_zones(zones, parent_name=""):
    """Recursively extract all leaf zones as (name, bounds) tuples."""
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


def fetch_flights():
    """Login to FR24 and fetch flights across all zones, deduplicated."""
    try:
        fr24 = FlightRadar24API(FR24_USERNAME, FR24_PASSWORD)
        zones = fr24.get_zones()
        all_zones = get_all_zones(zones)
        log.info(f"Querying {len(all_zones)} zones...")

        seen_ids = set()
        all_flights = []

        for zone_name, bounds in all_zones:
            try:
                bounds_str = f"{bounds['tl_y']},{bounds['br_y']},{bounds['tl_x']},{bounds['br_x']}"
                flights = fr24.get_flights(bounds=bounds_str)
                new = 0
                for f in flights:
                    fid = getattr(f, "id", None)
                    if fid and fid not in seen_ids:
                        seen_ids.add(fid)
                        all_flights.append(f)
                        new += 1
                log.info(f"Zone {zone_name}: {len(flights)} flights, {new} new")
                time.sleep(0.5)
            except Exception as e:
                log.warning(f"Zone {zone_name} failed: {e}")
                continue

        log.info(f"Fetched {len(all_flights)} total unique flights from FR24")
        return fr24, all_flights
    except Exception as e:
        log.error(f"Failed to fetch FR24 data: {e}")
        return None, None


def fetch_most_tracked(fr24):
    """Fetch FR24's top most tracked flights."""
    try:
        most_tracked = fr24.get_most_tracked_flights()
        return most_tracked[:10] if most_tracked else []
    except Exception as e:
        log.warning(f"Could not fetch most tracked: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# FILTERING
# ─────────────────────────────────────────────────────────────

def is_excluded(flight):
    """Return True if flight should be filtered out."""
    ftype   = (getattr(flight, "aircraft_code", "") or "").upper()
    airline = (getattr(flight, "airline_icao",  "") or "").upper()

    # Full airline block
    if airline in [a.upper() for a in EXCLUDED_AIRLINES]:
        return True

    # Type + airline combo block
    for combo in EXCLUDED_COMBOS:
        if ftype == combo["type"].upper() and airline == combo["airline"].upper():
            return True

    return False


def matches_watchlist(flight):
    """Return True if flight matches any watchlist criteria."""
    ftype   = (getattr(flight, "aircraft_code", "") or "").upper()
    reg     = (getattr(flight, "registration",  "") or "").upper()
    airline = (getattr(flight, "airline_icao",  "") or "").upper()
    squawk  = (getattr(flight, "squawk",        "") or "")

    if ftype in [t.upper() for t in WATCHLIST_TYPES]:
        return True
    if reg in [r.upper() for r in WATCHLIST_REGS]:
        return True
    if airline in [a.upper() for a in WATCHLIST_AIRLINES]:
        return True
    if squawk in SQUAWK_WATCH:
        return True
    return False


def is_rare(flight):
    """Return True if flight matches the rare/ping tier."""
    ftype = (getattr(flight, "aircraft_code", "") or "").upper()
    return ftype in [t.upper() for t in RARE_TYPES]


def is_squawk_alert(flight):
    """Return True if flight is squawking an emergency code."""
    squawk = (getattr(flight, "squawk", "") or "")
    return squawk in SQUAWK_WATCH


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def safe(val, suffix=""):
    if val is None or str(val).strip() in ("", "0", "None", "N/A"):
        return "N/A"
    return f"{val}{suffix}"


def get_jetphotos_link(reg):
    if not reg or reg == "N/A":
        return None
    clean = reg.replace("-", "").replace(" ", "").upper()
    return f"https://www.jetphotos.com/registration/{clean}"


def get_fr24_link(flight):
    callsign  = getattr(flight, "callsign", "") or ""
    flight_id = getattr(flight, "id", "")       or ""
    if callsign:
        return f"https://www.flightradar24.com/{callsign}/{flight_id}"
    return f"https://www.flightradar24.com/{flight_id}"


def format_flight_age(flight):
    try:
        ts   = int(getattr(flight, "time", 0) or 0)
        now  = int(datetime.now(timezone.utc).timestamp())
        diff = now - ts
        if diff < 60:
            return f"{diff}s ago"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        else:
            h = diff // 3600
            m = (diff % 3600) // 60
            return f"{h}h {m}m ago"
    except Exception:
        return "N/A"


# ─────────────────────────────────────────────────────────────
# DISCORD
# ─────────────────────────────────────────────────────────────

def build_embed(flight, rare, squawk_alert):
    reg      = safe(getattr(flight, "registration",  None))
    ftype    = safe(getattr(flight, "aircraft_code", None))
    callsign = safe(getattr(flight, "callsign",      None))
    airline  = safe(getattr(flight, "airline_icao",  None))
    origin   = safe(getattr(flight, "origin_airport_iata",      None))
    dest     = safe(getattr(flight, "destination_airport_iata", None))
    alt      = getattr(flight, "altitude",     None)
    spd      = getattr(flight, "ground_speed", None)
    squawk   = safe(getattr(flight, "squawk",  None))

    try:
        alt_str = f"{int(alt):,} ft" if alt and int(alt) > 0 else "N/A"
    except Exception:
        alt_str = "N/A"

    try:
        spd_str = f"{int(spd)} kts" if spd and int(spd) > 0 else "N/A"
    except Exception:
        spd_str = "N/A"

    jp_link   = get_jetphotos_link(reg)
    fr24_link = get_fr24_link(flight)
    age       = format_flight_age(flight)

    jp_val   = f"[Photos]({jp_link})"  if jp_link   else "N/A"
    fr24_val = f"[Track]({fr24_link})" if fr24_link  else "N/A"

    if rare:
        color = 0xFF4500
        title = f"🚨 RARE — {reg} — {ftype}"
    elif squawk_alert:
        color = 0xFFD700
        title = f"⚠️ SQUAWK {squawk} — {reg} — {ftype}"
    else:
        color = 0x00BFFF
        title = f"✈️  {reg} — {ftype}"

    return {
        "title": title,
        "color": color,
        "fields": [
            {"name": "Registration",  "value": reg,                  "inline": True},
            {"name": "Aircraft Type", "value": ftype,                 "inline": True},
            {"name": "Callsign",      "value": callsign,              "inline": True},
            {"name": "Airline",       "value": airline,               "inline": True},
            {"name": "Route",         "value": f"{origin} → {dest}", "inline": True},
            {"name": "Squawk",        "value": squawk,                "inline": True},
            {"name": "Altitude",      "value": alt_str,               "inline": True},
            {"name": "Speed",         "value": spd_str,               "inline": True},
            {"name": "First Seen",    "value": age,                   "inline": True},
            {"name": "FR24 Live",     "value": fr24_val,              "inline": True},
            {"name": "JetPhotos",     "value": jp_val,                "inline": True},
        ],
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


def build_most_tracked_embed(most_tracked):
    """Build a purple embed showing top 10 most tracked flights."""
    if not most_tracked:
        return None

    lines = []
    for i, flight in enumerate(most_tracked, 1):
        try:
            callsign = getattr(flight, "callsign", None) or getattr(flight, "identification", {})
            if isinstance(callsign, dict):
                callsign = callsign.get("callsign", "N/A")
            ftype = getattr(flight, "aircraft", {})
            if isinstance(ftype, dict):
                ftype = ftype.get("code", {}).get("icao", "N/A")
            count = getattr(flight, "tracked_by_count", "?")
            lines.append(f"`{i}.` {callsign} — {ftype} — {count} trackers")
        except Exception:
            lines.append(f"`{i}.` Data unavailable")

    return {
        "title": "📡 Top 10 Most Tracked Right Now",
        "description": "\n".join(lines),
        "color": 0x9B59B6,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


def send_discord(content=None, embed=None):
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = float(r.json().get("retry_after", 2))
            log.warning(f"Rate limited. Waiting {retry_after}s")
            time.sleep(retry_after)
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        elif r.status_code not in (200, 204):
            log.error(f"Discord error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"Discord send failed: {e}")


def send_flight(flight, rare, squawk_alert):
    embed   = build_embed(flight, rare, squawk_alert)
    content = "@everyone 🚨 Rare aircraft detected!" if rare else None
    send_discord(content=content, embed=embed)
    time.sleep(DISCORD_MESSAGE_DELAY)


def send_summary(total, rare_count, squawk_count, excluded_count):
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    embed = {
        "title": "📊 Hourly Scan Complete",
        "color": 0x2ECC71,
        "fields": [
            {"name": "Flights Shown",    "value": str(total),          "inline": True},
            {"name": "Rare Detected",    "value": str(rare_count),     "inline": True},
            {"name": "Squawk Alerts",    "value": str(squawk_count),   "inline": True},
            {"name": "Filtered Out",     "value": str(excluded_count), "inline": True},
        ],
        "footer": {"text": f"FR24 Monitor • {now}"},
    }
    send_discord(embed=embed)


def send_fetch_error():
    embed = {
        "title": "❌ FR24 Fetch Failed",
        "description": "Could not reach FlightRadar24. The site may be down or your login details are wrong.",
        "color": 0xFF0000,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }
    send_discord(embed=embed)


def send_zero_flights():
    embed = {
        "title": "👻 0 Flights Found",
        "description": "Somehow nothing matched your filter this hour.\nConsolation prize: [JetPhotos Latest](https://www.jetphotos.com/latest-photos)",
        "color": 0x95A5A6,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }
    send_discord(embed=embed)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    log.info("FR24 Monitor starting...")

    fr24, all_flights = fetch_flights()

    if all_flights is None:
        send_fetch_error()
        return

    matched       = []
    excluded_count = 0

    for flight in all_flights:
        if not matches_watchlist(flight):
            continue
        if is_excluded(flight):
            excluded_count += 1
            continue
        matched.append(flight)

    log.info(f"{len(matched)} flights matched after exclusions ({excluded_count} excluded)")

    if not matched:
        send_zero_flights()
    else:
        rare_count   = 0
        squawk_count = 0

        for flight in matched:
            rare         = is_rare(flight)
            squawk_alert = is_squawk_alert(flight)
            if rare:
                rare_count += 1
            if squawk_alert:
                squawk_count += 1
            send_flight(flight, rare, squawk_alert)

        send_summary(
            total=len(matched),
            rare_count=rare_count,
            squawk_count=squawk_count,
            excluded_count=excluded_count
        )

    # Top 10 most tracked — always posted at the end
    most_tracked = fetch_most_tracked(fr24)
    if most_tracked:
        embed = build_most_tracked_embed(most_tracked)
        if embed:
            time.sleep(DISCORD_MESSAGE_DELAY)
            send_discord(embed=embed)

    log.info("Done.")


if __name__ == "__main__":
    main()
