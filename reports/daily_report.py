#!/usr/bin/env python3
"""Daily report generation for Yewoo & Yeseo.

Outputs yesterday's activity totals with 7-day rolling averages and trend arrows.
Designed to be called by n8n at 7:10am AEST daily (reporting on the previous day).

Usage:
    python daily_report.py [--date YYYY-MM-DD] [--child_id N] [--format text|json]
"""

import argparse
import json
import sys
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from config import CHILDREN, TIMEZONE
from db import get_connection


def trend_indicator(today_val, avg_val):
    if avg_val == 0:
        return "NEW" if today_val > 0 else ""
    pct = (today_val - avg_val) / avg_val * 100
    if pct > 10:
        return "\u2191"
    elif pct < -10:
        return "\u2193"
    else:
        return "\u2192"


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


def make_bar(actual, average, width=10):
    """Build a visual bar with ║ fixed at the midpoint (position width//2).

    The average always maps to the midpoint. Actual fills proportionally:
      actual=0      → no fill
      actual=avg    → fills to ║
      actual=2*avg  → fills entire bar (capped)
    """
    mid = width // 2  # ║ position (5 for width=10)
    if average > 0:
        fill = round((actual / average) * mid)
    elif actual > 0:
        fill = mid  # NEW subject: fill to midpoint
    else:
        fill = 0
    fill = max(0, min(fill, width))  # clamp 0..width
    filled = "█" * fill
    dots = "·" * (width - fill)
    # Insert ║ at the midpoint
    bar = filled + dots
    bar = bar[:mid] + "║" + bar[mid + 1:]
    return f"[{bar}]"


def query_today_categories(conn, child_id, report_date):
    """Get today's totals by category. Routine is merged into Rest."""
    sql = """
        SELECT
            CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
            SUM(actual_minutes) as total_minutes
        FROM activity_logs
        WHERE child_id = %s AND activity_date = %s
        GROUP BY cat;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def query_today_subjects(conn, child_id, report_date):
    """Get today's study breakdown by subject."""
    sql = """
        SELECT s.subject_name, SUM(al.actual_minutes) as minutes
        FROM activity_logs al
        JOIN subjects s ON al.subject_id = s.subject_id
        WHERE al.child_id = %s AND al.activity_date = %s AND al.category = 'Study'
        GROUP BY s.subject_name
        ORDER BY minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date))
        return [(row[0], int(row[1])) for row in cur.fetchall()]


def query_today_workouts(conn, child_id, report_date):
    """Get today's workout breakdown."""
    sql = """
        SELECT w.workout_name, SUM(al.actual_minutes) as minutes
        FROM activity_logs al
        JOIN workout_types w ON al.workout_id = w.workout_id
        WHERE al.child_id = %s AND al.activity_date = %s AND al.category = 'Workout'
        GROUP BY w.workout_name
        ORDER BY minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date))
        return [(row[0], int(row[1])) for row in cur.fetchall()]


def query_avg_categories(conn, child_id, report_date):
    """Get 7-day daily average per category (excluding report_date). Routine merged into Rest."""
    sql = """
        SELECT
            CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
            ROUND(SUM(actual_minutes)::numeric /
                  GREATEST(COUNT(DISTINCT activity_date), 1), 0) as avg_daily_minutes
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s - INTERVAL '7 days' AND %s - INTERVAL '1 day'
        GROUP BY cat;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date, report_date))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def query_avg_subjects(conn, child_id, report_date):
    """Get 7-day daily average study breakdown by subject."""
    sql = """
        SELECT s.subject_name,
               ROUND(SUM(al.actual_minutes)::numeric /
                     GREATEST(COUNT(DISTINCT al.activity_date), 1), 0) as avg_daily_minutes
        FROM activity_logs al
        JOIN subjects s ON al.subject_id = s.subject_id
        WHERE al.child_id = %s
          AND al.activity_date BETWEEN %s - INTERVAL '7 days' AND %s - INTERVAL '1 day'
          AND al.category = 'Study'
        GROUP BY s.subject_name
        ORDER BY avg_daily_minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date, report_date))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def query_avg_workouts(conn, child_id, report_date):
    """Get 7-day daily average workout breakdown by type."""
    sql = """
        SELECT w.workout_name,
               ROUND(SUM(al.actual_minutes)::numeric /
                     GREATEST(COUNT(DISTINCT al.activity_date), 1), 0) as avg_daily_minutes
        FROM activity_logs al
        JOIN workout_types w ON al.workout_id = w.workout_id
        WHERE al.child_id = %s
          AND al.activity_date BETWEEN %s - INTERVAL '7 days' AND %s - INTERVAL '1 day'
          AND al.category = 'Workout'
        GROUP BY w.workout_name
        ORDER BY avg_daily_minutes DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date, report_date))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def count_history_days(conn, child_id, report_date):
    """Count distinct days with data in the 7-day lookback window."""
    sql = """
        SELECT COUNT(DISTINCT activity_date)
        FROM activity_logs
        WHERE child_id = %s
          AND activity_date BETWEEN %s - INTERVAL '7 days' AND %s - INTERVAL '1 day';
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, report_date, report_date))
        return cur.fetchone()[0]


def format_daily_sms(name, report_date, today_cats, today_subjects,
                     today_workouts, avg_cats, avg_subjects, avg_workouts,
                     history_days):
    sep_double = "══════════════════════════════════════"
    sep_single = "──────────────────────────────────────"
    day_name = report_date.strftime("%b %d (%a)")
    lines = [f"\U0001f4ca {name} Daily Report — {day_name}", sep_double]

    # No data case
    if not today_cats:
        lines.append("No activities logged today.")
        lines.append(sep_double)
        return "\n".join(lines)

    limited = ", limited data" if history_days < 3 else ""

    # --- Study section ---
    study_total = today_cats.get("Study", 0)
    study_avg = avg_cats.get("Study", 0)
    arrow = trend_indicator(study_total, study_avg)
    avg_note = f"avg {format_minutes(study_avg)}{limited}" if study_avg > 0 else "NEW"
    lines.append("")
    study_bar = make_bar(study_total, study_avg)
    lines.append(f"\U0001f4da Study  {format_minutes(study_total)} {study_bar} {arrow} ({avg_note})")
    lines.append(sep_single)

    # Collect all subjects (today + avg)
    all_subjects = {}
    for subj, mins in today_subjects:
        all_subjects[subj] = {"today": mins}
    for subj, avg in avg_subjects.items():
        if subj not in all_subjects:
            all_subjects[subj] = {"today": 0}
        all_subjects[subj]["avg"] = avg

    # Find max subject name length for alignment
    subj_names = list(all_subjects.keys()) if all_subjects else []
    pad = max((len(s) for s in subj_names), default=10)

    for subj, vals in all_subjects.items():
        today_val = vals.get("today", 0)
        avg_val = vals.get("avg", 0)
        time_str = format_minutes(today_val) if today_val > 0 else "\u2014"
        bar = make_bar(today_val, avg_val)
        if avg_val > 0:
            subj_arrow = trend_indicator(today_val, avg_val)
            avg_str = f"{subj_arrow} avg {format_minutes(avg_val)}"
        else:
            avg_str = "NEW"
        lines.append(f"{subj:<{pad}s}  {time_str:>5s} {bar} {avg_str}")

    # --- Workout section ---
    workout_total = today_cats.get("Workout", 0)
    workout_avg = avg_cats.get("Workout", 0)
    arrow = trend_indicator(workout_total, workout_avg)
    avg_note = f"avg {format_minutes(workout_avg)}{limited}" if workout_avg > 0 else "NEW"
    lines.append("")
    workout_bar = make_bar(workout_total, workout_avg)
    lines.append(f"\U0001f3c3 Workout  {format_minutes(workout_total)} {workout_bar} {arrow} ({avg_note})")
    lines.append(sep_single)

    # Collect all workouts (today + avg)
    all_workouts = {}
    for wname, mins in today_workouts:
        all_workouts[wname] = {"today": mins}
    for wname, avg in avg_workouts.items():
        if wname not in all_workouts:
            all_workouts[wname] = {"today": 0}
        all_workouts[wname]["avg"] = avg

    if all_workouts:
        w_pad = max(len(w) for w in all_workouts)
        for wname, vals in all_workouts.items():
            today_val = vals.get("today", 0)
            avg_val = vals.get("avg", 0)
            time_str = format_minutes(today_val) if today_val > 0 else "\u2014"
            bar = make_bar(today_val, avg_val)
            if avg_val > 0:
                w_arrow = trend_indicator(today_val, avg_val)
                avg_str = f"{w_arrow} avg {format_minutes(avg_val)}"
            else:
                avg_str = "NEW"
            lines.append(f"{wname:<{w_pad}s}  {time_str:>5s} {bar} {avg_str}")
    else:
        lines.append("  No workout logged")

    # --- Rest section ---
    rest_total = today_cats.get("Rest", 0)
    rest_avg = avg_cats.get("Rest", 0)
    lines.append("")
    if rest_total == 0 and rest_avg == 0:
        lines.append("\U0001f634 Rest  not logged")
    else:
        arrow = trend_indicator(rest_total, rest_avg)
        lines.append(f"\U0001f634 Rest  {format_minutes(rest_total)} {arrow}  (avg {format_minutes(rest_avg)}{limited})")
    lines.append(sep_double)

    return "\n".join(lines)


def generate_daily_report(conn, child_id, name, report_date):
    today_cats = query_today_categories(conn, child_id, report_date)
    today_subjects = query_today_subjects(conn, child_id, report_date)
    today_workouts = query_today_workouts(conn, child_id, report_date)
    avg_cats = query_avg_categories(conn, child_id, report_date)
    avg_subjects = query_avg_subjects(conn, child_id, report_date)
    avg_workouts = query_avg_workouts(conn, child_id, report_date)
    history_days = count_history_days(conn, child_id, report_date)

    return format_daily_sms(name, report_date, today_cats, today_subjects,
                            today_workouts, avg_cats, avg_subjects,
                            avg_workouts, history_days)


def main():
    parser = argparse.ArgumentParser(description="Generate daily activity report")
    parser.add_argument("--date", type=str, default=None,
                        help="Report date (YYYY-MM-DD). Defaults to today (Melbourne time).")
    parser.add_argument("--child_id", type=int, default=None,
                        help="Generate for specific child (1=Yewoo, 2=Yeseo). Default: both.")
    parser.add_argument("--format", dest="fmt", choices=["text", "json"], default="text",
                        help="Output format. Default: text.")
    args = parser.parse_args()

    if args.date:
        report_date = date.fromisoformat(args.date)
    else:
        report_date = date.today() - timedelta(days=1)  # report on yesterday

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
            results[name.lower()] = generate_daily_report(conn, child_id, name, report_date)
    finally:
        conn.close()

    if args.fmt == "json":
        print(json.dumps(results, ensure_ascii=False))
    else:
        print("\n---\n".join(results.values()))


if __name__ == "__main__":
    main()
