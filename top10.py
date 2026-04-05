"""
FR24 Top 10 Most Tracked — Lightweight poller
Posts top 10 most tracked flights to its own webhook.
Triggered every 30 seconds via cron-job.org.
"""

import os
import time
import logging
import requests
from datetime import datetime, timezone
from FlightRadar24 import FlightRadar24API

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FR24_USERNAME          = os.environ.get("FR24_USERNAME", "")
FR24_PASSWORD          = os.environ.get("FR24_PASSWORD", "")
DISCORD_WEBHOOK_TOP10  = os.environ.get("DISCORD_WEBHOOK_TOP10", "")


def fetch_most_tracked():
    try:
        fr24 = FlightRadar24API(FR24_USERNAME, FR24_PASSWORD)
        result = fr24.get_most_tracked()
        if isinstance(result, dict):
            flights = result.get("flights", result.get("data", []))
        elif isinstance(result, list):
            flights = result
        else:
            flights = []
        return flights[:10]
    except Exception as e:
        log.warning(f"Could not fetch most tracked: {e}")
        return []


def send_discord(webhook_url, embed):
    if not webhook_url:
        return
    try:
        r = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)))
            requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        elif r.status_code not in (200, 204):
            log.error(f"Discord error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"Discord send failed: {e}")


def main():
    log.info("Top 10 fetcher starting...")
    most_tracked = fetch_most_tracked()

    if not most_tracked:
        log.info("No data returned.")
        return

    lines = []
    for i, flight in enumerate(most_tracked, 1):
        try:
            callsign = flight.get("callsign", "N/A")
            ftype    = flight.get("model", "N/A")
            count    = flight.get("clicks", "?")
            lines.append(f"`{i}.` **{callsign}** — {ftype} — {count} trackers")
        except Exception:
            lines.append(f"`{i}.` Data unavailable")

    embed = {
        "title": "📡 Top 10 Most Tracked Right Now",
        "description": "\n".join(lines),
        "color": 0x9B59B6,
        "footer": {"text": f"FR24 Monitor • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }

    send_discord(DISCORD_WEBHOOK_TOP10, embed)
    log.info("Done.")


if __name__ == "__main__":
    main()
