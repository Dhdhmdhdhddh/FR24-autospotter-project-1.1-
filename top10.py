import os
import time
import logging
import requests
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DISCORD_WEBHOOK_TOP10 = os.environ.get("DISCORD_WEBHOOK_TOP10", "")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.flightradar24.com/",
    "Origin": "https://www.flightradar24.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_most_tracked():
    try:
        r = requests.get(
            "https://www.flightradar24.com/flights/most-tracked",
            headers=BROWSER_HEADERS,
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        flights = data.get("data", data.get("flights", []))
        return flights[:10]
    except Exception as e:
        log.warning(f"Could not fetch most tracked: {e}")
        return []


def fetch_tracker_count(flight_id):
    try:
        r = requests.get(
            f"https://data-live.flightradar24.com/clickhandler/?flight={flight_id}",
            headers=BROWSER_HEADERS,
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("stats", {}).get("visible", {}).get("tracking", None)
    except Exception as e:
        log.warning(f"Tracker fetch exception for {flight_id}: {e}")
    return None


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
            callsign   = flight.get("callsign") or flight.get("flight") or "N/A"
            ftype      = flight.get("type") or flight.get("model") or "N/A"
            origin     = flight.get("from_city") or flight.get("from_iata") or "N/A"
            dest       = flight.get("to_city") or flight.get("to_iata") or "N/A"
            flight_id  = flight.get("flight_id")
            trackers   = fetch_tracker_count(flight_id) if flight_id else None
            count_str  = f"{trackers:,} trackers" if trackers else f"{flight.get('clicks', '?')} clicks"
            lines.append(f"`{i}.` **{callsign}** — {ftype} — {origin} → {dest} — {count_str}")
            time.sleep(0.3)
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
