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

WATCHLIST_REGS     = ["N990XB"]
WATCHLIST_AIRLINES = ["IGY"]  # NASA
SQUAWK_WATCH       = ["7500", "7600", "7700"]
RARE_TYPES         = ["E4", "VC25", "WB57", "CONC", "BSCA"]

# Add airlines here as you spot spammy ones
EXCLUDED_AIRLINES = []

EXCLUDED_COMBOS = [
    {"type": "F100", "airline": "UTY"},  # Alliance Airlines
    {"type": "F100", "airline": "QLK"},  # QantasLink
    {"type": "B717", "airline": "DAL"},  # Delta
    {"type": "B717", "airline": "HAL"},  # Hawaiian
    {"type": "MD11", "airline": "FDX"},  # FedEx
    {"type": "MD11", "airline": "WGN"},  # Western Global
    {"type": "B733", "airline": "EXS"},  # Jet2
]

# ─────────────────────────────────────────────────────────────
# LOOKUP TABLES
# ─────────────────────────────────────────────────────────────

AIRCRAFT_NAMES = {
    "B741": "Boeing 747-100", "B742": "Boeing 747-200", "B743": "Boeing 747-300",
    "B744": "Boeing 747-400", "B74S": "Boeing 747SP", "B748": "Boeing 747-8",
    "B732": "Boeing 737-200", "B733": "Boeing 737-300", "B734": "Boeing 737-400",
    "B735": "Boeing 737-500", "B736": "Boeing 737-600", "B717": "Boeing 717",
    "B722": "Boeing 727-200", "B703": "Boeing 707-300", "B720": "Boeing 720",
    "B779": "Boeing 777-9", "B52": "Boeing B-52 Stratofortress", "B1": "Rockwell B-1 Lancer",
    "B2": "Northrop Grumman B-2 Spirit",
    "DC3": "Douglas DC-3", "DC4": "Douglas DC-4", "DC6": "Douglas DC-6",
    "DC7": "Douglas DC-7", "DC10": "McDonnell Douglas DC-10",
    "DC9": "McDonnell Douglas DC-9", "DC87": "Douglas DC-8-70", "DC91": "Douglas DC-9-10",
    "MD11": "McDonnell Douglas MD-11", "MD81": "McDonnell Douglas MD-81",
    "MD82": "McDonnell Douglas MD-82", "MD83": "McDonnell Douglas MD-83",
    "MD87": "McDonnell Douglas MD-87", "MD88": "McDonnell Douglas MD-88",
    "MD90": "McDonnell Douglas MD-90", "MD10": "McDonnell Douglas MD-10",
    "A124": "Antonov An-124 Ruslan", "A148": "Antonov An-148",
    "A310": "Airbus A310", "A3ST": "Airbus A300-600ST Beluga",
    "AN12": "Antonov An-12", "AN22": "Antonov An-22 Antei",
    "AN26": "Antonov An-26", "AN30": "Antonov An-30",
    "AN32": "Antonov An-32", "AN72": "Antonov An-72", "AN74": "Antonov An-74",
    "IL62": "Ilyushin Il-62", "IL76": "Ilyushin Il-76", "IL18": "Ilyushin Il-18",
    "T154": "Tupolev Tu-154", "T134": "Tupolev Tu-134",
    "YK42": "Yakovlev Yak-42", "YK40": "Yakovlev Yak-40", "YK50": "Yakovlev Yak-50",
    "L101": "Lockheed L-1011 TriStar", "L188": "Lockheed L-188 Electra",
    "L410": "Let L-410 Turbolet",
    "F22": "Lockheed Martin F-22 Raptor", "F35": "Lockheed Martin F-35 Lightning II",
    "F16": "General Dynamics F-16 Fighting Falcon", "F15": "McDonnell Douglas F-15 Eagle",
    "F18": "McDonnell Douglas F/A-18 Hornet", "F14": "Grumman F-14 Tomcat",
    "F104": "Lockheed F-104 Starfighter",
    "P3": "Lockheed P-3 Orion", "U2": "Lockheed U-2",
    "V22": "Bell Boeing V-22 Osprey", "VC25": "Boeing VC-25 (Air Force One)",
    "E6": "Boeing E-6 Mercury", "E3": "Boeing E-3 Sentry (AWACS)",
    "E4": "Boeing E-4B Nightwatch", "E8": "Boeing E-8 JSTARS",
    "WB57": "Martin WB-57", "VC10": "Vickers VC10",
    "CONC": "Aerospatiale/BAC Concorde", "BSCA": "Aerospatiale/BAC Concorde",
    "F100": "Fokker 100", "F70": "Fokker 70",
    "F27": "Fokker 27 Friendship", "F28": "Fokker 28 Fellowship",
    "D328": "Dornier 328", "TRID": "Hawker Siddeley Trident",
    "NIM": "Hawker Siddeley Nimrod", "SGUP": "Airbus Super Guppy",
    "VT23": "Vought F4U Corsair",
}

AIRLINE_NAMES = {
    "IGY": "NASA", "DAL": "Delta Air Lines", "AAL": "American Airlines",
    "UAL": "United Airlines", "SWA": "Southwest Airlines", "BAW": "British Airways",
    "DLH": "Lufthansa", "AFR": "Air France", "KLM": "KLM Royal Dutch Airlines",
    "QFA": "Qantas", "SIA": "Singapore Airlines", "UAE": "Emirates",
    "ETH": "Ethiopian Airlines", "MSR": "EgyptAir", "THY": "Turkish Airlines",
    "FDX": "FedEx Express", "UPS": "UPS Airlines", "WGN": "Western Global Airlines",
    "HAL": "Hawaiian Airlines", "ASA": "Alaska Airlines",
    "FFT": "Frontier Airlines", "SKW": "SkyWest Airlines",
    "UTY": "Alliance Airlines", "QLK": "QantasLink",
    "AFG": "Ariana Afghan Airlines", "IGO": "IndiGo",
    "EXS": "Jet2",
}

# ─────────────────────────────────────────────────────────────
# FR24 FETCHING
# ─────────────────────────────────────────────────────────────

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


def fetch_flights():
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
    try:
        most_tracked = fr24.get_most_tracked_flights()
        return most_tracked[:10] if most_tracked else []
    except Exception as e:
        log.warning(f"Could not fetch most tracked: {e}")
        return []

# ─────────────────────────────────────────────────────────────
# FILTERING
# ─────────────────────────────────────────────────────────────

def get_detection_reason(flight):
    ftype   = (getattr(flight, "aircraft_code", "") or "").upper()
    reg     = (getattr(flight, "registration",  "") or "").upper()
    airline = (getattr(flight, "airline_icao",  "") or "").upper()
    squawk  = (getattr(flight, "squawk",        "") or "")

    if ftype in [t.upper() for t in RARE_TYPES]:
        return "rare"
    if squawk in SQUAWK_WATCH:
        return "squawk"
    if reg in [r.upper() for r in WATCHLIST_REGS]:
        return "registration"
    if airline in [a.upper() for a in WATCHLIST_AIRLINES]:
        return "airline"
    return "type"


def is_excluded(flight):
    ftype   = (getattr(flight, "aircraft_code", "") or "").upper()
    airline = (getattr(flight, "airline_icao",  "") or "").upper()

    if airline in [a.upper() for a in EXCLUDED_AIRLINES]:
        return True
    for combo in EXCLUDED_COMBOS:
        if ftype == combo["type"].upper() and airline == combo["airline"].upper():
            return True
    return False


def matches_watchlist(flight):
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

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def fmt(v):
    return str(v) if v not in [None, "", "None", "N/A"] else "N/A"


def get_aircraft_name(icao):
    icao = (icao or "").upper()
    return AIRCRAFT_NAMES.get(icao, icao if icao else "N/A")


def get_airline_name(icao):
    icao = (icao or "").upper()
    return AIRLINE_NAMES.get(icao, icao if icao else "N/A")


def get_planespotters_image(reg):
    """Fetch first photo thumbnail URL from Planespotters API."""
    if not reg or reg == "N/A":
        return None
    try:
        url = f"https://api.planespotters.net/pub/photos/reg/{reg}"
        r = requests.get(url, timeout=8, headers={"User-Agent": "FR24Monitor/1.0"})
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                src = photos[0].get("thumbnail_large", {}).get("src")
                return src or photos[0].get("thumbnail", {}).get("src")
    except Exception:
        pass
    return None


def get_fr24_link(flight):
    callsign  = getattr(flight, "callsign", "") or ""
    flight_id = getattr(flight, "id",       "") or ""
    if callsign:
        return f"https://www.flightradar24.com/{callsign}/{flight_id}"
    return f"https://www.flightradar24.com/{flight_id}"


def get_jetphotos_link(reg):
    if not reg or reg == "N/A":
        return None
    clean = reg.replace("-", "").replace(" ", "").upper()
    return f"https://www.jetphotos.com/registration/{clean}"


def get_aviationphoto_link(reg):
    if not reg or reg == "N/A":
        return None
    return f"https://www.aviationphotos.net/search/?reg={reg}"


def discord_timestamp(unix_ts):
    try:
        ts = int(unix_ts)
        if ts > 0:
            return f"<t:{ts}:R>"
    except Exception:
        pass
    return "N/A"

# ─────────────────────────────────────────────────────────────
# EMBED COLORS + LABELS
# ─────────────────────────────────────────────────────────────

COLORS = {
    "rare":         0xFF4500,
    "squawk":       0xFFD700,
    "registration": 0x00FF99,
    "airline":      0x1E90FF,
    "type":         0x7289DA,
}

REASON_LABELS = {
    "rare":         "🚨 RARE AIRCRAFT",
    "squawk":       "⚠️ EMERGENCY SQUAWK",
    "registration": "📋 WATCHED REGISTRATION",
    "airline":      "🏢 WATCHED AIRLINE",
    "type":         "✈️ WATCHED TYPE",
}

SQUAWK_MEANINGS = {
    "7500": "Hijacking",
    "7600": "Radio Failure",
    "7700": "Emergency",
}

# ─────────────────────────────────────────────────────────────
# DISCORD
# ─────────────────────────────────────────────────────────────

def build_embed(flight, reason):
    reg      = fmt(getattr(flight, "registration",           None))
    ftype    = fmt(getattr(flight, "aircraft_code",          None))
    callsign = fmt(getattr(flight, "callsign",               None))
    airline  = fmt(getattr(flight, "airline_icao",           None))
    origin   = fmt(getattr(flight, "origin_airport_iata",       None))
    dest     = fmt(getattr(flight, "destination_airport_iata",  None))
    squawk   = fmt(getattr(flight, "squawk",                 None))
    ts       = getattr(flight, "time",           None)
    alt      = getattr(flight, "altitude",       None)
    spd      = getattr(flight, "ground_speed",   None)
    vspd     = getattr(flight, "vertical_speed", None)
    heading  = getattr(flight, "heading",        None)
    lat      = getattr(flight, "latitude",       None)
    lon      = getattr(flight, "longitude",      None)
    icao24   = fmt(getattr(flight, "icao_24bit", None))

    aircraft_full = get_aircraft_name(ftype)
    airline_full  = get_airline_name(airline)

    try:
        alt_str = f"{int(alt):,} ft" if alt and int(alt) > 0 else "N/A"
    except Exception:
        alt_str = "N/A"
    try:
        spd_str = f"{int(spd)} kts" if spd and int(spd) > 0 else "N/A"
    except Exception:
        spd_str = "N/A"
    try:
        vspd_str = f"{int(vspd):+,} fpm" if vspd is not None else "N/A"
    except Exception:
        vspd_str = "N/A"
    try:
        heading_str = f"{int(heading)}°" if heading is not None else "N/A"
    except Exception:
        heading_str = "N/A"
    try:
        pos_str = f"{float(lat):.4f}, {float(lon):.4f}" if lat and lon else "N/A"
    except Exception:
        pos_str = "N/A"

    fr24_link = get_fr24_link(flight)
    jp_link   = get_jetphotos_link(reg)
    ap_link   = get_aviationphoto_link(reg)
    photo_url = get_planespotters_image(reg) if reg != "N/A" else None
    ts_str    = discord_timestamp(ts) if ts else "N/A"

    color = COLORS.get(reason, 0x7289DA)
    label = REASON_LABELS.get(reason, "✈️ WATCHED TYPE")

    links = []
    if fr24_link:
        links.append(f"[FR24 Live]({fr24_link})")
    if jp_link:
        links.append(f"[JetPhotos]({jp_link})")
    if ap_link:
        links.append(f"[AviationPhoto]({ap_link})")

    description = None
    if reason == "squawk":
        meaning = SQUAWK_MEANINGS.get(squawk, "Emergency")
        description = f"**Squawk {squawk} — {meaning}**"

    embed = {
        "title": f"{label} — {reg}",
        "color": color,
        "fields": [
            {"name": "Aircraft",            "value": f"{aircraft_full}\n`{ftype}`",         "inline": True},
            {"name": "Airline",             "value": f"{airline_full}\n`{airline}`",         "inline": True},
            {"name": "Callsign",            "value": callsign,                               "inline": True},
            {"name": "Route",               "value": f"{origin} → {dest}",                  "inline": True},
            {"name": "Squawk",              "value": squawk,                                 "inline": True},
            {"name": "Hex (ICAO 24-bit)",   "value": icao24,                                 "inline": True},
            {"name": "Altitude",            "value": alt_str,                                "inline": True},
            {"name": "Ground Speed",        "value": spd_str,                                "inline": True},
            {"name": "Vertical Speed",      "value": vspd_str,                               "inline": True},
            {"name": "Heading",             "value": heading_str,                            "inline": True},
            {"name": "Position",            "value": pos_str,                                "inline": True},
            {"name": "First Seen",          "value": ts_str,                                 "inline": True},
            {"name": "Links",               "value": " · ".join(links) if links else "N/A", "inline": False},
        ],
        "footer": {"text": f"FR24 Monitor • Detected {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }

    if description:
        embed["description"] = description
    if photo_url:
        embed["image"] = {"url": photo_url}

    return embed


def build_most_tracked_embed(most_tracked):
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
    """Send a message to Discord. embed should be a plain dict (not wrapped)."""
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


def send_flight(flight, reason):
    embed   = build_embed(flight, reason)
    content = "@everyone 🚨 Rare aircraft detected!" if reason == "rare" else None
    send_discord(content=content, embed=embed)
    time.sleep(DISCORD_MESSAGE_DELAY)


def send_summary(total, rare_count, squawk_count, excluded_count):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    send_discord(embed={
        "title": "📊 Scan Complete",
        "color": 0x2ECC71,
        "fields": [
            {"name": "✈️ Flights Shown",  "value": str(total),          "inline": True},
            {"name": "🚨 Rare Detected",  "value": str(rare_count),     "inline": True},
            {"name": "⚠️ Squawk Alerts",  "value": str(squawk_count),   "inline": True},
            {"name": "🚫 Filtered Out",   "value": str(excluded_count), "inline": True},
        ],
        "footer": {"text": f"FR24 Monitor • {now}"},
    })


def send_fetch_error():
    send_discord(embed={
        "title": "❌ FR24 Fetch Failed",
        "description": "Could not reach FlightRadar24. The site may be down or your login details are wrong.",
        "color": 0xFF0000,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    })


def send_zero_flights():
    send_discord(embed={
        "title": "👻 0 Flights Found",
        "description": "Somehow nothing matched your filter this scan.\nConsolation prize: [JetPhotos Latest](https://www.jetphotos.com/latest-photos)",
        "color": 0x95A5A6,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    })

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    log.info("FR24 Monitor starting...")

    fr24, all_flights = fetch_flights()

    if all_flights is None:
        send_fetch_error()
        return

    matched        = []
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
            reason = get_detection_reason(flight)
            if reason == "rare":
                rare_count += 1
            if reason == "squawk":
                squawk_count += 1
            send_flight(flight, reason)

        send_summary(
            total=len(matched),
            rare_count=rare_count,
            squawk_count=squawk_count,
            excluded_count=excluded_count,
        )

    most_tracked = fetch_most_tracked(fr24)
    if most_tracked:
        embed = build_most_tracked_embed(most_tracked)
        if embed:
            time.sleep(DISCORD_MESSAGE_DELAY)
            send_discord(embed=embed)

    log.info("Done.")


if __name__ == "__main__":
    main()
