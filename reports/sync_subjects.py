#!/usr/bin/env python3
"""Sync Notion timer Subject options → subjects.json + PostgreSQL.

Reads Subject select options from each kid's Notion timer database,
compares with subjects.json, inserts any new subjects into PostgreSQL,
and updates subjects.json.

Run before notion_sync.py (e.g. 11:45pm, 5 min before the 11:50pm sync).

Usage:
    python sync_subjects.py              # sync subjects
    python sync_subjects.py --dry-run    # preview without writing
"""

import argparse
import json
import os
import sys

import requests
import psycopg2

from config import DB_CONFIG, NOTION_DB_IDS, CHILDREN, WORKOUT_IDS

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"
SUBJECTS_FILE = os.path.join(os.path.dirname(__file__), "subjects.json")

WORKOUT_NAMES = set()
for wmap in WORKOUT_IDS.values():
    WORKOUT_NAMES.update(wmap.keys())

REST_NAMES = {"Rest", "Dinner", "Sleep", "Break"}


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def load_subjects():
    with open(SUBJECTS_FILE, "r") as f:
        return json.load(f)


def save_subjects(data):
    with open(SUBJECTS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_notion_subjects(db_id):
    """Fetch Subject select options from a Notion database."""
    url = f"{NOTION_BASE}/databases/{db_id}"
    resp = requests.get(url, headers=notion_headers())
    resp.raise_for_status()
    db = resp.json()
    subject_prop = db.get("properties", {}).get("Subject", {})
    options = subject_prop.get("select", {}).get("options", [])
    return [opt["name"] for opt in options]


def insert_subject(conn, child_id, subject_name):
    """Insert a new subject into PostgreSQL and return the subject_id."""
    sql = """
        INSERT INTO subjects (child_id, subject_name, is_academic)
        VALUES (%s, %s, true)
        RETURNING subject_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (child_id, subject_name))
        return cur.fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description="Sync Notion subjects → subjects.json + DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if not NOTION_API_KEY:
        print("Error: NOTION_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    data = load_subjects()
    new_count = 0

    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(**DB_CONFIG)

    try:
        for child_id, db_id in NOTION_DB_IDS.items():
            who = CHILDREN[child_id]
            cid = str(child_id)
            notion_subjects = get_notion_subjects(db_id)
            known_subjects = set(data["subject_ids"].get(cid, {}).keys())
            known_workouts = set(data["workout_ids"].get(cid, {}).keys())
            all_known = known_subjects | known_workouts | REST_NAMES

            for subj in notion_subjects:
                if subj in all_known:
                    continue

                if subj in WORKOUT_NAMES:
                    print(f"  SKIP {who} | {subj} (workout, add manually)")
                    continue

                if args.dry_run:
                    print(f"  [DRY RUN] NEW {who} | {subj}")
                else:
                    subject_id = insert_subject(conn, child_id, subj)
                    conn.commit()
                    if cid not in data["subject_ids"]:
                        data["subject_ids"][cid] = {}
                    data["subject_ids"][cid][subj] = subject_id
                    print(f"  ADDED {who} | {subj} → subject_id={subject_id}")

                new_count += 1

    finally:
        if conn:
            conn.close()

    if new_count > 0 and not args.dry_run:
        save_subjects(data)
        print(f"Updated subjects.json with {new_count} new subject(s)")
    elif new_count == 0:
        print("No new subjects found")

    print(json.dumps({"new_subjects": new_count}))


if __name__ == "__main__":
    main()
