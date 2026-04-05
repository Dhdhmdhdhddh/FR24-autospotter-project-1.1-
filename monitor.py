"""
FR24 Rare Plane Monitor — Main Scanner
Queries by type/reg/airline, routes to main or filtered webhook.
Saves seen flight IDs and daily log for dedup and summary.
"""

import os
import json
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from FlightRadar24 import FlightRadar24API

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

FR24_USERNAME             = os.environ.get("FR24_USERNAME", "")
FR24_PASSWORD             = os.environ.get("FR24_PASSWORD", "")
DISCORD_WEBHOOK_URL       = os.environ.get("DISCORD_WEBHOOK_URL", "")       # main
DISCORD_WEBHOOK_FILTERED  = os.environ.get("DISCORD_WEBHOOK_FILTERED", "")  # filtered airlines
DISCORD_MESSAGE_DELAY     = 1.5

SEEN_IDS_FILE  = "seen_ids.json"
DAILY_LOG_FILE = "daily_log.json"

# ── Aircraft type watchlist ───────────────────────────────────
WATCHLIST_TYPES = [
    "L188", "ZZZZ", "B2", "B52",
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
    "NIM", "P3", "SGUP",
    "YK50", "YK42", "YK40",
    "VT23", "WHK2", "VC10",
    "V22", "U2",
    "TRID", "T45", "T204", "T2", "T154", "T134",
    "SLCH", "SHIP", "733",
    "BTB2", "RFAL", "CORS",
    "E6", "E3", "E4", "E8", "VC25",
    "F27", "F28", "F100", "F70",
    "D328", "WB57", "KFIR",
]

WATCHLIST_REGS     = ["N990XB"]
WATCHLIST_AIRLINES = ["IGY"]  # NASA
SQUAWK_WATCH       = ["7500", "7600", "7700"]
RARE_TYPES         = ["E4", "VC25", "WB57", "CONC", "BSCA"]

# Routes to FILTERED webhook instead of being dropped
FILTERED_AIRLINES = [
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
    "VT23": "Vought F4U Corsair", "KFIR": "IAI Kfir",
}

AIRLINE_NAMES = {
    "IGY": "NASA", "DAL": "Delta Air Lines", "AAL": "American Airlines",
    "UAL": "United Airlines", "SWA": "Southwest Airlines", "BAW": "British Airways",
    "DLH": "Lufthansa", "AFR": "Air France", "KLM": "KLM Royal Dutch Airlines",
    "QFA": "Qantas", "SIA": "Singapore Airlines", "UAE": "Emirates",
    "ETH": "Ethiopian Airlines", "MSR": "EgyptAir", "THY": "Turkish Airlines",
    "FDX": "FedEx Express", "UPS": "UPS Airlines", "WGN": "Western Global Airlines",
    "HAL": "Hawaiian Airlines", "ASA": "Alaska Airlines",
    "UTY": "Alliance Airlines", "QLK": "QantasLink",
    "EXS": "Jet2",
    "AVJ": "Avia Traffic Company", "UTA": "UTair", "AFG": "Ariana Afghan Airlines",
    "SJY": "Sriwijaya Air", "TGN": "Trigana Air", "AZG": "Silk Way Airlines",
    "KMF": "Kam Air", "SWT": "Swiftair", "DHL": "DHL",
}

# ─────────────────────────────────────────────────────────────
# PERSISTENT STORAGE
# ─────────────────────────────────────────────────────────────

def load_seen_ids():
    try:
        with open(SEEN_IDS_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("ids", []))
    except Exception:
        return set()


def save_seen_ids(ids):
    try:
        with open(SEEN_IDS_FILE, "w") as f:
            json.dump({"ids": list(ids), "updated": datetime.now(timezone.utc).isoformat()}, f)
    except Exception as e:
        log.warning(f"Could not save seen IDs: {e}")


def load_daily_log():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(DAILY_LOG_FILE, "r") as f:
            data = json.load(f)
            if data.get("date") == today:
                return data
    except Exception:
        pass
    return {"date": today, "total": 0, "rare": 0, "squawk": 0, "filtered": 0, "types": {}}


def save_daily_log(log_data):
    try:
        with open(DAILY_LOG_FILE, "w") as f:
            json.dump(log_data, f)
    except Exception as e:
        log.warning(f"Could not save daily log: {e}")


def update_daily_log(log_data, matched, filtered, rare_count, squawk_count):
    log_data["total"]    += len(matched)
    log_data["rare"]     += rare_count
    log_data["squawk"]   += squawk_count
    log_data["filtered"] += len(filtered)
    for flight in matched:
        ftype = (getattr(flight, "aircraft_code", "") or "N/A").upper()
        log_data["types"][ftype] = log_data["types"].get(ftype, 0) + 1
    return log_data

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
        seen_ids = set()
        all_flights = []

        for ftype in WATCHLIST_TYPES:
            try:
                flights = fr24.get_flights(aircraft_type=ftype)
                new = 0
                for f in flights:
                    fid = getattr(f, "id", None)
                    if fid and fid not in seen_ids:
                        seen_ids.add(fid)
                        all_flights.append(f)
                        new += 1
                if flights:
                    log.info(f"Type {ftype}: {len(flights)} flights, {new} new")
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"Type {ftype} failed: {e}")

        for reg in WATCHLIST_REGS:
            try:
                flights = fr24.get_flights(registration=reg)
                new = 0
                for f in flights:
                    fid = getattr(f, "id", None)
                    if fid and fid not in seen_ids:
                        seen_ids.add(fid)
                        all_flights.append(f)
                        new += 1
                if flights:
                    log.info(f"Reg {reg}: {len(flights)} flights, {new} new")
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"Reg {reg} failed: {e}")

        for airline in WATCHLIST_AIRLINES:
            try:
                flights = fr24.get_flights(airline=airline)
                new = 0
                for f in flights:
                    fid = getattr(f, "id", None)
                    if fid and fid not in seen_ids:
                        seen_ids.add(fid)
                        all_flights.append(f)
                        new += 1
                if flights:
                    log.info(f"Airline {airline}: {len(flights)} flights, {new} new")
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"Airline {airline} failed: {e}")

        log.info(f"Fetched {len(all_flights)} total unique flights")
        return fr24, all_flights
    except Exception as e:
        log.error(f"Failed to fetch FR24 data: {e}")
        return None, None

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


def is_filtered(flight):
    """Returns True if flight should go to filtered webhook instead of main."""
    airline = (getattr(flight, "airline_icao", "") or "").upper()
    return airline in [a.upper() for a in FILTERED_AIRLINES]


def is_excluded(flight):
    """Returns True if flight should be dropped entirely."""
    ftype   = (getattr(flight, "aircraft_code", "") or "").upper()
    airline = (getattr(flight, "airline_icao",  "") or "").upper()
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
    if not reg or reg == "N/A":
        return None
    try:
        url = f"https://api.planespotters.net/pub/photos/reg/{reg}"
        r = requests.get(url, timeout=5, headers={"User-Agent": "FR24Monitor/1.0"})
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                src = photos[0].get("thumbnail_large", {}).get("src")
                return src or photos[0].get("thumbnail", {}).get("src")
    except Exception:
        pass
    return None


def prefetch_images(flights):
    regs = list({fmt(getattr(f, "registration", None)) for f in flights})
    regs = [r for r in regs if r != "N/A"]
    results = {}

    def fetch_one(reg):
        return reg, get_planespotters_image(reg)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_one, reg): reg for reg in regs}
        for future in as_completed(futures):
            try:
                reg, url = future.result()
                results[reg] = url
            except Exception:
                pass

    log.info(f"Prefetched images for {len(results)} registrations")
    return results


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
    "filtered":     0x99AAB5,
}

REASON_LABELS = {
    "rare":         "🚨 RARE AIRCRAFT",
    "squawk":       "⚠️ EMERGENCY SQUAWK",
    "registration": "📋 WATCHED REGISTRATION",
    "airline":      "🏢 WATCHED AIRLINE",
    "type":         "✈️ WATCHED TYPE",
    "filtered":     "📁 FILTERED AIRLINE",
}

SQUAWK_MEANINGS = {
    "7500": "Hijacking",
    "7600": "Radio Failure",
    "7700": "Emergency",
}

# ─────────────────────────────────────────────────────────────
# DISCORD
# ─────────────────────────────────────────────────────────────

def build_embed(flight, reason, image_cache=None, is_new=True):
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
    photo_url = image_cache.get(reg) if image_cache else None
    ts_str    = discord_timestamp(ts) if ts else "N/A"
    status    = "🆕 New" if is_new else "🔄 Still Airborne"

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
            {"name": "Aircraft",          "value": f"{aircraft_full}\n`{ftype}`",         "inline": True},
            {"name": "Airline",           "value": f"{airline_full}\n`{airline}`",         "inline": True},
            {"name": "Callsign",          "value": callsign,                               "inline": True},
            {"name": "Route",             "value": f"{origin} → {dest}",                  "inline": True},
            {"name": "Squawk",            "value": squawk,                                 "inline": True},
            {"name": "Hex (ICAO 24-bit)", "value": icao24,                                 "inline": True},
            {"name": "Altitude",          "value": alt_str,                                "inline": True},
            {"name": "Ground Speed",      "value": spd_str,                                "inline": True},
            {"name": "Vertical Speed",    "value": vspd_str,                               "inline": True},
            {"name": "Heading",           "value": heading_str,                            "inline": True},
            {"name": "Position",          "value": pos_str,                                "inline": True},
            {"name": "First Seen",        "value": ts_str,                                 "inline": True},
            {"name": "Status",            "value": status,                                 "inline": True},
            {"name": "Links",             "value": " · ".join(links) if links else "N/A", "inline": False},
        ],
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }

    if description:
        embed["description"] = description
    if photo_url:
        embed["image"] = {"url": photo_url}

    return embed


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
            retry_after = float(r.json().get("retry_after", 2))
            log.warning(f"Rate limited. Waiting {retry_after}s")
            time.sleep(retry_after)
            requests.post(webhook_url, json=payload, timeout=10)
        elif r.status_code not in (200, 204):
            log.error(f"Discord error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"Discord send failed: {e}")


def send_flight(flight, reason, webhook_url, image_cache=None, is_new=True):
    embed   = build_embed(flight, reason, image_cache=image_cache, is_new=is_new)
    content = "@everyone 🚨 Rare aircraft detected!" if reason == "rare" else None
    send_discord(webhook_url, content=content, embed=embed)
    time.sleep(DISCORD_MESSAGE_DELAY)


def send_summary(total, rare_count, squawk_count, filtered_count):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    send_discord(DISCORD_WEBHOOK_URL, embed={
        "title": "📊 Scan Complete",
        "color": 0x2ECC71,
        "fields": [
            {"name": "✈️ Flights",       "value": str(total),          "inline": True},
            {"name": "🚨 Rare",          "value": str(rare_count),     "inline": True},
            {"name": "⚠️ Squawks",       "value": str(squawk_count),   "inline": True},
            {"name": "📁 Filtered",      "value": str(filtered_count), "inline": True},
        ],
        "footer": {"text": f"FR24 Monitor • {now}"},
    })


def send_fetch_error():
    send_discord(DISCORD_WEBHOOK_URL, embed={
        "title": "❌ FR24 Fetch Failed",
        "description": "Could not reach FlightRadar24. The site may be down or your login details are wrong.",
        "color": 0xFF0000,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    })


def send_zero_flights():
    send_discord(DISCORD_WEBHOOK_URL, embed={
        "title": "👻 0 Flights Found",
        "description": "Nothing matched this scan.\nConsolation prize: [JetPhotos Latest](https://www.jetphotos.com/latest-photos)",
        "color": 0x95A5A6,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    })

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    log.info("FR24 Monitor starting...")

    previous_seen_ids = load_seen_ids()
    daily_log         = load_daily_log()

    fr24, all_flights = fetch_flights()
    if all_flights is None:
        send_fetch_error()
        return

    matched  = []
    filtered = []

    for flight in all_flights:
        if not matches_watchlist(flight):
            continue
        if is_excluded(flight):
            continue
        if is_filtered(flight):
            filtered.append(flight)
        else:
            matched.append(flight)

    log.info(f"{len(matched)} main, {len(filtered)} filtered")

    all_to_send = matched + filtered

    if not all_to_send:
        send_zero_flights()
        return

    # Prefetch all images in parallel
    log.info("Prefetching images...")
    image_cache = prefetch_images(all_to_send)

    rare_count   = 0
    squawk_count = 0
    current_ids  = set()

    # Send main flights
    for flight in matched:
        fid    = getattr(flight, "id", None)
        is_new = fid not in previous_seen_ids
        if fid:
            current_ids.add(fid)

        reason = get_detection_reason(flight)
        if reason == "rare":
            rare_count += 1
        if reason == "squawk":
            squawk_count += 1

        send_flight(flight, reason, DISCORD_WEBHOOK_URL, image_cache=image_cache, is_new=is_new)

    # Send filtered flights
    for flight in filtered:
        fid    = getattr(flight, "id", None)
        is_new = fid not in previous_seen_ids
        if fid:
            current_ids.add(fid)
        send_flight(flight, "filtered", DISCORD_WEBHOOK_FILTERED, image_cache=image_cache, is_new=is_new)

    send_summary(
        total=len(matched),
        rare_count=rare_count,
        squawk_count=squawk_count,
        filtered_count=len(filtered),
    )

    # Update persistent storage
    save_seen_ids(current_ids)
    daily_log = update_daily_log(daily_log, matched, filtered, rare_count, squawk_count)
    save_daily_log(daily_log)

    log.info("Done.")


if __name__ == "__main__":
    main()
