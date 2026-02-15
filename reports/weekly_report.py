#!/usr/bin/env python3
"""Weekly report generation for Yewoo & Yeseo.

Outputs weekly totals with 4-week rolling averages, trend arrows, and
study/workout breakdowns. Supports text (SMS), HTML (email), and JSON output.
Designed to be called by n8n Saturday at 9pm AEST.

Usage:
    python weekly_report.py [--week-ending YYYY-MM-DD] [--child_id N] [--format text|html|json]
"""

import argparse
import json
import sys
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from config import CHILDREN, CHILDREN_KR, TIMEZONE
from db import get_connection


def trend_indicator(current, avg):
    if avg == 0:
        return "NEW" if current > 0 else ""
    pct = (current - avg) / avg * 100
    if pct > 10:
        return "\u2191"
    elif pct < -10:
        return "\u2193"
    else:
        return "\u2192"


def trend_color(current, avg):
    if avg == 0:
        return "#888"
    pct = (current - avg) / avg * 100
    if pct > 10:
        return "green"
    elif pct < -10:
        return "red"
    else:
        return "#888"


def format_minutes(minutes):
    if minutes is None or minutes == 0:
        return "0m"
    minutes = int(minutes)
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours}h{mins}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{mins}m"


# ---------------------------------------------------------------------------
# SQL Queries
# ---------------------------------------------------------------------------

def query_week_categories(conn, child_id, week_end):
    """This week's totals by category. Routine merged into Rest."""
    week_start = week_end - timedelta(days=6)
    sql = """
        SELECT
            CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
            SUM(actual_minutes) as total_minutes,
            COUNT(*) as sessions
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s AND %s
        GROUP BY cat;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, week_start, week_end))
        return {row[0]: {"minutes": int(row[1]), "sessions": int(row[2])} for row in cur.fetchall()}


def query_week_subjects(conn, child_id, week_end):
    """This week's study breakdown by subject."""
    week_start = week_end - timedelta(days=6)
    sql = """
        SELECT s.subject_name, s.is_academic,
               SUM(al.actual_minutes) as total_minutes,
               COUNT(*) as sessions,
               COUNT(DISTINCT al.activity_date) as days_studied
        FROM activity_logs al
        JOIN subjects s ON al.subject_id = s.subject_id
        WHERE al.child_id = %s
          AND al.activity_date BETWEEN %s AND %s
          AND al.category = 'Study'
        GROUP BY s.subject_name, s.is_academic
        ORDER BY total_minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, week_start, week_end))
        return [{"name": r[0], "academic": r[1], "minutes": int(r[2]),
                 "sessions": int(r[3]), "days": int(r[4])} for r in cur.fetchall()]


def query_week_workouts(conn, child_id, week_end):
    """This week's workout breakdown."""
    week_start = week_end - timedelta(days=6)
    sql = """
        SELECT w.workout_name,
               SUM(al.actual_minutes) as total_minutes,
               COUNT(*) as sessions
        FROM activity_logs al
        JOIN workout_types w ON al.workout_id = w.workout_id
        WHERE al.child_id = %s
          AND al.activity_date BETWEEN %s AND %s
          AND al.category = 'Workout'
        GROUP BY w.workout_name
        ORDER BY total_minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, week_start, week_end))
        return [{"name": r[0], "minutes": int(r[1]), "sessions": int(r[2])} for r in cur.fetchall()]


def query_daily_breakdown(conn, child_id, week_end):
    """Daily totals for the week."""
    week_start = week_end - timedelta(days=6)
    sql = """
        SELECT activity_date,
               CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
               SUM(actual_minutes) as total_minutes
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s AND %s
        GROUP BY activity_date, cat
        ORDER BY activity_date;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, week_start, week_end))
        daily = {}
        for row in cur.fetchall():
            d = row[0]
            if d not in daily:
                daily[d] = {}
            daily[d][row[1]] = int(row[2])
        return daily


def query_days_active(conn, child_id, week_end):
    """Count distinct active days this week."""
    week_start = week_end - timedelta(days=6)
    sql = """
        SELECT COUNT(DISTINCT activity_date)
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s AND %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, week_start, week_end))
        return cur.fetchone()[0]


def query_4week_avg_categories(conn, child_id, week_end):
    """4-week weekly average per category. Routine merged into Rest."""
    avg_end = week_end - timedelta(days=7)
    avg_start = week_end - timedelta(days=34)
    sql = """
        SELECT
            CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
            ROUND(SUM(actual_minutes)::numeric /
                  GREATEST(COUNT(DISTINCT DATE_TRUNC('week', activity_date)), 1), 0) as avg_weekly_minutes
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s AND %s
        GROUP BY cat;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, avg_start, avg_end))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def query_4week_avg_subjects(conn, child_id, week_end):
    """4-week weekly average study breakdown by subject."""
    avg_end = week_end - timedelta(days=7)
    avg_start = week_end - timedelta(days=34)
    sql = """
        SELECT s.subject_name,
               ROUND(SUM(al.actual_minutes)::numeric /
                     GREATEST(COUNT(DISTINCT DATE_TRUNC('week', al.activity_date)), 1), 0) as avg_weekly_minutes
        FROM activity_logs al
        JOIN subjects s ON al.subject_id = s.subject_id
        WHERE al.child_id = %s
          AND al.activity_date BETWEEN %s AND %s
          AND al.category = 'Study'
        GROUP BY s.subject_name
        ORDER BY avg_weekly_minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, avg_start, avg_end))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def query_4week_avg_days_active(conn, child_id, week_end):
    """4-week average of days active per week."""
    avg_end = week_end - timedelta(days=7)
    avg_start = week_end - timedelta(days=34)
    sql = """
        SELECT COUNT(DISTINCT activity_date)::numeric /
               GREATEST(COUNT(DISTINCT DATE_TRUNC('week', activity_date)), 1)
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s AND %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, avg_start, avg_end))
        result = cur.fetchone()[0]
        return round(float(result), 1) if result else 0


def query_weekly_goals(conn, child_id, week_end):
    """Get weekly goals if set."""
    week_start = week_end - timedelta(days=6)
    sql = """
        SELECT target_study_hours, target_workout_count
        FROM weekly_goals
        WHERE child_id = %s AND week_start_date = %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, week_start))
        row = cur.fetchone()
        if row:
            return {"study_hours": row[0], "workout_count": row[1]}
        return None


# ---------------------------------------------------------------------------
# SMS Formatter
# ---------------------------------------------------------------------------

def format_weekly_sms(name, week_end, week_cats, week_subjects, week_workouts,
                      days_active, avg_cats, avg_subjects, avg_days_active):
    week_start = week_end - timedelta(days=6)
    header = f"[{name}]"
    lines = [header]

    # Study
    study = week_cats.get("Study", {}).get("minutes", 0)
    study_avg = avg_cats.get("Study", 0)
    arrow = trend_indicator(study, study_avg)
    lines.append(f"Study: {format_minutes(study)} {arrow} (4wk avg: {format_minutes(study_avg)})")

    # Subject pairs on same line
    subj_strs = []
    for s in week_subjects:
        avg = avg_subjects.get(s["name"], 0)
        a = trend_indicator(s["minutes"], avg)
        subj_strs.append(f"{s['name']} {format_minutes(s['minutes']):>6s} {a}")

    for i in range(0, len(subj_strs), 2):
        pair = subj_strs[i:i+2]
        lines.append("  " + " | ".join(pair))

    # Workout
    workout = week_cats.get("Workout", {}).get("minutes", 0)
    workout_avg = avg_cats.get("Workout", 0)
    arrow = trend_indicator(workout, workout_avg)
    lines.append(f"Workout: {format_minutes(workout)} {arrow} (4wk avg: {format_minutes(workout_avg)})")

    for w in week_workouts:
        lines.append(f"  {w['name']} {w['sessions']}x {format_minutes(w['minutes'])}")

    # Rest (only if logged)
    rest = week_cats.get("Rest", {}).get("minutes", 0)
    rest_avg = avg_cats.get("Rest", 0)
    if rest > 0 or rest_avg > 0:
        arrow = trend_indicator(rest, rest_avg)
        lines.append(f"Rest: {format_minutes(rest)} {arrow} (4wk avg: {format_minutes(rest_avg)})")

    # Days active
    lines.append(f"Days active: {days_active}/7 (4wk avg: {avg_days_active}/7)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML Email Formatter
# ---------------------------------------------------------------------------

def format_weekly_html(name, child_id, week_end, week_cats, week_subjects,
                       week_workouts, daily_breakdown, avg_cats, avg_subjects):
    week_start = week_end - timedelta(days=6)
    kr_name = CHILDREN_KR.get(child_id, "")

    study = week_cats.get("Study", {}).get("minutes", 0)
    study_avg = avg_cats.get("Study", 0)
    workout = week_cats.get("Workout", {}).get("minutes", 0)
    workout_avg = avg_cats.get("Workout", 0)
    rest = week_cats.get("Rest", {}).get("minutes", 0)
    rest_avg = avg_cats.get("Rest", 0)

    def trend_html(current, avg):
        arrow = trend_indicator(current, avg)
        color = trend_color(current, avg)
        if avg > 0:
            return f'<div style="color: {color}; font-size: 14px;">{arrow} vs {format_minutes(avg)} avg</div>'
        elif current > 0:
            return '<div style="color: #888; font-size: 14px;">NEW</div>'
        return '<div style="font-size: 14px;">-</div>'

    # Study subject rows
    study_rows = ""
    for s in week_subjects:
        avg = avg_subjects.get(s["name"], 0)
        arrow = trend_indicator(s["minutes"], avg)
        color = trend_color(s["minutes"], avg)
        study_rows += f"""    <tr>
      <td style="padding: 4px 8px;">{s['name']}</td>
      <td style="text-align: right; padding: 4px 8px;">{format_minutes(s['minutes'])}</td>
      <td style="text-align: right; padding: 4px 8px;">{format_minutes(avg)}</td>
      <td style="text-align: center; padding: 4px 8px; color: {color};">{arrow}</td>
    </tr>\n"""

    # Workout rows
    workout_rows = ""
    for w in week_workouts:
        workout_rows += f"""    <tr>
      <td style="padding: 4px 8px;">{w['name']}</td>
      <td style="text-align: right; padding: 4px 8px;">{w['sessions']}</td>
      <td style="text-align: right; padding: 4px 8px;">{format_minutes(w['minutes'])}</td>
    </tr>\n"""

    # Daily rows
    daily_rows = ""
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(7):
        d = week_start + timedelta(days=i)
        data = daily_breakdown.get(d, {})
        day_label = day_names[d.weekday()]
        s = format_minutes(data.get("Study", 0)) if data.get("Study", 0) else "-"
        w = format_minutes(data.get("Workout", 0)) if data.get("Workout", 0) else "-"
        r = format_minutes(data.get("Rest", 0)) if data.get("Rest", 0) else "-"
        daily_rows += f"    <tr><td style=\"padding: 4px;\">{day_label}</td><td style=\"padding: 4px;\">{s}</td><td style=\"padding: 4px;\">{w}</td><td style=\"padding: 4px;\">{r}</td></tr>\n"

    return f"""<div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
  <h3 style="color: #2196F3; margin-top: 0;">{name} ({kr_name})</h3>

  <table style="width: 100%; margin-bottom: 16px;">
    <tr>
      <td style="text-align: center; padding: 8px; background: #E3F2FD; border-radius: 4px;">
        <div style="font-size: 24px; font-weight: bold;">{format_minutes(study)}</div>
        <div style="font-size: 12px; color: #666;">Study</div>
        {trend_html(study, study_avg)}
      </td>
      <td style="text-align: center; padding: 8px; background: #E8F5E9; border-radius: 4px;">
        <div style="font-size: 24px; font-weight: bold;">{format_minutes(workout)}</div>
        <div style="font-size: 12px; color: #666;">Workout</div>
        {trend_html(workout, workout_avg)}
      </td>
      <td style="text-align: center; padding: 8px; background: #FFF3E0; border-radius: 4px;">
        <div style="font-size: 24px; font-weight: bold;">{format_minutes(rest)}</div>
        <div style="font-size: 12px; color: #666;">Rest</div>
        {trend_html(rest, rest_avg)}
      </td>
    </tr>
  </table>

  <h4 style="margin-bottom: 4px;">Study Breakdown</h4>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
    <tr style="background: #f5f5f5;">
      <th style="text-align: left; padding: 4px 8px;">Subject</th>
      <th style="text-align: right; padding: 4px 8px;">This Week</th>
      <th style="text-align: right; padding: 4px 8px;">4wk Avg</th>
      <th style="text-align: center; padding: 4px 8px;">Trend</th>
    </tr>
{study_rows}  </table>

  <h4 style="margin-bottom: 4px;">Workout Breakdown</h4>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
    <tr style="background: #f5f5f5;">
      <th style="text-align: left; padding: 4px 8px;">Type</th>
      <th style="text-align: right; padding: 4px 8px;">Sessions</th>
      <th style="text-align: right; padding: 4px 8px;">Total Time</th>
    </tr>
{workout_rows}  </table>

  <h4 style="margin-bottom: 4px;">Daily Breakdown</h4>
  <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
    <tr style="background: #f5f5f5;">
      <th style="padding: 4px;">Day</th>
      <th style="padding: 4px;">Study</th>
      <th style="padding: 4px;">Workout</th>
      <th style="padding: 4px;">Rest</th>
    </tr>
{daily_rows}  </table>
</div>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_child_report(conn, child_id, name, week_end):
    week_cats = query_week_categories(conn, child_id, week_end)
    week_subjects = query_week_subjects(conn, child_id, week_end)
    week_workouts = query_week_workouts(conn, child_id, week_end)
    daily_breakdown = query_daily_breakdown(conn, child_id, week_end)
    days_active = query_days_active(conn, child_id, week_end)
    avg_cats = query_4week_avg_categories(conn, child_id, week_end)
    avg_subjects = query_4week_avg_subjects(conn, child_id, week_end)
    avg_days_active = query_4week_avg_days_active(conn, child_id, week_end)

    sms = format_weekly_sms(name, week_end, week_cats, week_subjects,
                            week_workouts, days_active, avg_cats, avg_subjects,
                            avg_days_active)
    html = format_weekly_html(name, child_id, week_end, week_cats, week_subjects,
                              week_workouts, daily_breakdown, avg_cats, avg_subjects)

    return {"sms": sms, "html": html}


def main():
    parser = argparse.ArgumentParser(description="Generate weekly activity report")
    parser.add_argument("--week-ending", type=str, default=None,
                        help="Week ending date, should be Saturday (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--child_id", type=int, default=None,
                        help="Generate for specific child (1=Yewoo, 2=Yeseo). Default: both.")
    parser.add_argument("--format", dest="fmt", choices=["text", "html", "json"], default="text",
                        help="Output format. Default: text.")
    args = parser.parse_args()

    if args.week_ending:
        week_end = date.fromisoformat(args.week_ending)
    else:
        week_end = date.today()

    try:
        conn = get_connection()
    except Exception as e:
        print(f"Database connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    results = {}
    try:
        for child_id, name in CHILDREN.items():
            if args.child_id and args.child_id != child_id:
                continue
            results[name.lower()] = generate_child_report(conn, child_id, name, week_end)
    finally:
        conn.close()

    week_start = week_end - timedelta(days=6)

    if args.fmt == "json":
        print(json.dumps(results, ensure_ascii=False))
    elif args.fmt == "html":
        header = f"<h2 style=\"color: #333;\">Weekly Report: {week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}</h2>"
        body = "\n".join(r["html"] for r in results.values())
        print(f'<html>\n<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">\n{header}\n{body}\n</body>\n</html>')
    else:
        header = f"Weekly Report: {week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
        sms_parts = [header, ""]
        for r in results.values():
            sms_parts.append(r["sms"])
            sms_parts.append("")
        print("\n".join(sms_parts).rstrip())


if __name__ == "__main__":
    main()
