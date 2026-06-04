"""Email HTML dashboard — dark theme matching browser dashboard, charts as PNG images."""

from __future__ import annotations

from datetime import date
from typing import Any

from garmin_chart_png import svg_to_png_data_uri
from garmin_dashboard import (
    ACTIVE_CAL_GOAL,
    COLOR_ACCENT,
    COLOR_GOOD,
    COLOR_WARN,
    COLOR_YELLOW,
    SLEEP_SCORE_MAX,
    SLEEP_SCORE_WARN,
    STEP_GOAL,
    _avg,
    _count_highlights,
    _fmt,
    _hrv_status_color,
    _svg_activity_impact_chart,
    _svg_bar_chart,
    _svg_hrv_chart,
    _svg_metric_line_chart,
    _svg_recovery_stress_panel,
    _svg_rhr_line_chart,
    _svg_status_strip,
    _training_status_color,
    classify_row,
)

EMAIL_W = 680
FONT = "Inter,Arial,Helvetica,sans-serif"
BG = "#0b0c0e"
PANEL = "#111217"
PANEL2 = "#181b1f"
BORDER = "#2c3235"
TEXT = "#d8d9da"
MUTED = "#8e8e8e"
ACCENT = "#5794f2"

TD = (
    f'style="padding:10px 12px;border-bottom:1px solid {BORDER};'
    f'font-family:{FONT};font-size:13px;color:{TEXT};"'
)
TH = (
    f'style="padding:8px 12px;border-bottom:1px solid {BORDER};'
    f'font-family:{FONT};font-size:11px;color:{MUTED};'
    f'text-transform:uppercase;text-align:left;"'
)

_PILL = {
    "good": ("#73bf69", "rgba(115,191,105,0.12)"),
    "warn": ("#ff9830", "rgba(255,152,48,0.14)"),
    "bad": ("#f2495c", "rgba(242,73,92,0.14)"),
    "neutral": ("#8e8e8e", "transparent"),
}

_TONE_COLOR = {"good": "#73bf69", "warn": "#ff9830", "bad": "#f2495c", "": TEXT}


def _esc(text: Any) -> str:
    s = str(text if text is not None else "—")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chart_img(svg: str, alt: str) -> str:
    uri = svg_to_png_data_uri(svg, width=EMAIL_W)
    if uri:
        return (
            f'<img src="{uri}" width="{EMAIL_W}" alt="{_esc(alt)}" '
            f'style="display:block;width:100%;max-width:{EMAIL_W}px;height:auto;border:0;" />'
        )
    return (
        f'<p style="color:{MUTED};font-family:{FONT};font-size:12px;margin:8px 0;">'
        f"Chart unavailable — run: pip install cairosvg</p>"
    )


def _email_pill(value: Any, highlight: str | None) -> str:
    fg, bg = _PILL.get(highlight or "neutral", _PILL["neutral"])
    display = _fmt(round(value)) if isinstance(value, float) else _fmt(value)
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;'
        f'font-size:11px;font-weight:600;color:{fg};background:{bg};">{_esc(display)}</span>'
    )


def _email_hrv_pill(status: str | None, highlight: str | None) -> str:
    return _email_pill(status or "—", highlight)


def _email_training_pill(status: str | None) -> str:
    if not status:
        return _email_pill("—", "neutral")
    color = _training_status_color(status)
    label = status.replace("_", " ").title()
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;'
        f'font-size:11px;font-weight:600;color:{color};background:{color}22;">'
        f"{_esc(label)}</span>"
    )


def _email_panel(title: str, rule: str, body: str) -> str:
    return f"""<table width="{EMAIL_W}" cellpadding="0" cellspacing="0" style="margin-bottom:12px;border:1px solid {BORDER};background:{PANEL};">
<tr><td style="padding:10px 14px;background:{PANEL2};border-bottom:1px solid {BORDER};font-family:{FONT};">
  <span style="font-size:13px;font-weight:600;color:{TEXT};">{_esc(title)}</span>
  <span style="float:right;font-size:11px;color:{MUTED};">{_esc(rule)}</span>
</td></tr>
<tr><td style="padding:8px 12px 4px;background:{PANEL};">{body}</td></tr>
</table>"""


def _email_stats_table(stat_cards: list[tuple[str, str, str, str]]) -> str:
    cells: list[str] = []
    for label, value, meta, tone in stat_cards:
        color = _TONE_COLOR.get(tone, TEXT)
        cells.append(
            f'<td width="33%" valign="top" style="padding:4px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {BORDER};background:{PANEL};">'
            f'<tr><td style="padding:14px;font-family:{FONT};">'
            f'<div style="font-size:11px;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:0.06em;">{_esc(label)}</div>'
            f'<div style="font-size:26px;font-weight:600;color:{color};margin:8px 0 4px;">'
            f"{_esc(value)}</div>"
            f'<div style="font-size:12px;color:{MUTED};">{_esc(meta)}</div>'
            f"</td></tr></table></td>"
        )
    rows_html: list[str] = []
    for i in range(0, len(cells), 3):
        chunk = cells[i : i + 3]
        while len(chunk) < 3:
            chunk.append(f'<td width="33%" style="padding:4px;">&nbsp;</td>')
        rows_html.append(f"<tr>{''.join(chunk)}</tr>")
    return f'<table width="100%" cellpadding="0" cellspacing="0">{"".join(rows_html)}</table>'


def _email_data_table(headers: list[str], table_rows: str) -> str:
    head = "".join(f"<th {TH}>{_esc(h)}</th>" for h in headers)
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
        f"<thead><tr>{head}</tr></thead><tbody>{table_rows}</tbody></table>"
    )


def _email_activity_breakdown(summary: dict[str, Any]) -> str:
    if not summary["breakdown"]:
        return f"<tr><td colspan='5' {TD}>No activities in this period</td></tr>"
    rows = []
    for row in summary["breakdown"]:
        rows.append(
            f"<tr>"
            f"<td {TD}>{_esc(row['type'])}</td>"
            f"<td {TD}>{row['count']}</td>"
            f"<td {TD}>{row['share_pct']}%</td>"
            f"<td {TD}>{row['minutes']} min</td>"
            f'<td {TD}><table width="{row["share_pct"]}%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="height:8px;background:{ACCENT};font-size:0;line-height:0;">&nbsp;</td></tr>'
            f"</table></td></tr>"
        )
    return "\n".join(rows)


def _email_fitness_impact(summary: dict[str, Any]) -> str:
    impacts = summary.get("ranked_impacts") or []
    if not impacts:
        return f"<tr><td colspan='5' {TD}>No activities in this period</td></tr>"
    rows = []
    for row in impacts:
        bg = "rgba(115,191,105,0.12)" if row.get("is_good_impact") else "transparent"
        hl = "good" if row.get("is_good_impact") else "neutral"
        rows.append(
            f'<tr style="background:{bg};">'
            f"<td {TD}>{_esc(row['name'])}</td>"
            f"<td {TD}>{_esc(row['date'])}</td>"
            f"<td {TD}>{row['aerobic_te']}</td>"
            f"<td {TD}>{row['anaerobic_te']}</td>"
            f"<td {TD}>{_email_pill(row['impact'], hl)}</td></tr>"
        )
    return "\n".join(rows)


def _email_legend() -> str:
    items = [
        (COLOR_GOOD, "Green = good"),
        (COLOR_WARN, "Orange = attention"),
        (COLOR_YELLOW, "Yellow = moderate"),
        ("#f2495c", "Red = low / high stress"),
        ("rgba(255,255,255,0.06)", "Weekend shading on charts"),
    ]
    spans = []
    for color, label in items:
        if "rgba" in color:
            dot = (
                f'<span style="display:inline-block;width:14px;height:8px;'
                f"background:{color};border:1px solid rgba(255,255,255,0.12);"
                f'border-radius:2px;margin-right:4px;"></span>'
            )
        else:
            dot = (
                f'<span style="display:inline-block;width:8px;height:8px;'
                f"background:{color};border-radius:50%;margin-right:4px;"
                f'vertical-align:middle;"></span>'
            )
        spans.append(
            f'<span style="margin-right:14px;font-size:11px;color:{MUTED};">'
            f"{dot}{_esc(label)}</span>"
        )
    return (
        f'<div style="margin-bottom:14px;font-family:{FONT};line-height:1.8;">'
        f"{''.join(spans)}</div>"
    )


def build_email_html(
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
        ("Steps", _fmt(round(_avg([r["steps"] for r in enriched]) or 0)), f"{good_steps} days ≥10k", "good" if good_steps >= half else ""),
        ("Resting HR", _fmt(round(_avg([r["resting_hr"] for r in enriched]) or 0), " bpm"), f"{good_rhr} days below avg", ""),
        ("HRV balanced days", str(hrv_balanced), f"{hrv_low} low · {hrv_unbalanced} unbalanced", "good" if hrv_low == 0 and hrv_unbalanced == 0 else ("bad" if hrv_low else "warn")),
        ("Active calories", _fmt(round(_avg([r["active_calories"] for r in enriched]) or 0), " kcal"), f"{good_cal} days >500", "good" if good_cal >= half else ""),
        ("Sleep score", _fmt(round(_avg([r["sleep_score"] for r in enriched if r["sleep_score"] is not None]) or 0)), f"{warn_sleep} days <90 · scale 0–100", "warn" if warn_sleep else "good"),
        ("Activities", str(activity_summary["total"]), "workouts in period", "good" if activity_summary["total"] else ""),
    ]

    sections: list[str] = [
        f"""<table width="{EMAIL_W}" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
<tr><td style="padding:8px 0;font-family:{FONT};">
  <div style="font-size:22px;font-weight:600;color:{TEXT};">Garmin Health Dashboard</div>
  <div style="font-size:13px;color:{MUTED};margin-top:6px;">{_esc(period_label)} · generated {_esc(generated_at)} · avg RHR {_esc(avg_rhr_display)}</div>
</td>
<td align="right" valign="top" style="padding:8px 0;">
  <span style="font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:{ACCENT};border:1px solid rgba(87,148,242,0.35);padding:4px 10px;border-radius:999px;">{_esc(mode)}</span>
</td></tr></table>""",
        _email_legend(),
        _email_panel("Summary", "Period averages", _email_stats_table(stat_cards)),
        _email_panel(
            "Steps",
            "Highlight if ≥10,000",
            _chart_img(_svg_bar_chart(enriched, "steps", "steps", goal_line=STEP_GOAL), "Steps"),
        ),
        _email_panel(
            "Resting heart rate",
            "Green dots below period average",
            _chart_img(_svg_rhr_line_chart(enriched, period_avg_rhr), "Resting heart rate"),
        ),
        _email_panel(
            "Active calories",
            "Highlight if >500 kcal",
            _chart_img(
                _svg_bar_chart(enriched, "active_calories", "active_calories", goal_line=ACTIVE_CAL_GOAL),
                "Active calories",
            ),
        ),
        _email_panel(
            "Sleep score",
            "Scale 0–100 · highlight if <90",
            _chart_img(
                _svg_bar_chart(
                    enriched,
                    "sleep_score",
                    "sleep_score",
                    goal_line=SLEEP_SCORE_WARN,
                    y_max_fixed=SLEEP_SCORE_MAX,
                    goal_line_color=COLOR_WARN,
                ),
                "Sleep score",
            ),
        ),
    ]

    if any(r.get("endurance_score") is not None for r in enriched):
        avg_endurance = _avg([r["endurance_score"] for r in enriched])
        sections.append(
            _email_panel(
                "Endurance score",
                f"Daily score · avg {_fmt(round(avg_endurance or 0))}",
                _chart_img(
                    _svg_metric_line_chart(
                        enriched, "endurance_score", line_color=COLOR_ACCENT, aria_label="Endurance"
                    ),
                    "Endurance score",
                ),
            )
        )

    sections.append(
        _email_panel(
            "HRV status",
            "Balanced = green · Unbalanced = orange · Low = red",
            _chart_img(_svg_hrv_chart(enriched), "HRV status"),
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
                sublegend + _chart_img(_svg_recovery_stress_panel(enriched), "Recovery and stress"),
            )
        )

    sections.append(
        _email_panel(
            "Training status",
            "Yellow maintaining · Green productive · Pink strained · Blue recovery",
            _chart_img(
                _svg_status_strip(
                    enriched, "training_status", _training_status_color, height=220, aria_label="Training"
                ),
                "Training status",
            ),
        )
    )
    sections.append(
        _email_panel(
            "Activity fitness impact",
            "Impact = aerobic TE + anaerobic TE · green if >8.0",
            _chart_img(
                _svg_activity_impact_chart(activity_summary.get("daily_impacts", [])),
                "Activity fitness impact",
            ),
        )
    )

    top = activity_summary.get("top_impact")
    top_rule = "No activities recorded"
    if top:
        top_rule = f"#1 {top['name']} · impact {top['impact']}"

    sections.append(
        _email_panel(
            "Activity breakdown",
            f"{activity_summary['total']} total activities",
            _email_data_table(
                ["Type", "Count", "Share", "Duration", ""],
                _email_activity_breakdown(activity_summary),
            ),
        )
    )
    sections.append(
        _email_panel(
            "Fitness impact ranking",
            top_rule,
            _email_data_table(
                ["Activity", "Date", "Aerobic TE", "Anaerobic TE", "Impact"],
                _email_fitness_impact(activity_summary),
            ),
        )
    )

    table_rows = "\n".join(
        f"<tr>"
        f"<td {TD}>{_esc(r['label'])}</td>"
        f"<td {TD}>{_email_pill(r['steps'], r['highlights'].get('steps'))}</td>"
        f"<td {TD}>{_email_pill(r['resting_hr'], r['highlights'].get('resting_hr'))}</td>"
        f"<td {TD}>{_email_hrv_pill(r['hrv_status'], r['highlights'].get('hrv_status'))}</td>"
        f"<td {TD}>{_email_pill(round(r['active_calories']) if r['active_calories'] is not None else None, r['highlights'].get('active_calories'))}</td>"
        f"<td {TD}>{_email_pill(r['sleep_score'], r['highlights'].get('sleep_score'))}</td>"
        f"<td {TD}>{_email_training_pill(r['training_status'])}</td>"
        f"<td {TD}>{_email_pill(r['endurance_score'], None)}</td>"
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
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG};">
    <tr><td align="center" style="padding:24px 12px;">
      <table width="{EMAIL_W}" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG};">
        <tr><td>{body}</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""
