#!/usr/bin/env python3
"""Download all Garmin Connect stats for the previous calendar month.

Usage:
    export EMAIL="you@example.com"
    export PASSWORD="your_password"
    python3 download_last_month.py

After the first login, tokens are saved to ~/.garminconnect and reused.
"""

import json
import os
import sys
import time
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


def last_calendar_month() -> tuple[date, date]:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_day = first_of_this_month - timedelta(days=1)
    first_day = last_day.replace(day=1)
    return first_day, last_day


def login() -> Garmin:
    tokenstore = str(Path(os.getenv("GARMINTOKENS", "~/.garminconnect")).expanduser())

    try:
        client = Garmin()
        client.login(tokenstore)
        print("Logged in using saved tokens.")
        return client
    except (GarminConnectAuthenticationError, GarminConnectConnectionError):
        print("No valid tokens found — please log in.")

    while True:
        email = os.getenv("EMAIL") or input("Garmin email: ").strip()
        password = os.getenv("PASSWORD") or getpass("Garmin password: ")
        try:
            client = Garmin(
                email=email,
                password=password,
                prompt_mfa=lambda: input("MFA code (leave blank if none): ").strip(),
            )
            client.login(tokenstore)
            print(f"Login successful. Tokens saved to: {tokenstore}")
            return client
        except GarminConnectAuthenticationError:
            print("Wrong credentials — try again.")
        except GarminConnectTooManyRequestsError as err:
            print(f"Rate limit: {err}")
            sys.exit(1)


def safe_call(label: str, func, *args, default=None):
    try:
        return func(*args)
    except Exception as err:
        print(f"  skipped {label}: {err}")
        return default


def main() -> None:
    start_date, end_date = last_calendar_month()
    start = start_date.isoformat()
    end = end_date.isoformat()
    month_label = start_date.strftime("%Y_%m")
    out = Path("your_data") / month_label
    out.mkdir(parents=True, exist_ok=True)

    print(f"Downloading stats for {start} to {end}")
    print(f"Output folder: {out.resolve()}")

    client = login()

    print("\n[1/3] Fetching range metrics...")
    range_data = {
        "daily_steps": safe_call("daily_steps", client.get_daily_steps, start, end, default=[]),
        "body_battery": safe_call("body_battery", client.get_body_battery, start, end, default=[]),
        "progress_summary": safe_call(
            "progress_summary",
            client.get_progress_summary_between_dates,
            start,
            end,
            default={},
        ),
        "blood_pressure": safe_call(
            "blood_pressure", client.get_blood_pressure, start, end, default=[]
        ),
    }
    (out / "range_metrics.json").write_text(
        json.dumps(range_data, indent=2, default=str), encoding="utf-8"
    )
    print("  saved range_metrics.json")

    print("\n[2/3] Fetching daily stats (one request per day)...")
    daily: dict[str, dict] = {}
    current = start_date
    while current <= end_date:
        ds = current.isoformat()
        print(f"  {ds}")
        daily[ds] = {
            "summary": safe_call("summary", client.get_user_summary, ds, default={}),
            "stats": safe_call("stats", client.get_stats, ds, default={}),
            "heart_rate": safe_call("heart_rate", client.get_heart_rates, ds, default={}),
            "sleep": safe_call("sleep", client.get_sleep_data, ds, default={}),
            "stress": safe_call("stress", client.get_all_day_stress, ds, default={}),
            "hrv": safe_call("hrv", client.get_hrv_data, ds, default=None),
        }
        current += timedelta(days=1)
        time.sleep(0.3)
    (out / "daily_stats.json").write_text(
        json.dumps(daily, indent=2, default=str), encoding="utf-8"
    )
    print("  saved daily_stats.json")

    print("\n[3/3] Fetching and downloading activities...")
    activities = safe_call(
        "activities", client.get_activities_by_date, start, end, default=[]
    ) or []
    (out / "activities.json").write_text(
        json.dumps(activities, indent=2, default=str), encoding="utf-8"
    )
    print(f"  found {len(activities)} activities")

    activities_dir = out / "activities"
    activities_dir.mkdir(exist_ok=True)
    for act in activities:
        activity_id = act.get("activityId")
        if not activity_id:
            continue
        name = act.get("activityName", "activity").replace("/", "-")
        try:
            gpx = client.download_activity(
                activity_id, dl_fmt=client.ActivityDownloadFormat.GPX
            )
            path = activities_dir / f"{activity_id}_{name}.gpx"
            path.write_bytes(gpx)
            print(f"  saved {path.name}")
        except Exception as err:
            print(f"  skipped activity {activity_id}: {err}")
        time.sleep(0.3)

    print(f"\nDone. All files are in: {out.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
