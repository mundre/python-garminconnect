"""Email-friendly HTML dashboard — table layout and HTML bars, no Cairo/SVG."""

from __future__ import annotations

from datetime import date
from typing import Any

from garmin_dashboard import (
    ACTIVE_CAL_GOAL,
    ACTIVITY_IMPACT_GOAL,
    BODY_BATTERY_GOOD,
    BODY_BATTERY_WARN,
    COLOR_ACCENT,
    COLOR_BAD,
    COLOR_GOOD,
    COLOR_NEUTRAL,
    COLOR_WARN,
    COLOR_YELLOW,
    READINESS_GOOD,
    READINESS_WARN,
    SLEEP_SCORE_MAX,
    SLEEP_SCORE_WARN,
    STEP_GOAL,
    STRESS_BAD,
    STRESS_GOOD,
    STRESS_WARN,
    _avg,
    _count_highlights,
    _fmt,
    _hrv_status_color,
    _row_is_weekend,
    _training_status_color,
    classify_row,
)
from garmin_email_html import (
    BG,
    BORDER,
    EMAIL_W,
    FONT,
    MUTED,
    PANEL,
    PANEL2,
    TEXT,
    _PILL,
    _email_activity_breakdown,
    _email_data_table,
    _email_fitness_impact,
    _email_hrv_pill,
    _email_legend,
    _email_panel,
    _email_pill,
    _email_stats_table,
    _email_training_pill,
    _esc,
)

_WEEKEND_BG = "#151518"
_TRACK = "#2c3235"


def _hl_color(highlight: str | None) -> str:
    return _PILL.get(highlight or "neutral", _PILL["neutral"])[0]


def _html_h_bar(value: float, max_val: float, color: str, *, height: int = 14) -> str:
    if max_val <= 0:
        pct = 0.0
    else:
        pct = min(100.0, max(0.0, (value / max_val) * 100))
    empty = max(0.0, 100.0 - pct)
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"<tr>"
        f'<td width="{pct:.1f}%" bgcolor="{color}" '
        f'style="height:{height}px;font-size:0;line-height:0;">&nbsp;</td>'
        f'<td width="{empty:.1f}%" bgcolor="{_TRACK}" '
        f'style="height:{height}px;font-size:0;line-height:0;">&nbsp;</td>'
        f"</tr></table>"
    )


def _short_label(label: str) -> str:
    return label[4:] if len(label) > 5 else label


def _html_bar_chart(
    rows: list[dict[str, Any]],
    value_key: str,
    highlight_key: str,
    *,
    goal_line: float | None = None,
    y_max_fixed: float | None = None,
    default_color: str = COLOR_NEUTRAL,
) -> str:
    if not rows:
        return f'<p style="color:{MUTED};font-family:{FONT};font-size:12px;">No data</p>'

    numeric = [float(r[value_key]) for r in rows if r.get(value_key) is not None]
    if y_max_fixed is not None:
        max_val = float(y_max_fixed)
    elif numeric:
        max_val = max(numeric)
        if goal_line is not None:
            max_val = max(max_val, goal_line)
        max_val = max_val * 1.08 or 1.0
    else:
        max_val = goal_line or 1.0

    parts: list[str] = []
    if goal_line is not None:
        parts.append(
            f'<p style="font-size:11px;color:{MUTED};margin:0 0 8px;font-family:{FONT};">'
            f"Goal: {_esc(_fmt(goal_line))}</p>"
        )

    trs: list[str] = []
    for row in rows:
        value = row.get(value_key)
        hl = row["highlights"].get(highlight_key)
        color = _hl_color(hl) if hl else default_color
        bg = f' bgcolor="{_WEEKEND_BG}"' if _row_is_weekend(row) else ""
        if value is None:
            bar = f'<span style="color:{MUTED};font-size:11px;">—</span>'
            display = "—"
        else:
            bar = _html_h_bar(float(value), max_val, color)
            display = _fmt(value)
        trs.append(
            f"<tr{bg}>"
            f'<td style="padding:3px 8px;font-size:11px;color:{MUTED};'
            f'font-family:{FONT};white-space:nowrap;width:72px;">'
            f"{_esc(_short_label(row['label']))}</td>"
            f'<td style="padding:3px 8px;width:58%;">{bar}</td>'
            f'<td style="padding:3px 8px;font-size:11px;color:{TEXT};'
            f'font-family:{FONT};text-align:right;width:56px;">{_esc(display)}</td>'
            f"</tr>"
        )

    parts.append(
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"{''.join(trs)}</table>"
    )
    return "".join(parts)


def _html_rhr_chart(rows: list[dict[str, Any]], period_avg_rhr: float | None) -> str:
    if not rows:
        return f'<p style="color:{MUTED};font-family:{FONT};font-size:12px;">No data</p>'

    numeric = [float(r["resting_hr"]) for r in rows if r.get("resting_hr") is not None]
    max_val = max(numeric) * 1.08 if numeric else 1.0
    min_val = min(numeric) if numeric else 0.0
    span = max(max_val - min_val, 1.0)

    if period_avg_rhr is not None:
        parts = [
            f'<p style="font-size:11px;color:{MUTED};margin:0 0 8px;font-family:{FONT};">'
            f"Period avg: {_esc(_fmt(round(period_avg_rhr, 1), ' bpm'))}</p>"
        ]
    else:
        parts = []

    trs: list[str] = []
    for row in rows:
        value = row.get("resting_hr")
        bg = f' bgcolor="{_WEEKEND_BG}"' if _row_is_weekend(row) else ""
        if value is None:
            bar = f'<span style="color:{MUTED};font-size:11px;">—</span>'
            display = "—"
        else:
            color = _hl_color(row["highlights"].get("resting_hr"))
            norm = (float(value) - min_val) / span
            bar = _html_h_bar(norm * span + min_val, max_val, color, height=10)
            display = _fmt(value)
        trs.append(
            f"<tr{bg}>"
            f'<td style="padding:3px 8px;font-size:11px;color:{MUTED};font-family:{FONT};">'
            f"{_esc(_short_label(row['label']))}</td>"
            f'<td style="padding:3px 8px;width:58%;">{bar}</td>'
            f'<td style="padding:3px 8px;font-size:11px;color:{TEXT};font-family:{FONT};'
            f'text-align:right;">{_esc(display)}</td>'
            f"</tr>"
        )

    parts.append(
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"{''.join(trs)}</table>"
    )
    return "".join(parts)


def _html_dot_row(
    rows: list[dict[str, Any]],
    *,
    color_fn,
    title_fn,
) -> str:
    cells: list[str] = []
    for row in rows:
        color = color_fn(row)
        title = _esc(title_fn(row))
        cells.append(
            f'<td align="center" valign="bottom" style="padding:2px 1px;">'
            f'<span title="{title}" style="display:inline-block;width:10px;height:10px;'
            f"background:{color};border-radius:50%;font-size:0;line-height:0;"
            f'">&nbsp;</span></td>'
        )
    labels = "".join(
        f'<td align="center" style="padding:2px 0;font-size:9px;color:{MUTED};'
        f'font-family:{FONT};">{_esc(_short_label(r["label"]))}</td>'
        for r in rows
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"<tr>{''.join(cells)}</tr><tr>{labels}</tr></table>"
    )


def _html_hrv_chart(rows: list[dict[str, Any]]) -> str:
    return _html_dot_row(
        rows,
        color_fn=lambda r: _hrv_status_color(r.get("hrv_status")),
        title_fn=lambda r: f"{r['label']}: {r.get('hrv_status') or '—'}",
    )


def _html_training_strip(rows: list[dict[str, Any]]) -> str:
    return _html_dot_row(
        rows,
        color_fn=lambda r: _training_status_color(r.get("training_status")),
        title_fn=lambda r: f"{r['label']}: {r.get('training_status') or '—'}",
    )


def _readiness_color(value: float | None) -> str:
    if value is None:
        return COLOR_NEUTRAL
    if value >= READINESS_GOOD:
        return COLOR_GOOD
    if value >= READINESS_WARN:
        return COLOR_YELLOW
    return COLOR_BAD


def _body_battery_color(value: float | None) -> str:
    if value is None:
        return COLOR_NEUTRAL
    if value >= BODY_BATTERY_GOOD:
        return COLOR_GOOD
    if value >= BODY_BATTERY_WARN:
        return COLOR_WARN
    return COLOR_BAD


def _stress_color(value: float | None) -> str:
    if value is None:
        return COLOR_NEUTRAL
    if value <= STRESS_GOOD:
        return COLOR_GOOD
    if value <= STRESS_WARN:
        return COLOR_YELLOW
    if value <= STRESS_BAD:
        return COLOR_WARN
    return COLOR_BAD


def _html_recovery_stress(rows: list[dict[str, Any]]) -> str:
    sections = [
        ("Readiness", "training_readiness", _readiness_color),
        ("Body battery (wake)", "body_battery_wake", _body_battery_color),
        ("Stress", "avg_stress", _stress_color),
    ]
    parts: list[str] = []
    for title, key, color_fn in sections:
        parts.append(
            f'<p style="font-size:11px;color:{MUTED};margin:12px 0 4px;font-family:{FONT};">'
            f"{_esc(title)}</p>"
        )
        parts.append(
            _html_dot_row(
                rows,
                color_fn=lambda r, k=key, fn=color_fn: fn(r.get(k)),
                title_fn=lambda r, k=key: f"{r['label']}: {r.get(k) if r.get(k) is not None else '—'}",
            )
        )
    return "".join(parts)


def _html_activity_impact(daily_rows: list[dict[str, Any]]) -> str:
    if not daily_rows:
        return f'<p style="color:{MUTED};font-family:{FONT};font-size:12px;">No data</p>'

    all_impacts = [
        float(act["impact"])
        for day in daily_rows
        for act in day.get("activities") or []
    ]
    if not all_impacts:
        return f'<p style="color:{MUTED};font-family:{FONT};font-size:12px;">No activities</p>'

    max_val = max(max(all_impacts), ACTIVITY_IMPACT_GOAL, 1.0) * 1.08
    trs: list[str] = []
    for day in daily_rows:
        acts = day.get("activities") or []
        bg = f' bgcolor="{_WEEKEND_BG}"' if _row_is_weekend(day) else ""
        if not acts:
            trs.append(
                f"<tr{bg}>"
                f'<td style="padding:3px 8px;font-size:11px;color:{MUTED};font-family:{FONT};">'
                f"{_esc(_short_label(day['label']))}</td>"
                f'<td colspan="2" style="padding:3px 8px;font-size:11px;color:{MUTED};'
                f'font-family:{FONT};">—</td></tr>'
            )
            continue
        for i, act in enumerate(acts):
            val = float(act["impact"])
            color = COLOR_GOOD if val > ACTIVITY_IMPACT_GOAL else COLOR_NEUTRAL
            label = _short_label(day["label"]) if i == 0 else ""
            trs.append(
                f"<tr{bg if i == 0 else ''}>"
                f'<td style="padding:3px 8px;font-size:11px;color:{MUTED};font-family:{FONT};">'
                f"{_esc(label)}</td>"
                f'<td style="padding:3px 8px;width:58%;">{_html_h_bar(val, max_val, color)}</td>'
                f'<td style="padding:3px 8px;font-size:11px;color:{TEXT};font-family:{FONT};'
                f'text-align:right;">{_esc(f"{val:.1f}")}</td>'
                f"</tr>"
            )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"{''.join(trs)}</table>"
    )


def _stat_cards(
    enriched: list[dict[str, Any]], activity_summary: dict[str, Any]
) -> list[tuple[str, str, str, str]]:
    good_steps = _count_highlights(enriched, "steps", "good")
    good_rhr = _count_highlights(enriched, "resting_hr", "good")
    hrv_balanced = _count_highlights(enriched, "hrv_status", "good")
    hrv_unbalanced = _count_highlights(enriched, "hrv_status", "warn")
    hrv_low = _count_highlights(enriched, "hrv_status", "bad")
    good_cal = _count_highlights(enriched, "active_calories", "good")
    warn_sleep = _count_highlights(enriched, "sleep_score", "warn")
    half = (len(enriched) + 1) // 2
    return [
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


def build_email_friendly_html(
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
    stat_cards = _stat_cards(enriched, activity_summary)

    sections: list[str] = [
        f"""<table width="{EMAIL_W}" cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:12px;">
<tr><td style="padding:8px 0;font-family:{FONT};">
  <div style="font-size:22px;font-weight:600;color:{TEXT};">Garmin Health Dashboard</div>
  <div style="font-size:13px;color:{MUTED};margin-top:6px;">{_esc(period_label)} · generated {_esc(generated_at)} · avg RHR {_esc(avg_rhr_display)}</div>
</td>
<td align="right" valign="top" style="padding:8px 0;">
  <span style="font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:#5794f2;border:1px solid rgba(87,148,242,0.35);padding:4px 10px;border-radius:999px;">{_esc(mode)}</span>
</td></tr></table>""",
        _email_legend(),
        _email_panel("Summary", "Period averages", _email_stats_table(stat_cards)),
        _email_panel(
            "Steps",
            "Highlight if ≥10,000",
            _html_bar_chart(enriched, "steps", "steps", goal_line=STEP_GOAL),
        ),
        _email_panel(
            "Resting heart rate",
            "Green below period average",
            _html_rhr_chart(enriched, period_avg_rhr),
        ),
        _email_panel(
            "Active calories",
            "Highlight if >500 kcal",
            _html_bar_chart(
                enriched, "active_calories", "active_calories", goal_line=ACTIVE_CAL_GOAL
            ),
        ),
        _email_panel(
            "Sleep score",
            "Scale 0–100 · highlight if <90",
            _html_bar_chart(
                enriched,
                "sleep_score",
                "sleep_score",
                goal_line=SLEEP_SCORE_WARN,
                y_max_fixed=SLEEP_SCORE_MAX,
            ),
        ),
    ]

    if any(r.get("endurance_score") is not None for r in enriched):
        avg_endurance = _avg([r["endurance_score"] for r in enriched])
        sections.append(
            _email_panel(
                "Endurance score",
                f"Daily score · avg {_fmt(round(avg_endurance or 0))}",
                _html_bar_chart(
                    enriched,
                    "endurance_score",
                    "__none__",
                    default_color=COLOR_ACCENT,
                ),
            )
        )

    sections.append(
        _email_panel(
            "HRV status",
            "Balanced = green · Unbalanced = orange · Low = red",
            _html_hrv_chart(enriched),
        )
    )

    if any(
        r.get("training_readiness") is not None
        or r.get("body_battery_wake") is not None
        or r.get("avg_stress") is not None
        for r in enriched
    ):
        avg_readiness = _avg([r["training_readiness"] for r in enriched])
        avg_bb = _avg([r["body_battery_wake"] for r in enriched])
        avg_stress = _avg([r["avg_stress"] for r in enriched])
        sublegend = (
            f'<p style="font-size:11px;color:{MUTED};margin:0 0 8px;font-family:{FONT};">'
            f"Readiness avg {_fmt(round(avg_readiness or 0))} · "
            f"BB wake avg {_fmt(round(avg_bb or 0))} · "
            f"Stress avg {_fmt(round(avg_stress or 0))}</p>"
        )
        sections.append(
            _email_panel(
                "Recovery & stress trends",
                "Colored dots = significance",
                sublegend + _html_recovery_stress(enriched),
            )
        )

    sections.extend(
        [
            _email_panel(
                "Training status",
                "Yellow maintaining · Green productive · Pink strained · Blue recovery",
                _html_training_strip(enriched),
            ),
            _email_panel(
                "Activity fitness impact",
                "Impact = aerobic TE + anaerobic TE · green if >8.0",
                _html_activity_impact(activity_summary.get("daily_impacts", [])),
            ),
        ]
    )

    top = activity_summary.get("top_impact")
    top_rule = "No activities recorded"
    if top:
        top_rule = f"#1 {top['name']} · impact {top['impact']}"

    sections.extend(
        [
            _email_panel(
                "Activity breakdown",
                f"{activity_summary['total']} total activities",
                _email_data_table(
                    ["Type", "Count", "Share", "Duration", ""],
                    _email_activity_breakdown(activity_summary),
                ),
            ),
            _email_panel(
                "Fitness impact ranking",
                top_rule,
                _email_data_table(
                    ["Activity", "Date", "Aerobic TE", "Anaerobic TE", "Impact"],
                    _email_fitness_impact(activity_summary),
                ),
            ),
        ]
    )

    table_rows = "\n".join(
        f"<tr>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};font-family:{FONT};font-size:13px;color:{TEXT};\">{_esc(r['label'])}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_pill(r['steps'], r['highlights'].get('steps'))}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_pill(r['resting_hr'], r['highlights'].get('resting_hr'))}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_hrv_pill(r['hrv_status'], r['highlights'].get('hrv_status'))}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_pill(round(r['active_calories']) if r['active_calories'] is not None else None, r['highlights'].get('active_calories'))}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_pill(r['sleep_score'], r['highlights'].get('sleep_score'))}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_training_pill(r['training_status'])}</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};\">{_email_pill(r['endurance_score'], None)}</td>"
        f"</tr>"
        for r in enriched
    )
    sections.append(
        _email_panel(
            "Daily breakdown",
            "Per-day values and highlight status",
            _email_data_table(
                ["Date", "Steps", "Resting HR", "HRV", "Active Cal", "Sleep", "Training", "Endurance"],
                table_rows,
            ),
        )
    )

    body = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Garmin Health — {mode.title()} Report</title>
</head>
<body style="margin:0;padding:0;background:{BG};">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG};" role="presentation">
    <tr><td align="center" style="padding:24px 12px;">
      <table width="{EMAIL_W}" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG};" role="presentation">
        <tr><td>{body}</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""
