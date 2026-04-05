"""
FR24 Daily Summary
Reads daily_log.json and posts a summary to the summary webhook.
Triggered once a day at midnight UTC.
"""

import os
import json
import logging
import requests
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DISCORD_WEBHOOK_SUMMARY = os.environ.get("DISCORD_WEBHOOK_SUMMARY", "")
DAILY_LOG_FILE          = "daily_log.json"

AIRCRAFT_NAMES = {
    "B741": "Boeing 747-100", "B742": "Boeing 747-200", "B74S": "Boeing 747SP",
    "B732": "Boeing 737-200", "B733": "Boeing 737-300", "B734": "Boeing 737-400",
    "B735": "Boeing 737-500", "B717": "Boeing 717",
    "B722": "Boeing 727-200", "B703": "Boeing 707-300",
    "B52": "B-52 Stratofortress", "B2": "B-2 Spirit", "B1": "B-1 Lancer",
    "DC3": "Douglas DC-3", "DC10": "DC-10",
    "MD11": "MD-11", "MD81": "MD-81", "MD82": "MD-82", "MD83": "MD-83",
    "A124": "An-124 Ruslan", "AN12": "An-12", "AN26": "An-26",
    "IL62": "Il-62", "IL76": "Il-76",
    "T154": "Tu-154", "T134": "Tu-134",
    "L101": "L-1011 TriStar", "L188": "L-188 Electra",
    "F22": "F-22 Raptor", "F35": "F-35 Lightning II",
    "F16": "F-16 Falcon", "F15": "F-15 Eagle", "F18": "F/A-18 Hornet",
    "P3": "P-3 Orion", "U2": "U-2", "V22": "V-22 Osprey",
    "VC25": "VC-25 (Air Force One)", "E4": "E-4B Nightwatch",
    "E3": "E-3 Sentry", "E6": "E-6 Mercury",
    "WB57": "WB-57", "CONC": "Concorde", "KFIR": "IAI Kfir",
    "F100": "Fokker 100", "F70": "Fokker 70",
}


def send_discord(embed):
    if not DISCORD_WEBHOOK_SUMMARY:
        return
    try:
        r = requests.post(DISCORD_WEBHOOK_SUMMARY, json={"embeds": [embed]}, timeout=10)
        if r.status_code not in (200, 204):
            log.error(f"Discord error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"Discord send failed: {e}")


def main():
    log.info("Daily summary starting...")

    try:
        with open(DAILY_LOG_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        log.warning("No daily log found.")
        send_discord({
            "title": "📅 Daily Summary",
            "description": "No flight data was recorded today.",
            "color": 0x95A5A6,
            "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"},
        })
        return

    date         = data.get("date", "Unknown")
    total        = data.get("total", 0)
    rare         = data.get("rare", 0)
    squawk       = data.get("squawk", 0)
    filtered     = data.get("filtered", 0)
    types        = data.get("types", {})

    # Top 10 aircraft types spotted today
    top_types = sorted(types.items(), key=lambda x: x[1], reverse=True)[:10]
    type_lines = []
    for code, count in top_types:
        name = AIRCRAFT_NAMES.get(code.upper(), code)
        type_lines.append(f"`{code}` {name} — **{count}**")

    type_str = "\n".join(type_lines) if type_lines else "No data"

    embed = {
        "title": f"📅 Daily Summary — {date}",
        "color": 0x3498DB,
        "fields": [
            {"name": "✈️ Total Flights Spotted", "value": str(total),    "inline": True},
            {"name": "🚨 Rare Detections",        "value": str(rare),     "inline": True},
            {"name": "⚠️ Squawk Alerts",          "value": str(squawk),   "inline": True},
            {"name": "📁 Filtered Flights",        "value": str(filtered), "inline": True},
            {"name": "🏆 Top Aircraft Types Today", "value": type_str,    "inline": False},
        ],
        "footer": {"text": f"FR24 Monitor • Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }

    send_discord(embed)
    log.info("Daily summary sent.")


if __name__ == "__main__":
    main()
