#!/usr/bin/env python3
"""
Notion Activity Timer → PostgreSQL activity_logs sync.

Reads completed (Done=true) sessions from per-kid Notion timer databases
and inserts them into the PostgreSQL activity_logs table.

Duplicate prevention is handled via a unique notion_page_id column in the DB,
so re-running the sync for the same date is safe.

Each kid has their own Notion database (no "Who" field needed):
  - Yewoo Timer (child_id=1)
  - Yeseo Timer (child_id=2)

Usage:
    python notion_sync.py                      # sync today's completed entries
    python notion_sync.py --dry-run             # preview without writing
    python notion_sync.py --date 2026-02-15     # sync entries for a specific date
    python notion_sync.py --all                 # sync ALL completed entries regardless of date
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta

import requests
import psycopg2

from config import DB_CONFIG, NOTION_DB_IDS, CHILDREN, MAX_DURATION

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"
SUBJECTS_FILE = os.path.join(os.path.dirname(__file__), "subjects.json")


def load_subjects():
    with open(SUBJECTS_FILE, "r") as f:
        data = json.load(f)
    subject_ids = {int(k): v for k, v in data["subject_ids"].items()}
    workout_ids = {int(k): v for k, v in data["workout_ids"].items()}
    aliases = data.get("activity_aliases", {})
    return subject_ids, workout_ids, aliases


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def query_completed_entries(db_id, target_date=None):
    """Query a Notion database for completed (Done=true) entries."""
    url = f"{NOTION_BASE}/databases/{db_id}/query"

    filters = [
        {"property": "Done", "checkbox": {"equals": True}},
    ]

    if target_date:
        next_day = target_date + timedelta(days=1)
        filters.append({
            "timestamp": "created_time",
            "created_time": {"on_or_after": f"{target_date}T00:00:00"},
        })
        filters.append({
            "timestamp": "created_time",
            "created_time": {"before": f"{next_day}T00:00:00"},
        })

    body = {"filter": {"and": filters}}

    entries = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = requests.post(url, headers=notion_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        entries.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return entries


def parse_entry(entry, child_id, subject_ids, workout_ids, aliases):
    """Parse a Notion page into an activity_logs-ready dict."""
    props = entry["properties"]
    who = CHILDREN[child_id]

    # Subject: prefer Subject select, fall back to Activity title
    subj_sel = props.get("Subject", {}).get("select")
    subject_name = subj_sel["name"] if subj_sel else None

    if not subject_name:
        title_parts = props.get("Activity", {}).get("title", [])
        raw_title = "".join(p.get("plain_text", "") for p in title_parts).strip()
        subject_name = aliases.get(raw_title, raw_title)

    # Infer category from subject
    category = None
    if subject_name == "Rest":
        category = "Rest"
    elif subject_name in workout_ids.get(child_id, {}):
        category = "Workout"
    elif subject_name in subject_ids.get(child_id, {}):
        category = "Study"

    if not category:
        return None, f"Cannot infer category for subject: {subject_name}"

    # Map subject → subject_id / workout_id
    subject_id = None
    workout_id = None
    if category == "Study":
        subject_id = subject_ids.get(child_id, {}).get(subject_name)
        if subject_id is None:
            return None, f"Unknown study subject for {who}: {subject_name}"
    elif category == "Workout":
        workout_id = workout_ids.get(child_id, {}).get(subject_name)
        if workout_id is None:
            return None, f"Unknown workout for {who}: {subject_name}"

    # Created (auto-set, tamper-proof) and Finished (last_edited_time)
    start_str = props.get("Created", {}).get("created_time")
    end_str = props.get("Finished", {}).get("last_edited_time")

    if not start_str or not end_str:
        return None, "Missing Created or Finished time"

    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    actual_minutes = int((end_dt - start_dt).total_seconds() / 60)

    if actual_minutes <= 0:
        return None, f"Invalid duration: {actual_minutes} minutes"

    max_dur = MAX_DURATION.get(child_id, 120)
    if actual_minutes > max_dur:
        return None, f"Duration {actual_minutes}min exceeds max {max_dur}min for {who}"

    activity_date = start_dt.date()

    # Notes / deviation reason
    notes_parts = props.get("Notes", {}).get("rich_text", [])
    notes = "".join(p.get("plain_text", "") for p in notes_parts) if notes_parts else None

    # Activity title (for logging)
    title_parts = props.get("Activity", {}).get("title", [])
    title = "".join(p.get("plain_text", "") for p in title_parts) if title_parts else ""

    return {
        "page_id": entry["id"],
        "title": title,
        "child_id": child_id,
        "who": who,
        "category": category,
        "subject_name": subject_name,
        "subject_id": subject_id,
        "workout_id": workout_id,
        "activity_date": activity_date,
        "actual_minutes": actual_minutes,
        "deviation_reason": notes,
    }, None


def insert_activity_log(conn, record):
    """Insert one record into activity_logs. Skips duplicates via notion_page_id.
    Returns the new log_id, or None if it was a duplicate."""
    sql = """
        INSERT INTO activity_logs
            (child_id, category, subject_id, workout_id,
             activity_date, actual_minutes, deviation_reason, notion_page_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (notion_page_id) DO NOTHING
        RETURNING log_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            record["child_id"],
            record["category"],
            record["subject_id"],
            record["workout_id"],
            record["activity_date"],
            record["actual_minutes"],
            record["deviation_reason"],
            record["page_id"],
        ))
        row = cur.fetchone()
        return row[0] if row else None


def main():
    parser = argparse.ArgumentParser(description="Sync Notion Activity Timer → PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--date", type=str, default=None,
                        help="Sync entries for a specific date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true",
                        help="Sync all completed entries regardless of date")
    args = parser.parse_args()

    if not NOTION_API_KEY:
        print("Error: NOTION_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Determine target date
    target_date = None
    if args.date:
        target_date = date.fromisoformat(args.date)
    elif not args.all:
        target_date = date.today()

    date_label = str(target_date) if target_date else "all dates"

    subject_ids, workout_ids, aliases = load_subjects()

    synced = []
    errors = []

    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(**DB_CONFIG)

    try:
        for child_id, db_id in NOTION_DB_IDS.items():
            who = CHILDREN[child_id]
            print(f"Querying {who}'s timer for completed entries ({date_label})...")

            entries = query_completed_entries(db_id, target_date)
            print(f"  Found {len(entries)} completed entries.")

            for entry in entries:
                record, err = parse_entry(entry, child_id, subject_ids, workout_ids, aliases)
                if err:
                    page_id = entry["id"]
                    errors.append({"page_id": page_id, "who": who, "error": err})
                    print(f"  SKIP {page_id[:8]}...: {err}")
                    continue

                if args.dry_run:
                    print(f"  [DRY RUN] {who} | {record['category']} | "
                          f"{record['subject_name'] or 'N/A'} | "
                          f"{record['actual_minutes']}min | {record['activity_date']}")
                    synced.append({
                        "who": who,
                        "category": record["category"],
                        "subject": record["subject_name"],
                        "minutes": record["actual_minutes"],
                        "date": str(record["activity_date"]),
                    })
                else:
                    log_id = insert_activity_log(conn, record)
                    conn.commit()
                    if log_id:
                        print(f"  SYNCED {who} | {record['category']} | "
                              f"{record['subject_name'] or 'N/A'} | "
                              f"{record['actual_minutes']}min → log_id={log_id}")
                        synced.append({
                            "who": who,
                            "category": record["category"],
                            "subject": record["subject_name"],
                            "minutes": record["actual_minutes"],
                            "date": str(record["activity_date"]),
                            "log_id": log_id,
                        })
                    else:
                        print(f"  SKIP (duplicate) {who} | {record['category']} | "
                              f"{record['subject_name'] or 'N/A'} | "
                              f"{record['actual_minutes']}min")
    finally:
        if conn:
            conn.close()

    result = {
        "synced": len(synced),
        "errors": len(errors),
        "details": synced,
        "error_details": errors if errors else None,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
