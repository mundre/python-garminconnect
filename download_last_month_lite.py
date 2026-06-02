#!/usr/bin/env python3
"""Lightweight export: daily steps + activity list for the previous calendar month.

Requires a prior login via example.py (tokens in ~/.garminconnect).

Usage:
    source .venv/bin/activate
    python3 download_last_month_lite.py
"""

import json
from datetime import date, timedelta
from pathlib import Path

from garminconnect import Garmin, GarminConnectConnectionError


def last_calendar_month() -> tuple[date, date]:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_day = first_of_this_month - timedelta(days=1)
    return last_day.replace(day=1), last_day


def main() -> None:
    start_date, end_date = last_calendar_month()
    start, end = start_date.isoformat(), end_date.isoformat()
    out = Path("your_data") / start_date.strftime("%Y_%m")
    out.mkdir(parents=True, exist_ok=True)

    client = Garmin()
    try:
        client.login("~/.garminconnect")
    except GarminConnectConnectionError as err:
        raise SystemExit(f"Login failed — run example.py first.\n{err}") from err

    export = {
        "period": {"start": start, "end": end},
        "daily_steps": client.get_daily_steps(start, end),
        "activities": client.get_activities_by_date(start, end),
    }

    path = out / "export_lite.json"
    path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")

    print(f"Saved {path} ({len(export['activities'])} activities)")


if __name__ == "__main__":
    main()
