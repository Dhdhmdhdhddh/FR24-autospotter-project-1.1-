import os
import asyncio
import time
import logging
import requests
from datetime import datetime, timezone
from fr24 import FR24

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DISCORD_WEBHOOK_TOP10 = os.environ.get("DISCORD_WEBHOOK_TOP10", "")


async def fetch_top_flights():
    try:
        async with FR24() as client:
            result = await client.top_flights.fetch(limit=10)
            data = result.to_dict()
            return data.get("flights", [])
    except Exception as e:
        log.warning(f"Could not fetch top flights: {e}")
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
    flights = asyncio.run(fetch_top_flights())

    if not flights:
        log.info("No data returned.")
        return

    log.info(f"Raw first flight: {flights[0] if flights else 'empty'}")

    lines = []
    for i, flight in enumerate(flights[:10], 1):
        try:
            callsign = flight.get("callsign") or flight.get("flight") or "N/A"
            ftype    = flight.get("type") or flight.get("model") or "N/A"
            origin   = flight.get("from_city") or flight.get("from_iata") or "N/A"
            dest     = flight.get("to_city") or flight.get("to_iata") or "N/A"
            trackers = flight.get("viewers") or flight.get("tracking") or flight.get("clicks") or "?"
            lines.append(f"`{i}.` **{callsign}** — {ftype} — {origin} → {dest} — {trackers} 👁️")
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
