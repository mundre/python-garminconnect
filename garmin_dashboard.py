#!/usr/bin/env python3
"""Generate a Grafana-style health dashboard from Garmin Connect data.

Modes:
  weekly  — last complete Mon–Sun week (intended to run on Mondays)
  monthly — full previous calendar month (intended to run on the 1st)
  auto    — weekly on Mondays, monthly on the 1st, else last complete week

Usage:
    source .venv/bin/activate
    python3 garmin_dashboard.py --mode monthly              # email-friendly HTML (default)
    python3 garmin_dashboard.py --mode weekly --format dashboard --open
    python3 garmin_dashboard.py --mode weekly --format email_dashboard

Requires tokens from example.py. Reuses your_data/*/daily_stats.json when available.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from garminconnect import Garmin, GarminConnectConnectionError

OUTPUT_DIR = Path("your_data/dashboards")
STEP_GOAL = 10_000
ACTIVE_CAL_GOAL = 500
SLEEP_SCORE_WARN = 90
SLEEP_SCORE_MAX = 100
ACTIVITY_IMPACT_GOAL = 8.0
READINESS_GOOD = 70
READINESS_WARN = 50
BODY_BATTERY_GOOD = 70
BODY_BATTERY_WARN = 40
STRESS_GOOD = 25
STRESS_WARN = 50
STRESS_BAD = 75

COLOR_GOOD = "#73bf69"
COLOR_WARN = "#ff9830"
COLOR_BAD = "#f2495c"
COLOR_NEUTRAL = "rgba(87, 148, 242, 0.55)"
COLOR_ACCENT = "#5794f2"
WEEKEND_SHADE = "rgba(255, 255, 255, 0.06)"
COLOR_YELLOW = "#fade2a"

TRAINING_STATUS_COLORS = {
    "MAINTAINING": "#fade2a",
    "PRODUCTIVE": "#73bf69",
    "STRAINED": "#e03184",
    "RECOVERY": "#5794f2",
    "OVERREACHING": "#f2495c",
    "PEAKING": "#b877d9",
    "DETRAINING": "#8e8e8e",
    "UNPRODUCTIVE": "#8e8e8e",
}

TRAINING_STATUS_BY_ID = {
    1: "DETRAINING",
    2: "UNPRODUCTIVE",
    3: "OVERREACHING",
    4: "MAINTAINING",
    5: "RECOVERY",
    6: "PEAKING",
    7: "PRODUCTIVE",
    8: "STRAINED",
    9: "OVERREACHING",
}


def last_complete_week(ref: date | None = None) -> tuple[date, date]:
    ref = ref or date.today()
    if ref.weekday() == 6:
        end = ref
    else:
        end = ref - timedelta(days=ref.weekday() + 1)
    return end - timedelta(days=6), end


def last_calendar_month(ref: date | None = None) -> tuple[date, date]:
    ref = ref or date.today()
    first_this = ref.replace(day=1)
    last_day = first_this - timedelta(days=1)
    return last_day.replace(day=1), last_day


def resolve_period(mode: str, ref: date | None = None) -> tuple[str, date, date]:
    ref = ref or date.today()
    if mode == "auto":
        if ref.day == 1:
            mode = "monthly"
        elif ref.weekday() == 0:
            mode = "weekly"
        else:
            mode = "weekly"
    if mode == "monthly":
        start, end = last_calendar_month(ref)
    elif mode == "weekly":
        start, end = last_complete_week(ref)
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return mode, start, end


def iter_dates(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def cache_path_for(start: date) -> Path:
    return Path("your_data") / start.strftime("%Y_%m") / "daily_stats.json"


def training_cache_path(month: date) -> Path:
    return Path("your_data") / month.strftime("%Y_%m") / "training_metrics.json"


def parse_training_readiness(response: Any) -> int | None:
    if not isinstance(response, list) or not response:
        return None
    scored = [item for item in response if item.get("score") is not None]
    if not scored:
        return None
    return int(max(scored, key=lambda item: item["score"])["score"])


def parse_training_status(response: dict[str, Any]) -> str | None:
    """Extract training status label (e.g. PRODUCTIVE) from API response."""
    block = response.get("mostRecentTrainingStatus") or {}
    devices = block.get("latestTrainingStatusData") or {}
    if not devices:
        return None

    data: dict[str, Any] | None = None
    for entry in devices.values():
        if entry.get("primaryTrainingDevice"):
            data = entry
            break
    if data is None:
        data = next(iter(devices.values()))

    phrase = data.get("trainingStatusFeedbackPhrase") or ""
    if phrase:
        return phrase.split("_")[0].upper()

    status_id = data.get("trainingStatus")
    if status_id is not None:
        return TRAINING_STATUS_BY_ID.get(int(status_id))
    return None


def load_cached_days(start: date, end: date) -> dict[str, Any] | None:
    """Load daily_stats.json if it fully covers the requested period."""
    needed = {d.isoformat() for d in iter_dates(start, end)}
    if start.month == end.month:
        paths = [cache_path_for(start)]
    else:
        paths = [cache_path_for(start), cache_path_for(end)]

    merged: dict[str, Any] = {}
    for path in paths:
        if not path.exists():
            return None
        merged.update(json.loads(path.read_text(encoding="utf-8")))

    if not needed.issubset(merged.keys()):
        return None
    return {day: merged[day] for day in sorted(needed)}


def login() -> Garmin:
    client = Garmin()
    try:
        client.login(os.getenv("GARMINTOKENS", "~/.garminconnect"))
    except GarminConnectConnectionError as err:
        raise SystemExit(f"Login failed — run example.py first.\n{err}") from err
    return client


def fetch_days(client: Garmin, start: date, end: date) -> dict[str, Any]:
    days: dict[str, Any] = {}
    for current in iter_dates(start, end):
        ds = current.isoformat()
        print(f"  fetching {ds}")
        days[ds] = {
            "summary": client.get_user_summary(ds),
            "sleep": client.get_sleep_data(ds),
            "hrv": client.get_hrv_data(ds),
        }
        time.sleep(0.25)
    return days


def ensure_training_metrics(
    client: Garmin, start: date, end: date, force: bool = False
) -> dict[str, dict[str, Any]]:
    """Load or fetch per-day training status, endurance score, and training readiness."""
    result: dict[str, dict[str, Any]] = {}
    month_caches: dict[str, dict[str, Any]] = {}

    for current in iter_dates(start, end):
        month_key = current.strftime("%Y_%m")
        if month_key not in month_caches:
            path = training_cache_path(current)
            if path.exists() and not force:
                month_caches[month_key] = json.loads(path.read_text(encoding="utf-8"))
            else:
                month_caches[month_key] = {}

    def _needs_fetch(entry: dict[str, Any] | None) -> bool:
        if not entry:
            return True
        return (
            entry.get("training_status") is None
            or entry.get("endurance_score") is None
            or entry.get("training_readiness_score") is None
        )

    for current in iter_dates(start, end):
        ds = current.isoformat()
        month_key = current.strftime("%Y_%m")
        cached = month_caches[month_key].get(ds)
        if not force and cached and not _needs_fetch(cached):
            result[ds] = cached
            continue

        print(f"  training metrics {ds}")
        entry = dict(cached) if cached else {}
        try:
            if force or entry.get("training_status") is None:
                entry["training_status"] = parse_training_status(
                    client.get_training_status(ds)
                )
            if force or entry.get("endurance_score") is None:
                endurance = client.get_endurance_score(ds)
                entry["endurance_score"] = (
                    endurance.get("overallScore")
                    if isinstance(endurance, dict)
                    else None
                )
            if force or entry.get("training_readiness_score") is None:
                entry["training_readiness_score"] = parse_training_readiness(
                    client.get_training_readiness(ds)
                )
        except Exception as err:
            print(f"    skipped: {err}")
            entry.setdefault("training_status", None)
            entry.setdefault("endurance_score", None)
            entry.setdefault("training_readiness_score", None)

        result[ds] = entry
        month_caches[month_key][ds] = entry
        time.sleep(0.25)

    for month_key, cache in month_caches.items():
        year, month = map(int, month_key.split("_"))
        path = training_cache_path(date(year, month, 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, default=str), encoding="utf-8")

    return result


def activities_cache_path(month: date) -> Path:
    return Path("your_data") / month.strftime("%Y_%m") / "activities.json"


def _activity_date(activity: dict[str, Any]) -> date | None:
    start = activity.get("startTimeLocal") or ""
    if len(start) < 10:
        return None
    return date.fromisoformat(start[:10])


def _format_activity_type(activity: dict[str, Any]) -> str:
    key = (activity.get("activityType") or {}).get("typeKey") or "unknown"
    return key.replace("_v2", "").replace("_", " ").title()


def _fitness_impact(activity: dict[str, Any]) -> float:
    aerobic = float(activity.get("aerobicTrainingEffect") or 0)
    anaerobic = float(activity.get("anaerobicTrainingEffect") or 0)
    return round(aerobic + anaerobic, 1)


def _activity_chart_label(activity: dict[str, Any]) -> str:
    activity_date = _activity_date(activity)
    start = activity.get("startTimeLocal") or ""
    if activity_date and len(start) >= 16:
        return f"{activity_date.strftime('%b %d')} {start[11:16]}"
    if activity_date:
        return activity_date.strftime("%a %b %d")
    return "—"


def _activity_impact_row(activity: dict[str, Any]) -> dict[str, Any]:
    activity_date = _activity_date(activity)
    start = activity.get("startTimeLocal") or ""
    time_display = start[11:16] if len(start) >= 16 else ""
    date_display = activity_date.isoformat() if activity_date else "—"
    if time_display:
        date_display = f"{date_display} {time_display}"

    return {
        "name": activity.get("activityName") or "Activity",
        "date": date_display,
        "chart_label": _activity_chart_label(activity),
        "type": _format_activity_type(activity),
        "aerobic_te": round(float(activity.get("aerobicTrainingEffect") or 0), 1),
        "anaerobic_te": round(float(activity.get("anaerobicTrainingEffect") or 0), 1),
        "impact": _fitness_impact(activity),
        "training_load": round(float(activity.get("activityTrainingLoad") or 0)),
        "label": activity.get("trainingEffectLabel") or "—",
        "start_time": start,
    }


def _duration_minutes(activity: dict[str, Any]) -> int:
    duration = activity.get("duration") or activity.get("elapsedDuration") or 0
    return round(float(duration) / 60)


def ensure_activities(
    client: Garmin, start: date, end: date, force: bool = False
) -> list[dict[str, Any]]:
    cached: list[dict[str, Any]] = []
    seen_months: set[str] = set()

    for current in iter_dates(start, end):
        month_key = current.strftime("%Y_%m")
        if month_key in seen_months:
            continue
        seen_months.add(month_key)
        year, month = map(int, month_key.split("_"))
        path = activities_cache_path(date(year, month, 1))
        if path.exists() and not force:
            cached.extend(json.loads(path.read_text(encoding="utf-8")))

    def in_range(activity: dict[str, Any]) -> bool:
        activity_date = _activity_date(activity)
        return activity_date is not None and start <= activity_date <= end

    filtered = [activity for activity in cached if in_range(activity)]
    if filtered:
        return filtered

    print("Fetching activities from Garmin Connect...")
    fetched = client.get_activities_by_date(start.isoformat(), end.isoformat())

    by_month: dict[str, list[dict[str, Any]]] = {}
    for activity in fetched:
        activity_date = _activity_date(activity)
        if activity_date is None:
            continue
        month_key = activity_date.strftime("%Y_%m")
        by_month.setdefault(month_key, []).append(activity)

    for month_key, month_activities in by_month.items():
        year, month = map(int, month_key.split("_"))
        path = activities_cache_path(date(year, month, 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(month_activities, indent=2, default=str), encoding="utf-8")

    return fetched


def analyze_activities(
    activities: list[dict[str, Any]], period_rows: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    total = len(activities)
    type_counts: dict[str, int] = {}
    type_minutes: dict[str, int] = {}

    for activity in activities:
        activity_type = _format_activity_type(activity)
        type_counts[activity_type] = type_counts.get(activity_type, 0) + 1
        type_minutes[activity_type] = type_minutes.get(activity_type, 0) + _duration_minutes(activity)

    breakdown = [
        {
            "type": activity_type,
            "count": count,
            "share_pct": round(100 * count / total, 1) if total else 0,
            "minutes": type_minutes[activity_type],
        }
        for activity_type, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    ranked = sorted(
        activities,
        key=lambda activity: (
            _fitness_impact(activity),
            float(activity.get("activityTrainingLoad") or 0),
        ),
        reverse=True,
    )

    chronological = sorted(activities, key=lambda activity: activity.get("startTimeLocal") or "")
    all_impacts_chronological = [_activity_impact_row(activity) for activity in chronological]
    ranked_impacts = [_activity_impact_row(activity) for activity in ranked]
    for row in ranked_impacts + all_impacts_chronological:
        row["is_good_impact"] = row["impact"] > ACTIVITY_IMPACT_GOAL
    for index, row in enumerate(ranked_impacts, start=1):
        row["rank"] = index

    return {
        "total": total,
        "breakdown": breakdown,
        "top_impact": ranked_impacts[0] if ranked_impacts else None,
        "ranked_impacts": ranked_impacts,
        "all_impacts_chronological": all_impacts_chronological,
        "daily_impacts": _daily_activity_impact_rows(period_rows or [], activities),
    }


def _render_activity_breakdown_table(summary: dict[str, Any]) -> str:
    if not summary["breakdown"]:
        return '<tr><td colspan="5" class="muted">No activities in this period</td></tr>'

    rows = []
    for row in summary["breakdown"]:
        rows.append(
            f"""          <tr>
            <td>{row['type']}</td>
            <td>{row['count']}</td>
            <td>{row['share_pct']}%</td>
            <td>{row['minutes']} min</td>
            <td class="bar-cell"><span class="share-bar" style="width:{row['share_pct']}%"></span></td>
          </tr>"""
        )
    return "\n".join(rows)


def _render_fitness_impact_table(summary: dict[str, Any]) -> str:
    impacts = summary.get("ranked_impacts") or []
    if not impacts:
        return '<tr><td colspan="5" class="muted">No activities in this period</td></tr>'

    rows = []
    for row in impacts:
        row_class = "highlight-row" if row.get("is_good_impact") else ""
        pill_class = "good" if row.get("is_good_impact") else "neutral"
        rows.append(
            f"""          <tr class="{row_class}">
            <td>{row['name']}</td>
            <td>{row['date']}</td>
            <td>{row['aerobic_te']}</td>
            <td>{row['anaerobic_te']}</td>
            <td><span class="pill {pill_class}">{row['impact']}</span></td>
          </tr>"""
        )
    return "\n".join(rows)


def _daily_activity_impact_rows(
    period_rows: list[dict[str, Any]], activities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for activity in sorted(activities, key=lambda item: item.get("startTimeLocal") or ""):
        activity_date = _activity_date(activity)
        if not activity_date:
            continue
        by_day.setdefault(activity_date.isoformat(), []).append(_activity_impact_row(activity))

    return [
        {
            "date": row["date"],
            "label": row["label"],
            "activities": by_day.get(row["date"], []),
        }
        for row in period_rows
    ]


def _svg_activity_impact_chart(daily_rows: list[dict[str, Any]]) -> str:
    n = len(daily_rows)
    if n == 0:
        return "<p>No data</p>"

    width, height, pad_l, pad_r, pad_t, pad_b = 680, 200, 48, 16, 12, 52
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b

    all_impacts = [
        float(act["impact"])
        for day in daily_rows
        for act in day.get("activities") or []
    ]
    if not all_impacts:
        return "<p>No activities in this period</p>"

    max_val = max(max(all_impacts), ACTIVITY_IMPACT_GOAL, 1.0) * 1.08

    bar_gap = 2
    bar_w = max(4, (chart_w - bar_gap * (n - 1)) / n)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="200" '
        f'role="img" aria-label="Activity fitness impact chart">',
    ]
    parts.extend(
        _svg_weekend_bands_discrete(
            daily_rows, pad_l=pad_l, pad_t=pad_t, chart_h=chart_h, bar_w=bar_w, bar_gap=bar_gap
        )
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h}" x2="{width - pad_r}" '
        f'y2="{pad_t + chart_h}" stroke="#2c3235"/>'
    )

    for i in range(5):
        y_val = max_val * (4 - i) / 4
        y = pad_t + chart_h * i / 4
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4}" fill="#8e8e8e" font-size="10" '
            f'text-anchor="end">{y_val:.1f}</text>'
        )
        if i < 4:
            parts.append(
                f'<line x1="{pad_l}" y1="{y}" x2="{width - pad_r}" y2="{y}" '
                f'stroke="#2c3235" stroke-dasharray="3,4"/>'
            )

    goal_y = pad_t + chart_h - (ACTIVITY_IMPACT_GOAL / max_val) * chart_h
    parts.append(
        f'<line x1="{pad_l}" y1="{goal_y:.1f}" x2="{width - pad_r}" y2="{goal_y:.1f}" '
        f'stroke="{COLOR_GOOD}" stroke-dasharray="6,4" opacity="0.85"/>'
    )

    for i, day in enumerate(daily_rows):
        activities = day.get("activities") or []
        x_day = pad_l + i * (bar_w + bar_gap)
        sub_gap = 1
        count = len(activities)

        if count == 1:
            sub_bars = [(x_day, bar_w, activities[0])]
        elif count >= 2:
            sub_w = max(2, (bar_w - sub_gap * (count - 1)) / count)
            sub_bars = [
                (x_day + j * (sub_w + sub_gap), sub_w, activities[j]) for j in range(count)
            ]
        else:
            sub_bars = []

        for sx, sw, act in sub_bars:
            val = float(act["impact"])
            color = COLOR_GOOD if val > ACTIVITY_IMPACT_GOAL else COLOR_NEUTRAL
            h = max(2, (val / max_val) * chart_h)
            y = pad_t + chart_h - h
            title = (
                f"{act['name']} · {act['date']} · impact {val} "
                f"(aerobic {act['aerobic_te']} + anaerobic {act['anaerobic_te']})"
            ).replace('"', "'")
            parts.append(
                f'<rect x="{sx:.1f}" y="{y:.1f}" width="{sw:.1f}" height="{h:.1f}" '
                f'fill="{color}" rx="2"><title>{title}</title></rect>'
            )
            if count >= 2:
                parts.append(
                    f'<text x="{sx + sw / 2:.1f}" y="{y - 4:.1f}" fill="#d8d9da" '
                    f'font-size="8" text-anchor="middle">{val:.1f}</text>'
                )

        if n <= 12 or i % max(1, n // 10) == 0 or i == n - 1:
            short = day["label"][4:] if len(day["label"]) > 4 else day["label"]
            parts.append(
                f'<text x="{x_day + bar_w / 2:.1f}" y="{height - 8}" fill="#8e8e8e" '
                f'font-size="9" text-anchor="end" transform="rotate(-40 '
                f'{x_day + bar_w / 2:.1f},{height - 8})">{short}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def extract_metrics(
    raw_days: dict[str, Any], training_by_day: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    training_by_day = training_by_day or {}
    rows: list[dict[str, Any]] = []
    for day in sorted(raw_days):
        payload = raw_days[day]
        training = training_by_day.get(day, {})
        summary = payload.get("summary") or {}
        sleep_dto = (payload.get("sleep") or {}).get("dailySleepDTO") or {}
        sleep_scores = sleep_dto.get("sleepScores") or {}
        overall = sleep_scores.get("overall") or {}
        hrv_summary = (payload.get("hrv") or {}).get("hrvSummary") or {}

        rows.append(
            {
                "date": day,
                "label": date.fromisoformat(day).strftime("%a %b %d"),
                "steps": summary.get("totalSteps"),
                "resting_hr": summary.get("restingHeartRate"),
                "active_calories": summary.get("activeKilocalories"),
                "sleep_score": overall.get("value"),
                "hrv_status": hrv_summary.get("status"),
                "training_status": training.get("training_status"),
                "endurance_score": training.get("endurance_score"),
                "training_readiness": training.get("training_readiness_score"),
                "body_battery_wake": summary.get("bodyBatteryAtWakeTime"),
                "avg_stress": summary.get("averageStressLevel"),
            }
        )
    return rows


def avg_rhr(rows: list[dict[str, Any]]) -> float | None:
    values = [r["resting_hr"] for r in rows if r["resting_hr"] is not None]
    return sum(values) / len(values) if values else None


def classify_row(row: dict[str, Any], period_avg_rhr: float | None) -> dict[str, str]:
    """Return highlight state per metric: good, warn, neutral."""
    highlights: dict[str, str] = {}

    steps = row.get("steps")
    if steps is not None:
        highlights["steps"] = "good" if steps >= STEP_GOAL else "neutral"

    rhr = row.get("resting_hr")
    if rhr is not None and period_avg_rhr is not None:
        highlights["resting_hr"] = "good" if rhr < period_avg_rhr else "neutral"

    active = row.get("active_calories")
    if active is not None:
        highlights["active_calories"] = "good" if active > ACTIVE_CAL_GOAL else "neutral"

    sleep = row.get("sleep_score")
    if sleep is not None:
        highlights["sleep_score"] = "warn" if sleep < SLEEP_SCORE_WARN else "neutral"

    status = (row.get("hrv_status") or "").upper()
    if status == "BALANCED":
        highlights["hrv_status"] = "good"
    elif status == "UNBALANCED":
        highlights["hrv_status"] = "warn"
    elif status == "LOW":
        highlights["hrv_status"] = "bad"

    return highlights


def _hrv_status_color(status: str | None) -> str:
    key = (status or "").upper()
    if key == "BALANCED":
        return COLOR_GOOD
    if key == "UNBALANCED":
        return COLOR_WARN
    if key == "LOW":
        return COLOR_BAD
    return COLOR_NEUTRAL


def output_name(mode: str, start: date, end: date, fmt: str = "email_friendly_only") -> str:
    if mode == "monthly":
        base = f"monthly_{start.strftime('%Y_%m')}.html"
    else:
        iso = start.isocalendar()
        base = f"weekly_{iso.year}_W{iso.week:02d}.html"
    if fmt == "email_dashboard":
        return base.replace(".html", "_email_dashboard.html")
    if fmt == "dashboard":
        return base.replace(".html", "_dashboard.html")
    return base


def _avg(values: list[float | int | None]) -> float | None:
    nums = [v for v in values if v is not None]
    return sum(nums) / len(nums) if nums else None


def _count_highlights(rows: list[dict[str, Any]], key: str, state: str) -> int:
    return sum(1 for r in rows if r["highlights"].get(key) == state)


def _bar_color(highlight: str | None) -> str:
    if highlight == "good":
        return COLOR_GOOD
    if highlight == "warn":
        return COLOR_WARN
    if highlight == "bad":
        return COLOR_BAD
    return COLOR_NEUTRAL


def _row_is_weekend(row: dict[str, Any]) -> bool:
    day = row.get("date")
    if not day:
        return False
    return date.fromisoformat(str(day)[:10]).weekday() >= 5


def _activity_row_is_weekend(row: dict[str, Any]) -> bool:
    stamp = row.get("start_time") or row.get("date") or ""
    if len(str(stamp)) < 10:
        return False
    return date.fromisoformat(str(stamp)[:10]).weekday() >= 5


def _svg_weekend_bands_discrete(
    rows: list[dict[str, Any]],
    *,
    pad_l: float,
    pad_t: float,
    chart_h: float,
    bar_w: float,
    bar_gap: float,
    is_weekend=_row_is_weekend,
) -> list[str]:
    parts: list[str] = []
    for i, row in enumerate(rows):
        if not is_weekend(row):
            continue
        x = pad_l + i * (bar_w + bar_gap)
        parts.append(
            f'<rect x="{x:.1f}" y="{pad_t:.1f}" width="{bar_w:.1f}" height="{chart_h:.1f}" '
            f'fill="{WEEKEND_SHADE}"/>'
        )
    return parts


def _svg_weekend_bands_continuous(
    rows: list[dict[str, Any]],
    n: int,
    *,
    pad_l: float,
    pad_t: float,
    chart_h: float,
    chart_w: float,
    is_weekend=_row_is_weekend,
) -> list[str]:
    if n == 0:
        return []
    parts: list[str] = []
    step = chart_w / (n - 1) if n > 1 else chart_w
    half = step / 2 if n > 1 else chart_w / 2
    for i, row in enumerate(rows):
        if not is_weekend(row):
            continue
        cx = pad_l + (i / (n - 1)) * chart_w if n > 1 else pad_l + chart_w / 2
        x = max(pad_l, cx - half)
        x2 = min(pad_l + chart_w, cx + half)
        parts.append(
            f'<rect x="{x:.1f}" y="{pad_t:.1f}" width="{x2 - x:.1f}" height="{chart_h:.1f}" '
            f'fill="{WEEKEND_SHADE}"/>'
        )
    return parts


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{round(value)}{suffix}"
    return f"{value}{suffix}"


def _pill(value: Any, highlight: str | None) -> str:
    cls = highlight or "neutral"
    display = _fmt(round(value)) if isinstance(value, float) else _fmt(value)
    return f'<span class="pill {cls}">{display}</span>'


def _hrv_pill(status: str | None, highlight: str | None) -> str:
    cls = highlight or "neutral"
    label = status or "—"
    return f'<span class="pill {cls}">{label}</span>'


def _training_status_color(status: str | None) -> str:
    key = (status or "").upper()
    return TRAINING_STATUS_COLORS.get(key, COLOR_NEUTRAL)


def _training_pill(status: str | None) -> str:
    if not status:
        return '<span class="pill neutral">—</span>'
    color = _training_status_color(status)
    label = status.replace("_", " ").title()
    return (
        f'<span class="pill" style="background:{color}22;color:{color}">{label}</span>'
    )


def _svg_bar_chart(
    rows: list[dict[str, Any]],
    value_key: str,
    highlight_key: str,
    *,
    goal_line: float | None = None,
    y_max_fixed: float | None = None,
    goal_line_color: str = COLOR_GOOD,
) -> str:
    n = len(rows)
    if n == 0:
        return "<p>No data</p>"

    width, height, pad_l, pad_r, pad_t, pad_b = 680, 200, 48, 16, 12, 52
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b

    values = [r.get(value_key) for r in rows]
    numeric = [float(v) for v in values if v is not None]

    if y_max_fixed is not None:
        max_val = y_max_fixed
    else:
        max_val = max(numeric) if numeric else 1
        if goal_line is not None:
            max_val = max(max_val, goal_line)
        max_val = max_val * 1.08 or 1

    bar_gap = 2
    bar_w = max(4, (chart_w - bar_gap * (n - 1)) / n)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="200" '
        f'role="img" aria-label="{value_key} chart">',
    ]
    parts.extend(
        _svg_weekend_bands_discrete(
            rows, pad_l=pad_l, pad_t=pad_t, chart_h=chart_h, bar_w=bar_w, bar_gap=bar_gap
        )
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h}" x2="{width - pad_r}" '
        f'y2="{pad_t + chart_h}" stroke="#2c3235"/>'
    )

    for i in range(5):
        y_val = max_val * (4 - i) / 4
        y = pad_t + chart_h * i / 4
        tick = f"{round(y_val)}%" if y_max_fixed == SLEEP_SCORE_MAX else f"{round(y_val):,}"
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4}" fill="#8e8e8e" font-size="10" '
            f'text-anchor="end">{tick}</text>'
        )
        if i < 4:
            parts.append(
                f'<line x1="{pad_l}" y1="{y}" x2="{width - pad_r}" y2="{y}" '
                f'stroke="#2c3235" stroke-dasharray="3,4"/>'
            )

    if goal_line is not None:
        gy = pad_t + chart_h - (goal_line / max_val) * chart_h
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="{goal_line_color}" stroke-dasharray="6,4" opacity="0.85"/>'
        )

    for i, row in enumerate(rows):
        val = row.get(value_key)
        x = pad_l + i * (bar_w + bar_gap)
        color = _bar_color(row["highlights"].get(highlight_key))
        label = row["label"].replace('"', "'")

        if val is None:
            parts.append(
                f'<rect x="{x:.1f}" y="{pad_t + chart_h - 2}" width="{bar_w:.1f}" '
                f'height="2" fill="#2c3235"/>'
            )
        else:
            h = max(2, (float(val) / max_val) * chart_h)
            y = pad_t + chart_h - h
            suffix = "%" if y_max_fixed == SLEEP_SCORE_MAX else ""
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'fill="{color}" rx="2"><title>{label}: {val}{suffix}</title></rect>'
            )

        if n <= 12 or i % max(1, n // 10) == 0 or i == n - 1:
            short = row["label"][4:] if len(row["label"]) > 4 else row["label"]
            parts.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{height - 8}" fill="#8e8e8e" '
                f'font-size="9" text-anchor="end" transform="rotate(-40 '
                f'{x + bar_w / 2:.1f},{height - 8})">{short}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _svg_rhr_line_chart(
    rows: list[dict[str, Any]], period_avg_rhr: float | None
) -> str:
    n = len(rows)
    if n == 0:
        return "<p>No data</p>"

    width, height, pad_l, pad_r, pad_t, pad_b = 680, 200, 48, 16, 12, 52
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b

    values = [r.get("resting_hr") for r in rows]
    numeric = [float(v) for v in values if v is not None]
    if not numeric:
        return "<p>No resting HR data</p>"

    y_min = min(numeric) - 3
    y_max = max(numeric) + 3
    if period_avg_rhr is not None:
        y_min = min(y_min, period_avg_rhr - 3)
        y_max = max(y_max, period_avg_rhr + 3)
    y_range = max(y_max - y_min, 1)

    def y_pos(val: float) -> float:
        return pad_t + chart_h - ((val - y_min) / y_range) * chart_h

    def x_pos(i: int) -> float:
        if n == 1:
            return pad_l + chart_w / 2
        return pad_l + (i / (n - 1)) * chart_w

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="200" '
        f'role="img" aria-label="Resting heart rate line chart">',
    ]
    parts.extend(
        _svg_weekend_bands_continuous(
            rows, n, pad_l=pad_l, pad_t=pad_t, chart_h=chart_h, chart_w=chart_w
        )
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h}" x2="{width - pad_r}" '
        f'y2="{pad_t + chart_h}" stroke="#2c3235"/>'
    )

    for i in range(5):
        y_val = y_min + y_range * (4 - i) / 4
        y = pad_t + chart_h * i / 4
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4}" fill="#8e8e8e" font-size="10" '
            f'text-anchor="end">{round(y_val)}</text>'
        )
        if i < 4:
            parts.append(
                f'<line x1="{pad_l}" y1="{y}" x2="{width - pad_r}" y2="{y}" '
                f'stroke="#2c3235" stroke-dasharray="3,4"/>'
            )

    if period_avg_rhr is not None:
        ay = y_pos(period_avg_rhr)
        parts.append(
            f'<line x1="{pad_l}" y1="{ay:.1f}" x2="{width - pad_r}" y2="{ay:.1f}" '
            f'stroke="{COLOR_GOOD}" stroke-dasharray="6,4" opacity="0.85"/>'
        )
        parts.append(
            f'<text x="{width - pad_r}" y="{ay - 4:.1f}" fill="{COLOR_GOOD}" '
            f'font-size="9" text-anchor="end">avg {period_avg_rhr:.0f} bpm</text>'
        )

    line_points: list[str] = []
    for i, row in enumerate(rows):
        val = row.get("resting_hr")
        if val is not None:
            line_points.append(f"{x_pos(i):.1f},{y_pos(float(val)):.1f}")

    if len(line_points) >= 2:
        parts.append(
            f'<polyline fill="none" stroke="{COLOR_NEUTRAL}" stroke-width="2" '
            f'points="{" ".join(line_points)}"/>'
        )

    for i, row in enumerate(rows):
        val = row.get("resting_hr")
        if val is None:
            continue
        cx, cy = x_pos(i), y_pos(float(val))
        color = _bar_color(row["highlights"].get("resting_hr"))
        label = row["label"].replace('"', "'")
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{color}" '
            f'stroke="#111217" stroke-width="1.5">'
            f'<title>{label}: {val} bpm</title></circle>'
        )

        if n <= 12 or i % max(1, n // 10) == 0 or i == n - 1:
            short = row["label"][4:] if len(row["label"]) > 4 else row["label"]
            parts.append(
                f'<text x="{cx:.1f}" y="{height - 8}" fill="#8e8e8e" font-size="9" '
                f'text-anchor="end" transform="rotate(-40 {cx:.1f},{height - 8})">{short}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _readiness_color(value: float | int | None) -> str:
    if value is None:
        return COLOR_NEUTRAL
    if value >= READINESS_GOOD:
        return COLOR_GOOD
    if value >= READINESS_WARN:
        return COLOR_YELLOW
    return COLOR_BAD


def _body_battery_color(value: float | int | None) -> str:
    if value is None:
        return COLOR_NEUTRAL
    if value >= BODY_BATTERY_GOOD:
        return COLOR_GOOD
    if value >= BODY_BATTERY_WARN:
        return COLOR_WARN
    return COLOR_BAD


def _stress_color(value: float | int | None) -> str:
    if value is None:
        return COLOR_NEUTRAL
    if value <= STRESS_GOOD:
        return COLOR_GOOD
    if value <= STRESS_WARN:
        return COLOR_YELLOW
    if value <= STRESS_BAD:
        return COLOR_WARN
    return COLOR_BAD


def _svg_hrv_chart(rows: list[dict[str, Any]]) -> str:
    return _svg_status_strip(
        rows, "hrv_status", _hrv_status_color, aria_label="HRV status chart"
    )


def _svg_status_strip(
    rows: list[dict[str, Any]],
    value_key: str,
    color_fn,
    *,
    height: int = 120,
    aria_label: str,
) -> str:
    n = len(rows)
    width, pad_l, pad_r, pad_t, pad_b = 680, 48, 16, 12, 52
    chart_w = width - pad_l - pad_r
    bar_gap = 2
    bar_w = max(4, (chart_w - bar_gap * (n - 1)) / n)
    bar_h = height - pad_t - pad_b

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="{aria_label}">',
    ]
    parts.extend(
        _svg_weekend_bands_discrete(
            rows, pad_l=pad_l, pad_t=pad_t, chart_h=bar_h, bar_w=bar_w, bar_gap=bar_gap
        )
    )
    for i, row in enumerate(rows):
        x = pad_l + i * (bar_w + bar_gap)
        raw = row.get(value_key)
        color = color_fn(raw)
        label = str(raw or "—").replace('"', "'")
        parts.append(
            f'<rect x="{x:.1f}" y="{pad_t}" width="{bar_w:.1f}" height="{bar_h}" '
            f'fill="{color}" rx="2"><title>{row["label"]}: {label}</title></rect>'
        )
        if n <= 12 or i % max(1, n // 10) == 0 or i == n - 1:
            short = row["label"][4:] if len(row["label"]) > 4 else row["label"]
            parts.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{height - 8}" fill="#8e8e8e" '
                f'font-size="9" text-anchor="end" transform="rotate(-40 '
                f'{x + bar_w / 2:.1f},{height - 8})">{short}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_metric_line_chart(
    rows: list[dict[str, Any]],
    value_key: str,
    *,
    line_color: str,
    aria_label: str,
) -> str:
    n = len(rows)
    if n == 0:
        return "<p>No data</p>"

    width, height, pad_l, pad_r, pad_t, pad_b = 680, 200, 48, 16, 12, 52
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b

    numeric = [float(r[value_key]) for r in rows if r.get(value_key) is not None]
    if not numeric:
        return "<p>No data for this period</p>"

    y_min = min(numeric) * 0.98
    y_max = max(numeric) * 1.02
    y_range = max(y_max - y_min, 1)

    def y_pos(val: float) -> float:
        return pad_t + chart_h - ((val - y_min) / y_range) * chart_h

    def x_pos(i: int) -> float:
        if n == 1:
            return pad_l + chart_w / 2
        return pad_l + (i / (n - 1)) * chart_w

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="200" '
        f'role="img" aria-label="{aria_label}">',
    ]
    parts.extend(
        _svg_weekend_bands_continuous(
            rows, n, pad_l=pad_l, pad_t=pad_t, chart_h=chart_h, chart_w=chart_w
        )
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h}" x2="{width - pad_r}" '
        f'y2="{pad_t + chart_h}" stroke="#2c3235"/>'
    )

    for i in range(5):
        y_val = y_min + y_range * (4 - i) / 4
        y = pad_t + chart_h * i / 4
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4}" fill="#8e8e8e" font-size="10" '
            f'text-anchor="end">{round(y_val):,}</text>'
        )
        if i < 4:
            parts.append(
                f'<line x1="{pad_l}" y1="{y}" x2="{width - pad_r}" y2="{y}" '
                f'stroke="#2c3235" stroke-dasharray="3,4"/>'
            )

    line_points: list[str] = []
    for i, row in enumerate(rows):
        val = row.get(value_key)
        if val is not None:
            line_points.append(f"{x_pos(i):.1f},{y_pos(float(val)):.1f}")

    if len(line_points) >= 2:
        parts.append(
            f'<polyline fill="none" stroke="{line_color}" stroke-width="2" '
            f'points="{" ".join(line_points)}"/>'
        )

    for i, row in enumerate(rows):
        val = row.get(value_key)
        if val is None:
            continue
        cx, cy = x_pos(i), y_pos(float(val))
        label = row["label"].replace('"', "'")
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{line_color}" '
            f'stroke="#111217" stroke-width="1.5">'
            f'<title>{label}: {val}</title></circle>'
        )
        if n <= 12 or i % max(1, n // 10) == 0 or i == n - 1:
            short = row["label"][4:] if len(row["label"]) > 4 else row["label"]
            parts.append(
                f'<text x="{cx:.1f}" y="{height - 8}" fill="#8e8e8e" font-size="9" '
                f'text-anchor="end" transform="rotate(-40 {cx:.1f},{height - 8})">{short}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _svg_recovery_stress_panel(rows: list[dict[str, Any]]) -> str:
    """Full-width panel: Training Readiness, Body Battery, and Stress (0–100, colored by significance)."""
    n = len(rows)
    if n == 0:
        return "<p>No data</p>"

    width, band_h, pad_l, pad_r, label_w = 680, 88, 48, 16, 132
    chart_w = width - pad_l - pad_r
    total_h = band_h * 3 + 36
    y_max = 100.0

    metrics: list[tuple[str, str, Any]] = [
        ("training_readiness", "Training Readiness", _readiness_color),
        ("body_battery_wake", "Body Battery (wake)", _body_battery_color),
        ("avg_stress", "Avg Stress", _stress_color),
    ]

    def x_pos(i: int) -> float:
        if n == 1:
            return pad_l + chart_w / 2
        return pad_l + (i / (n - 1)) * chart_w

    def y_pos(val: float, band_top: float) -> float:
        inner_h = band_h - 28
        return band_top + 12 + inner_h - (val / y_max) * inner_h

    parts = [
        f'<svg viewBox="0 0 {width} {total_h}" width="100%" height="{total_h}" '
        f'role="img" aria-label="Training readiness, body battery, and stress trends">',
    ]
    chart_top = 12
    chart_bottom = band_h * 3 - 16
    parts.extend(
        _svg_weekend_bands_continuous(
            rows,
            n,
            pad_l=pad_l,
            pad_t=chart_top,
            chart_h=chart_bottom - chart_top,
            chart_w=chart_w,
        )
    )

    for band_idx, (value_key, title, color_fn) in enumerate(metrics):
        band_top = band_idx * band_h
        inner_bottom = band_top + band_h - 16

        parts.append(
            f'<text x="8" y="{band_top + 22}" fill="#d8d9da" font-size="10" '
            f'font-weight="600">{title}</text>'
        )
        parts.append(
            f'<line x1="{pad_l}" y1="{inner_bottom}" x2="{width - pad_r}" '
            f'y2="{inner_bottom}" stroke="#2c3235"/>'
        )

        for tick in (0, 50, 100):
            y = y_pos(float(tick), band_top)
            parts.append(
                f'<text x="{pad_l - 8}" y="{y + 4}" fill="#8e8e8e" font-size="9" '
                f'text-anchor="end">{tick}</text>'
            )
            if tick < 100:
                parts.append(
                    f'<line x1="{pad_l}" y1="{y}" x2="{width - pad_r}" y2="{y}" '
                    f'stroke="#2c3235" stroke-dasharray="3,4" opacity="0.6"/>'
                )

        line_points: list[str] = []
        for i, row in enumerate(rows):
            val = row.get(value_key)
            if val is not None:
                line_points.append(f"{x_pos(i):.1f},{y_pos(float(val), band_top):.1f}")

        if len(line_points) >= 2:
            parts.append(
                f'<polyline fill="none" stroke="#555" stroke-width="1.5" '
                f'points="{" ".join(line_points)}" opacity="0.7"/>'
            )

        for i, row in enumerate(rows):
            val = row.get(value_key)
            if val is None:
                continue
            cx = x_pos(i)
            cy = y_pos(float(val), band_top)
            dot_color = color_fn(val)
            label = row["label"].replace('"', "'")
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{dot_color}" '
                f'stroke="#111217" stroke-width="1.5">'
                f'<title>{label}: {title} {val}</title></circle>'
            )
            if band_idx == 2 and (n <= 12 or i % max(1, n // 10) == 0 or i == n - 1):
                short = row["label"][4:] if len(row["label"]) > 4 else row["label"]
                parts.append(
                    f'<text x="{cx:.1f}" y="{total_h - 6}" fill="#8e8e8e" font-size="9" '
                    f'text-anchor="end" transform="rotate(-40 {cx:.1f},{total_h - 6})">{short}</text>'
                )

        if band_idx < 2:
            parts.append(
                f'<line x1="{pad_l}" y1="{band_top + band_h}" x2="{width - pad_r}" '
                f'y2="{band_top + band_h}" stroke="#2c3235" opacity="0.5"/>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def build_dashboard_html(
    mode: str,
    start: date,
    end: date,
    rows: list[dict[str, Any]],
    period_avg_rhr: float | None,
    activity_summary: dict[str, Any],
) -> str:
    enriched = [{**row, "highlights": classify_row(row, period_avg_rhr)} for row in rows]
    period_label = f"{start.isoformat()} → {end.isoformat()}"
    generated_at = date.today().isoformat()
    avg_rhr_display = _fmt(round(period_avg_rhr, 1) if period_avg_rhr else None, " bpm")

    good_steps = _count_highlights(enriched, "steps", "good")
    good_rhr = _count_highlights(enriched, "resting_hr", "good")
    hrv_balanced = _count_highlights(enriched, "hrv_status", "good")
    hrv_unbalanced = _count_highlights(enriched, "hrv_status", "warn")
    hrv_low = _count_highlights(enriched, "hrv_status", "bad")
    good_cal = _count_highlights(enriched, "active_calories", "good")
    warn_sleep = _count_highlights(enriched, "sleep_score", "warn")
    half = (len(enriched) + 1) // 2

    stat_cards = [
        (
            "Steps",
            _fmt(round(_avg([r["steps"] for r in enriched]) or 0)),
            f"{good_steps} days ≥10k",
            "good" if good_steps >= half else "",
        ),
        (
            "Resting HR",
            _fmt(round(_avg([r["resting_hr"] for r in enriched]) or 0), " bpm"),
            f"{good_rhr} days below avg",
            "",
        ),
        (
            "HRV balanced days",
            str(hrv_balanced),
            f"{hrv_low} low · {hrv_unbalanced} unbalanced",
            "good" if hrv_low == 0 and hrv_unbalanced == 0 else ("bad" if hrv_low else "warn"),
        ),
        (
            "Active calories",
            _fmt(round(_avg([r["active_calories"] for r in enriched]) or 0), " kcal"),
            f"{good_cal} days >500",
            "good" if good_cal >= half else "",
        ),
        (
            "Sleep score",
            _fmt(round(_avg([r["sleep_score"] for r in enriched if r["sleep_score"] is not None]) or 0)),
            f"{warn_sleep} days <90 · scale 0–100",
            "warn" if warn_sleep else "good",
        ),
        (
            "Activities",
            str(activity_summary["total"]),
            "workouts in period",
            "good" if activity_summary["total"] else "",
        ),
    ]

    stats_html = "\n".join(
        f"""      <div class="stat">
        <div class="stat-label">{label}</div>
        <div class="stat-value {tone}">{value}</div>
        <div class="stat-meta">{meta}</div>
      </div>"""
        for label, value, meta, tone in stat_cards
    )

    charts_html = f"""    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Steps</div>
        <div class="panel-rule">Highlight if ≥10,000</div>
      </div>
      <div class="panel-body">{_svg_bar_chart(enriched, "steps", "steps", goal_line=STEP_GOAL)}</div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Resting heart rate</div>
        <div class="panel-rule">Line chart · green dots below period average</div>
      </div>
      <div class="panel-body">{_svg_rhr_line_chart(enriched, period_avg_rhr)}</div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Active calories</div>
        <div class="panel-rule">Highlight if &gt;500 kcal</div>
      </div>
      <div class="panel-body">{_svg_bar_chart(enriched, "active_calories", "active_calories", goal_line=ACTIVE_CAL_GOAL)}</div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Sleep score</div>
        <div class="panel-rule">Scale 0–100% · highlight if &lt;90</div>
      </div>
      <div class="panel-body">{_svg_bar_chart(enriched, "sleep_score", "sleep_score", goal_line=SLEEP_SCORE_WARN, y_max_fixed=SLEEP_SCORE_MAX, goal_line_color=COLOR_WARN)}</div>
    </div>"""

    has_endurance = any(r.get("endurance_score") is not None for r in enriched)
    endurance_panel = ""
    if has_endurance:
        avg_endurance = _avg([r["endurance_score"] for r in enriched])
        endurance_panel = f"""    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Endurance score</div>
        <div class="panel-rule">Daily score · avg {_fmt(round(avg_endurance or 0))}</div>
      </div>
      <div class="panel-body">{_svg_metric_line_chart(enriched, "endurance_score", line_color=COLOR_ACCENT, aria_label="Endurance score line chart")}</div>
    </div>"""

    hrv_panel = f"""    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">HRV status</div>
        <div class="panel-rule">Balanced = green · Unbalanced = orange · Low = red</div>
      </div>
      <div class="panel-body">{_svg_hrv_chart(enriched)}</div>
    </div>"""

    endurance_hrv_html = f"""    <div class="grid">
{endurance_panel}{hrv_panel}
    </div>"""

    has_recovery = any(
        r.get("training_readiness") is not None
        or r.get("body_battery_wake") is not None
        or r.get("avg_stress") is not None
        for r in enriched
    )
    recovery_stress_html = ""
    if has_recovery:
        avg_readiness = _avg([r["training_readiness"] for r in enriched])
        avg_bb = _avg([r["body_battery_wake"] for r in enriched])
        avg_stress = _avg([r["avg_stress"] for r in enriched])
        recovery_stress_html = f"""    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head">
        <div class="panel-title">Recovery &amp; stress trends</div>
        <div class="panel-rule">Readiness avg {_fmt(round(avg_readiness or 0))} · BB wake avg {_fmt(round(avg_bb or 0))} · Stress avg {_fmt(round(avg_stress or 0))}</div>
      </div>
      <div class="panel-sublegend">
        <span><span class="dot" style="background:{COLOR_GOOD}"></span><span class="dot" style="background:{COLOR_YELLOW}"></span><span class="dot" style="background:{COLOR_WARN}"></span><span class="dot" style="background:{COLOR_BAD}"></span>
        Readiness: green ≥70 · yellow 50–69 · red &lt;50</span>
        <span><span class="dot" style="background:{COLOR_GOOD}"></span><span class="dot" style="background:{COLOR_WARN}"></span><span class="dot" style="background:{COLOR_BAD}"></span>
        Body battery (wake): green ≥70 · orange 40–69 · red &lt;40</span>
        <span><span class="dot" style="background:{COLOR_GOOD}"></span><span class="dot" style="background:{COLOR_YELLOW}"></span><span class="dot" style="background:{COLOR_WARN}"></span><span class="dot" style="background:{COLOR_BAD}"></span>
        Stress (lower is better): green ≤25 · yellow 26–50 · orange 51–75 · red &gt;75</span>
      </div>
      <div class="panel-body">{_svg_recovery_stress_panel(enriched)}</div>
    </div>"""

    training_and_impact_html = f"""    <div class="grid">
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Training status</div>
        <div class="panel-rule">Yellow maintaining · Green productive · Pink strained · Blue recovery · Red overreaching</div>
      </div>
      <div class="panel-body panel-body-tall">{_svg_status_strip(enriched, "training_status", _training_status_color, height=220, aria_label="Training status chart")}</div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Activity fitness impact</div>
        <div class="panel-rule">Impact = aerobic TE + anaerobic TE · green if &gt;8.0</div>
      </div>
      <div class="panel-body panel-body-tall">{_svg_activity_impact_chart(activity_summary.get("daily_impacts", []))}</div>
    </div>
    </div>"""

    top = activity_summary.get("top_impact")
    top_rule = "No activities recorded"
    if top:
        top_rule = (
            f"#1 {top['name']} · impact {top['impact']} "
            f"(aerobic {top['aerobic_te']} + anaerobic {top['anaerobic_te']})"
        )

    activities_html = f"""    <div class="grid">
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Activity breakdown</div>
        <div class="panel-rule">{activity_summary['total']} total activities</div>
      </div>
      <div class="panel-table-wrap">
        <table>
          <thead>
            <tr><th>Type</th><th>Count</th><th>Share</th><th>Duration</th><th></th></tr>
          </thead>
          <tbody>
{_render_activity_breakdown_table(activity_summary)}
          </tbody>
        </table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Fitness impact ranking</div>
        <div class="panel-rule">{top_rule}</div>
      </div>
      <div class="panel-table-wrap">
        <table>
          <thead>
            <tr><th>Activity</th><th>Date</th><th>Aerobic TE</th><th>Anaerobic TE</th><th>Impact</th></tr>
          </thead>
          <tbody>
{_render_fitness_impact_table(activity_summary)}
          </tbody>
        </table>
      </div>
    </div>
    </div>"""

    table_rows = "\n".join(
        f"""          <tr>
            <td>{r["label"]}</td>
            <td>{_pill(r["steps"], r["highlights"].get("steps"))}</td>
            <td>{_pill(r["resting_hr"], r["highlights"].get("resting_hr"))}</td>
            <td>{_hrv_pill(r["hrv_status"], r["highlights"].get("hrv_status"))}</td>
            <td>{_pill(round(r["active_calories"]) if r["active_calories"] is not None else None, r["highlights"].get("active_calories"))}</td>
            <td>{_pill(r["sleep_score"], r["highlights"].get("sleep_score"))}</td>
            <td>{_training_pill(r["training_status"])}</td>
            <td>{_pill(r["endurance_score"], None)}</td>
          </tr>"""
        for r in enriched
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Garmin Health — {mode.title()} Dashboard</title>
  <style>
    :root {{
      --bg: #0b0c0e;
      --panel: #111217;
      --panel-2: #181b1f;
      --border: #2c3235;
      --text: #d8d9da;
      --muted: #8e8e8e;
      --accent: #5794f2;
      --good: #73bf69;
      --warn: #ff9830;
      --bad: #f2495c;
      --good-bg: rgba(115, 191, 105, 0.12);
      --warn-bg: rgba(255, 152, 48, 0.14);
      --bad-bg: rgba(242, 73, 92, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    .wrap {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    header {{
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 16px; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border);
    }}
    h1 {{ margin: 0; font-size: 1.35rem; font-weight: 600; }}
    .sub {{ color: var(--muted); font-size: 0.85rem; margin-top: 6px; }}
    .badge {{
      font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--accent); border: 1px solid rgba(87,148,242,0.35);
      padding: 4px 10px; border-radius: 999px;
    }}
    .stats {{
      display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px;
    }}
    .stat {{
      background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 14px;
    }}
    .stat-label {{ color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }}
    .stat-value {{ font-size: 1.65rem; font-weight: 600; margin: 8px 0 4px; }}
    .stat-meta {{ color: var(--muted); font-size: 0.78rem; }}
    .stat-value.good {{ color: var(--good); }}
    .stat-value.warn {{ color: var(--warn); }}
    .stat-value.bad {{ color: var(--bad); }}
    .grid {{
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px;
    }}
    .panel {{
      background: var(--panel); border: 1px solid var(--border); border-radius: 4px; overflow: hidden;
    }}
    .panel-head {{
      display: flex; justify-content: space-between; align-items: center; gap: 12px;
      padding: 10px 14px; border-bottom: 1px solid var(--border); background: var(--panel-2);
    }}
    .panel-title {{ font-size: 0.82rem; font-weight: 600; }}
    .panel-rule {{ font-size: 0.72rem; color: var(--muted); text-align: right; }}
    .panel-body {{ padding: 8px 12px 4px; overflow-x: auto; }}
    .panel-body-tall {{ min-height: 228px; }}
    .panel-table-wrap {{ overflow-x: auto; }}
    .highlight-row td {{ background: var(--good-bg); }}
    .bar-cell {{ width: 110px; }}
    .share-bar {{ display: block; height: 8px; background: var(--accent); border-radius: 2px; max-width: 100%; }}
    .muted {{ color: var(--muted); }}
    .legend {{ display: flex; gap: 14px; flex-wrap: wrap; font-size: 0.72rem; color: var(--muted); margin-bottom: 14px; }}
    .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }}
    .weekend-swatch {{
      display: inline-block; width: 14px; height: 8px; border-radius: 2px; margin-right: 5px;
      background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.12);
    }}
    .panel-sublegend {{
      display: flex; gap: 12px; flex-wrap: wrap; padding: 8px 14px; font-size: 0.68rem;
      color: var(--muted); border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02);
    }}
    .panel-sublegend span {{ display: inline-flex; align-items: center; gap: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }}
    th {{ color: var(--muted); font-weight: 500; font-size: 0.72rem; text-transform: uppercase; }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .pill {{
      display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.72rem; font-weight: 600;
    }}
    .pill.good {{ background: var(--good-bg); color: var(--good); }}
    .pill.warn {{ background: var(--warn-bg); color: var(--warn); }}
    .pill.bad {{ background: var(--bad-bg); color: var(--bad); }}
    .pill.neutral {{ color: var(--muted); }}
    @media (max-width: 1100px) {{
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>Garmin Health Dashboard</h1>
        <div class="sub">{period_label} · generated {generated_at} · avg RHR {avg_rhr_display}</div>
      </div>
      <div class="badge">{mode}</div>
    </header>

    <div class="legend">
      <span><span class="dot" style="background:var(--good)"></span>Green = good (steps ≥10k, RHR below avg, active cal &gt;500, HRV balanced, activity impact &gt;8)</span>
      <span><span class="dot" style="background:var(--warn)"></span>Orange = HRV unbalanced · sleep &lt;90</span>
      <span><span class="dot" style="background:var(--bad)"></span>Red = HRV low · overreaching</span>
      <span><span class="dot" style="background:#fade2a"></span>Training: yellow maintaining · green productive · pink strained · blue recovery</span>
      <span><span class="weekend-swatch"></span>Light shading = Saturday &amp; Sunday</span>
    </div>

    <div class="stats">
{stats_html}
    </div>

    <div class="grid">
{charts_html}
    </div>

{endurance_hrv_html}

{recovery_stress_html}

{training_and_impact_html}

{activities_html}

    <div class="panel">
      <div class="panel-head">
        <div class="panel-title">Daily breakdown</div>
        <div class="panel-rule">Per-day values and highlight status</div>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr>
              <th>Date</th><th>Steps</th><th>Resting HR</th><th>HRV</th>
              <th>Active Cal</th><th>Sleep Score</th><th>Training</th><th>Endurance</th>
            </tr>
          </thead>
          <tbody>
{table_rows}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Garmin health dashboard")
    parser.add_argument(
        "--mode",
        choices=["auto", "weekly", "monthly"],
        default="auto",
        help="weekly=last Mon–Sun, monthly=previous calendar month",
    )
    parser.add_argument(
        "--date",
        help="Reference date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open dashboard in browser after generation",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Force fetch from Garmin even if cached daily_stats.json exists",
    )
    parser.add_argument(
        "--format",
        choices=["email_friendly_only", "email_dashboard", "dashboard", "email"],
        default="email_friendly_only",
        help="email_friendly_only=table HTML + bar charts, no Cairo (default); "
        "email_dashboard=Gmail PNG charts (needs cairosvg/Cairo); "
        "dashboard=full browser SVG dashboard; email=alias for email_dashboard",
    )
    args = parser.parse_args()
    fmt = "email_dashboard" if args.format == "email" else args.format

    ref = date.fromisoformat(args.date) if args.date else date.today()
    mode, start, end = resolve_period(args.mode, ref)
    print(f"Mode: {mode}")
    print(f"Period: {start.isoformat()} → {end.isoformat()}")

    if args.fetch:
        print("Fetching from Garmin Connect...")
        client = login()
        raw_days = fetch_days(client, start, end)
    else:
        raw_days = load_cached_days(start, end)
        if raw_days:
            print("Using cached daily_stats.json")
            client = login()
        else:
            print("No cache for this period — fetching from Garmin Connect...")
            client = login()
            raw_days = fetch_days(client, start, end)

    print("Loading training status & endurance score...")
    training_by_day = ensure_training_metrics(client, start, end, force=args.fetch)

    print("Loading activities...")
    activities = ensure_activities(client, start, end, force=args.fetch)
    rows = extract_metrics(raw_days, training_by_day)
    period_avg_rhr = avg_rhr(rows)
    activity_summary = analyze_activities(activities, rows)
    if fmt == "email_dashboard":
        from garmin_email_html import build_email_html

        html = build_email_html(
            mode, start, end, rows, period_avg_rhr, activity_summary
        )
    elif fmt == "dashboard":
        html = build_dashboard_html(
            mode, start, end, rows, period_avg_rhr, activity_summary
        )
    else:
        from garmin_email_friendly_html import build_email_friendly_html

        html = build_email_friendly_html(
            mode, start, end, rows, period_avg_rhr, activity_summary
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / output_name(mode, start, end, fmt)
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard saved ({fmt}): {out_path.resolve()}")

    if args.open:
        webbrowser.open(out_path.resolve().as_uri())


if __name__ == "__main__":
    main()
