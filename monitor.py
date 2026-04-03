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

# These are loaded from GitHub Secrets — do not paste values here
FR24_USERNAME        = os.environ.get("FR24_USERNAME", "")
FR24_PASSWORD        = os.environ.get("FR24_PASSWORD", "")
DISCORD_WEBHOOK_URL  = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Seconds to wait between Discord messages (avoids rate limiting)
DISCORD_MESSAGE_DELAY = 1.5

# ── Aircraft type watchlist ───────────────────────────────────
# All flights matching these ICAO type codes will appear in the hourly report
WATCHLIST_TYPES = [
    "L188", "ZZZZ", "B2",
    "B52",
    "A124", "A148", "A310", "A3ST",
    "AN12", "AN22", "AN26", "AN30", "AN32", "AN72", "AN74",
    "B779", "B74S", "B742", "B741", "B732", "B722", "B703", "B720",
    "B1",
    "DC6", "DC5", "DC4", "DC3", "DC2", "DC10", "DC1", "DC7", "DC87", "DC91", "DC9",
    "C144", "BSCA", "CONC", "BER2", "BER1", "BALL", "DC7",
    "F1", "F104", "F11", "F12", "F14", "F2", "F22", "F35", "F4", "F5", "F16", "F15", "F18",
    "IL62", "IL76", "IL18",
    "L101", "L410",
    "MD10", "MD81", "MD82", "MD83", "MD87", "MD88", "MD90",
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
    "E6", "E3", "E8",
    "F27", "F28", "F100", "F70",
    "D328",
    "WB57",
]

# ── Registration watchlist ────────────────────────────────────
WATCHLIST_REGS = [
    "N990XB",
]

# ── Airline watchlist ─────────────────────────────────────────
# ICAO airline codes
WATCHLIST_AIRLINES = [
    "IGY",  # NASA
]

# ── Squawk codes to flag ──────────────────────────────────────
# These will be noted in the embed with a warning
SQUAWK_WATCH = ["7500", "7600", "7700"]

# ── Rare tier — triggers @everyone ───────────────────────────
RARE_TYPES = ["E4", "VC25", "WB57", "CONC", "BSCA"]

# ─────────────────────────────────────────────────────────────
# FR24 FETCHING
# ─────────────────────────────────────────────────────────────

def fetch_flights():
    """Login to FR24 and fetch all live flights."""
    try:
        fr24 = FlightRadar24API(FR24_USERNAME, FR24_PASSWORD)
        flights = fr24.get_flights()
        log.info(f"Fetched {len(flights)} total flights from FR24")
        return fr24, flights
    except Exception as e:
        log.error(f"Failed to fetch FR24 data: {e}")
        return None, None


def get_flight_details(fr24, flight):
    """Fetch detailed info for a single flight."""
    try:
        details = fr24.get_flight_details(flight)
        return details
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# FILTERING
# ─────────────────────────────────────────────────────────────

def matches_watchlist(flight):
    """Return True if flight matches any watchlist criteria."""
    ftype    = (getattr(flight, "aircraft_code", "") or "").upper()
    reg      = (getattr(flight, "registration",  "") or "").upper()
    airline  = (getattr(flight, "airline_icao",  "") or "").upper()
    squawk   = (getattr(flight, "squawk",        "") or "")

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
    """Return value with optional suffix, or N/A if empty."""
    if val is None or str(val).strip() in ("", "0", "None"):
        return "N/A"
    return f"{val}{suffix}"


def get_jetphotos_link(reg):
    if not reg or reg == "N/A":
        return "N/A"
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
    alt      = getattr(flight, "altitude", None)
    spd      = getattr(flight, "ground_speed", None)
    squawk   = safe(getattr(flight, "squawk", None))

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

    jp_val   = f"[Photos]({jp_link})"   if jp_link   != "N/A" else "N/A"
    fr24_val = f"[Track]({fr24_link})"  if fr24_link else "N/A"

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
            {"name": "Registration",  "value": reg,                   "inline": True},
            {"name": "Aircraft Type", "value": ftype,                  "inline": True},
            {"name": "Callsign",      "value": callsign,               "inline": True},
            {"name": "Airline",       "value": airline,                "inline": True},
            {"name": "Route",         "value": f"{origin} → {dest}",  "inline": True},
            {"name": "Squawk",        "value": squawk,                 "inline": True},
            {"name": "Altitude",      "value": alt_str,                "inline": True},
            {"name": "Speed",         "value": spd_str,                "inline": True},
            {"name": "First Seen",    "value": age,                    "inline": True},
            {"name": "FR24 Live",     "value": fr24_val,               "inline": True},
            {"name": "JetPhotos",     "value": jp_val,                 "inline": True},
        ],
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


def send_summary(total, rare_count, squawk_count):
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    embed = {
        "title": "📊 Hourly Scan Complete",
        "color": 0x2ECC71,
        "fields": [
            {"name": "Flights Found",   "value": str(total),        "inline": True},
            {"name": "Rare Detected",   "value": str(rare_count),   "inline": True},
            {"name": "Squawk Alerts",   "value": str(squawk_count), "inline": True},
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

    matched = [f for f in all_flights if matches_watchlist(f)]
    log.info(f"{len(matched)} flights matched watchlist")

    if not matched:
        send_zero_flights()
        return

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

    send_summary(total=len(matched), rare_count=rare_count, squawk_count=squawk_count)
    log.info(f"Done. {len(matched)} matched, {rare_count} rare, {squawk_count} squawk alerts.")


if __name__ == "__main__":
    main()
