# Case Study: Building an Automated Activity Tracking & Reporting System

A reproducible blueprint for building a Notion-based activity tracker with PostgreSQL storage, Docker-containerised sync/report scripts, and n8n workflow automation with SMS/email delivery.

**Original project:** Weekly Report — tracking Study, Workout, and Rest for two teenage daughters.

---

## Table of Contents

1. [Prerequisites: Configure MCP Servers & Validate Twilio](#step-0-prerequisites)
2. [Create PostgreSQL Database and Schema](#step-1-create-postgresql-database-and-schema)
3. [Create Input Data Interface Using Notion](#step-2-create-input-data-interface-using-notion)
4. [Create Python Sync Script and Docker Files](#step-3-create-python-sync-script-and-docker-files)
5. [Create n8n Workflow to Collect Data](#step-4-create-n8n-workflow-to-collect-data)
6. [Create Python Report Scripts and Update Docker](#step-5-create-python-report-scripts-and-update-docker)
7. [Create n8n Workflows for Report Automation](#step-6-create-n8n-workflows-for-report-automation)
8. [Lessons Learned](#lessons-learned)
9. [Reproduction Checklist](#reproduction-checklist)

---

## Step 0: Prerequisites

Before writing any code, set up the tools you'll interact with throughout the project. Claude Code with MCP servers lets you query your database and manage n8n workflows directly from the terminal.

### 0.1 Configure PostgreSQL MCP Server

Add the postgres MCP server to your Claude Code config (`~/.claude.json` or project-level `.claude/mcp.json`) so you can query your database directly during development:

```json
{
  "mcpServers": {
    "postgres-server": {
      "command": "npx",
      "args": [
        "mcp-server-postgres",
        "postgresql://postgres:YOUR_PASSWORD@your-host:5432/your_database"
      ]
    }
  }
}
```

**Why this matters:** You can run SQL queries directly in Claude Code to verify schema, check data, and debug — no need to switch to a separate database client.

Example usage once configured:
```
# Ask Claude Code to query the database
"Show me all rows in the children table"
→ Uses mcp__postgres-server__query tool automatically
```

### 0.2 Configure n8n MCP Server

Add the n8n MCP server so you can create, inspect, and manage automation workflows directly:

```json
{
  "mcpServers": {
    "n8n-mcp": {
      "command": "npx",
      "args": ["n8n-mcp"],
      "env": {
        "N8N_BASE_URL": "https://your-n8n-instance.com",
        "N8N_API_KEY": "your-n8n-api-key"
      }
    }
  }
}
```

**Getting your n8n API key:**
1. Open your n8n instance → Settings → API
2. Create a new API key
3. Copy it into the env config above

**Available n8n MCP tools:**
- `n8n_health_check` — verify connectivity
- `n8n_create_workflow` — create workflows programmatically
- `n8n_get_workflow` — inspect existing workflows
- `n8n_list_workflows` — see all workflows
- `n8n_update_full_workflow` / `n8n_update_partial_workflow` — modify workflows
- `n8n_test_workflow` — test execution
- `n8n_deploy_template` — deploy from n8n.io templates

### 0.3 Validate Twilio Phone Numbers

Before building any SMS-sending workflows, validate that your phone numbers are correctly formatted and registered with Twilio. Invalid numbers cause silent delivery failures that are hard to debug later.

**Steps:**

1. **Sign up for Twilio** and get your Account SID, Auth Token, and a Twilio phone number (the sender).

2. **Verify recipient numbers** — In Twilio's trial mode, you must verify every number you want to send to:
   - Twilio Console → Phone Numbers → Verified Caller IDs
   - Add each recipient's number and complete the verification call/SMS

3. **Use E.164 format** — All phone numbers must be in international format:
   ```
   +61412345678    ✅  (Australian mobile)
   0412345678      ❌  (missing country code)
   +61 412 345 678 ❌  (no spaces allowed)
   ```

4. **Test send before automating** — Send a test SMS from the Twilio console or via curl:
   ```bash
   curl -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_SID/Messages.json" \
     -u "$TWILIO_SID:$TWILIO_AUTH" \
     --data-urlencode "To=+61412345678" \
     --data-urlencode "From=+1234567890" \
     --data-urlencode "Body=Test message"
   ```

5. **Configure Twilio credentials in n8n:**
   - n8n → Credentials → Add Credential → Twilio API
   - Enter Account SID and Auth Token
   - In workflow SMS nodes, select this credential and set:
     - **From:** your Twilio number (E.164)
     - **To:** recipient number (E.164, verified)

**Common issues:**
- "The 'To' number is not a valid phone number" → missing `+` prefix or country code
- "The number is unverified" → add it in Twilio Console → Verified Caller IDs (trial accounts only)
- SMS sent but not received → check Twilio logs for delivery status; some carriers block short-code messages

---

## Step 1: Create PostgreSQL Database and Schema

### 1.1 Create the Database

```sql
CREATE DATABASE family_member_schedule;
```

### 1.2 Create the Enum

```sql
CREATE TYPE activity_category AS ENUM ('Study', 'Workout', 'Rest', 'Routine');
```

**Why `Routine`?** It's a sub-type of Rest (e.g., morning routine, bedtime routine). Report scripts merge Routine into Rest for display, but keeping them separate in the database preserves the distinction for future analysis.

### 1.3 Create Tables

```sql
-- People being tracked
CREATE TABLE children (
    child_id   SERIAL PRIMARY KEY,
    name       VARCHAR NOT NULL,
    age        INTEGER
);

-- Academic and non-academic subjects (per child)
CREATE TABLE subjects (
    subject_id   SERIAL PRIMARY KEY,
    child_id     INTEGER REFERENCES children(child_id),
    subject_name VARCHAR NOT NULL,
    is_academic  BOOLEAN DEFAULT TRUE
);

-- Workout types with weekly targets (per child)
CREATE TABLE workout_types (
    workout_id                 SERIAL PRIMARY KEY,
    child_id                   INTEGER REFERENCES children(child_id),
    workout_name               VARCHAR NOT NULL,
    target_sessions_per_week   INTEGER DEFAULT 0,
    target_minutes_per_session INTEGER
);

-- Every activity session logged here
CREATE TABLE activity_logs (
    log_id           SERIAL PRIMARY KEY,
    child_id         INTEGER REFERENCES children(child_id),
    category         activity_category NOT NULL,
    subject_id       INTEGER REFERENCES subjects(subject_id),
    workout_id       INTEGER REFERENCES workout_types(workout_id),
    activity_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    actual_minutes   INTEGER NOT NULL,
    deviation_reason TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Optional: weekly goal targets
CREATE TABLE weekly_goals (
    goal_id              SERIAL PRIMARY KEY,
    child_id             INTEGER REFERENCES children(child_id),
    week_start_date      DATE NOT NULL,
    target_study_hours   DOUBLE PRECISION,
    target_workout_count INTEGER
);
```

### 1.4 Seed Reference Data

```sql
INSERT INTO children (name, age) VALUES ('Second Daughter', 15), ('First Daughter', 16);

-- Second Daughter's subjects
INSERT INTO subjects (child_id, subject_name, is_academic) VALUES
  (1, 'Maths', true), (1, 'Chemistry', true), (1, 'Physics', true),
  (1, 'Reading', true), (1, 'Biology', true), (1, 'JMSS Prep', true);

-- First Daughter's subjects
INSERT INTO subjects (child_id, subject_name, is_academic) VALUES
  (2, 'Piano Practice', false), (2, 'Music Theory', false),
  (2, 'Music Composition', false), (2, 'Review/Planning', true),
  (2, 'Chemistry', true), (2, 'Legal Studies', true),
  (2, 'Methods', true), (2, 'Literature', true);

-- Workout types
INSERT INTO workout_types (child_id, workout_name, target_sessions_per_week, target_minutes_per_session) VALUES
  (1, 'Jogging', 4, 30), (2, 'Jogging', 4, 30), (1, 'Tennis', 1, 180);
```

### 1.5 Relationships

```
activity_logs.child_id   → children.child_id
activity_logs.subject_id → subjects.subject_id
activity_logs.workout_id → workout_types.workout_id
subjects.child_id        → children.child_id
workout_types.child_id   → children.child_id
weekly_goals.child_id    → children.child_id
```

---

## Step 2: Create Input Data Interface Using Notion

### 2.1 Create a Notion Integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click "New integration"
3. Name it (e.g., "Activity Timer Sync")
4. Select the workspace
5. Copy the **Internal Integration Secret** — this becomes `NOTION_API_KEY`

### 2.2 Create Per-Person Timer Databases

Create a **separate Notion database for each person** (not one shared database).

**Why per-person, not shared?**
- No "Who" field needed — the database identity IS the person
- Simpler select dropdowns — each kid only sees their own subjects
- Kids can't accidentally see or modify each other's data
- Sync script maps database ID → child_id directly

**Database fields for each person:**

| Property | Type | Purpose |
|----------|------|---------|
| Activity | title | Optional label for the session |
| Subject | select | Pre-populated with that person's subjects + workout types |
| Done | checkbox | Kid checks this when they finish studying |
| Created | created_time | **Auto-set by Notion, cannot be manually edited** |
| Finished | last_edited_time | **Auto-updates when Done is checked** |
| Duration (min) | formula | `dateBetween(prop("Finished"), prop("Created"), "minutes")` |
| Notes | rich_text | Optional comment or deviation reason |
| Synced | checkbox | **Hidden from user** — set to true by sync script |

### 2.3 Why Tamper-Proof Timestamps Matter

The key insight: `created_time` and `last_edited_time` are **system fields that cannot be manually edited** by users. This means:

- **Created** = when the kid tapped "New" (started studying)
- **Finished** = when the kid checked "Done" (stopped studying)
- **Duration** = the real elapsed time, impossible to fake

If you used manual date fields instead, kids could enter whatever times they want. The system timestamps remove that temptation entirely.

### 2.4 Share and Configure

1. **Share database with integration:** Open each database → "..." menu → Connections → Add your integration
2. **Share with users as guests:** Share each database with the respective kid's Notion account
3. **Hide the Synced field:** In database view settings, hide the "Synced" property so users don't see or toggle it

### 2.5 Mobile UX Flow

The user experience on a phone:

```
1. Open Notion app → their timer database
2. Tap "New" to create a row (Created time auto-stamps NOW)
3. Pick Subject from dropdown (e.g., "Maths")
4. Study...
5. Check the "Done" checkbox (Finished time auto-stamps NOW)
6. Duration formula calculates automatically
```

Total user effort: 3 taps to start, 1 tap to finish.

---

## Step 3: Create Python Sync Script and Docker Files

### 3.1 Project Structure

```
├── Dockerfile
├── docker-compose.yml
├── .env                    # secrets (not committed)
├── reports/
│   ├── config.py           # DB config, Notion DB IDs, mappings
│   ├── db.py               # PostgreSQL connection helper
│   └── notion_sync.py      # Notion → PostgreSQL sync
```

### 3.2 config.py — Central Configuration

```python
import os

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "adventuretube.net"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "family_member_schedule"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

CHILDREN = {1: "Second Daughter", 2: "First Daughter"}

TIMEZONE = "Australia/Melbourne"

# Notion per-kid timer databases: child_id -> database_id
NOTION_DB_IDS = {
    1: "7b628dc68fee4d5bad66a3dbebb5560e",  # Second Daughter Timer
    2: "9662c755a6b249f2bfa6f1392c1d9b82",  # First Daughter Timer
}

# Maps: child_id -> {subject_name: subject_id}
SUBJECT_IDS = {
    1: {  # Second Daughter
        "Maths": 35, "Chemistry": 36, "Physics": 37,
        "Reading": 38, "Biology": 47, "JMSS Prep": 48,
    },
    2: {  # First Daughter
        "Piano Practice": 39, "Music Theory": 40, "Music Composition": 41,
        "Review/Planning": 42, "Chemistry": 43, "Legal Studies": 44,
        "Methods": 45, "Literature": 46,
    },
}

# Maps: child_id -> {workout_name: workout_id}
WORKOUT_IDS = {
    1: {"Jogging": 9, "Tennis": 11},   # Second Daughter
    2: {"Jogging": 10},                 # First Daughter
}
```

**Key design decisions:**
- DB credentials come from environment variables (Docker `.env`), with fallback defaults for local dev
- Subject/workout names in Notion must **exactly match** the keys in these maps
- Each person's Notion database ID maps to a child_id — no "Who" field parsing needed

### 3.3 db.py — Database Connection Helper

```python
import psycopg2
from config import DB_CONFIG

def get_connection():
    return psycopg2.connect(**DB_CONFIG)
```

### 3.4 notion_sync.py — The Sync Script

The sync script does three things:
1. **Query Notion** — find entries where `Done=true` and `Synced=false`
2. **Insert into PostgreSQL** — write each session to `activity_logs`
3. **Mark as Synced** — set `Synced=true` on the Notion page so it's not re-synced

```python
#!/usr/bin/env python3
"""Notion Activity Timer → PostgreSQL activity_logs sync."""

import argparse, json, os, sys
from datetime import datetime, date, timedelta
import requests, psycopg2
from config import DB_CONFIG, NOTION_DB_IDS, SUBJECT_IDS, WORKOUT_IDS, CHILDREN

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

def query_unsynced_entries(db_id, target_date=None):
    """Query Notion for Done=true, Synced=false entries."""
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    filters = [
        {"property": "Synced", "checkbox": {"equals": False}},
        {"property": "Done", "checkbox": {"equals": True}},
    ]
    if target_date:
        next_day = target_date + timedelta(days=1)
        filters.append({"timestamp": "created_time",
                        "created_time": {"on_or_after": f"{target_date}T00:00:00"}})
        filters.append({"timestamp": "created_time",
                        "created_time": {"before": f"{next_day}T00:00:00"}})

    body = {"filter": {"and": filters}}
    entries = []
    has_more, start_cursor = True, None

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

def parse_entry(entry, child_id):
    """Parse a Notion page into an activity_logs-ready dict."""
    props = entry["properties"]

    # Subject → infer category (Study or Workout)
    subj_sel = props.get("Subject", {}).get("select")
    subject_name = subj_sel["name"] if subj_sel else None

    if subject_name in WORKOUT_IDS.get(child_id, {}):
        category, workout_id = "Workout", WORKOUT_IDS[child_id][subject_name]
        subject_id = None
    elif subject_name in SUBJECT_IDS.get(child_id, {}):
        category, subject_id = "Study", SUBJECT_IDS[child_id][subject_name]
        workout_id = None
    else:
        return None, f"Unknown subject: {subject_name}"

    # Tamper-proof timestamps
    start_str = props.get("Created", {}).get("created_time")
    end_str = props.get("Finished", {}).get("last_edited_time")
    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    actual_minutes = int((end_dt - start_dt).total_seconds() / 60)

    if actual_minutes <= 0:
        return None, f"Invalid duration: {actual_minutes}min"

    return {
        "page_id": entry["id"],
        "child_id": child_id,
        "category": category,
        "subject_id": subject_id,
        "workout_id": workout_id,
        "activity_date": start_dt.date(),
        "actual_minutes": actual_minutes,
        "deviation_reason": None,  # populated from Notes field
    }, None

def insert_activity_log(conn, record):
    sql = """INSERT INTO activity_logs
             (child_id, category, subject_id, workout_id,
              activity_date, actual_minutes, deviation_reason)
             VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING log_id"""
    with conn.cursor() as cur:
        cur.execute(sql, (record["child_id"], record["category"],
                          record["subject_id"], record["workout_id"],
                          record["activity_date"], record["actual_minutes"],
                          record["deviation_reason"]))
        return cur.fetchone()[0]

def mark_synced(page_id):
    url = f"{NOTION_BASE}/pages/{page_id}"
    body = {"properties": {"Synced": {"checkbox": True}}}
    requests.patch(url, headers=notion_headers(), json=body).raise_for_status()
```

**CLI flags:**
```bash
python notion_sync.py                    # sync today's unsynced entries
python notion_sync.py --dry-run          # preview without writing to DB or Notion
python notion_sync.py --date 2026-02-15  # sync entries for a specific date
python notion_sync.py --all              # sync ALL unsynced entries regardless of date
```

### 3.5 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies only — scripts mounted at runtime
RUN pip install --no-cache-dir "psycopg2-binary>=2.9" "requests>=2.28"

CMD ["python3", "reports/notion_sync.py"]
```

**Key: scripts are mounted, not baked in.** The `./reports` directory is mounted read-only at runtime via docker-compose. This means you can edit scripts without rebuilding the image.

### 3.6 docker-compose.yml

```yaml
services:
  notion-sync:
    build: .
    volumes:
      - ./reports:/app/reports:ro
    environment:
      - TZ=Australia/Sydney
      - DB_HOST=adventuretube.net
      - DB_PORT=5432
      - DB_NAME=family_member_schedule
      - DB_USER=${POSTGRES_USER}
      - DB_PASSWORD=${POSTGRES_PASSWORD}
      - NOTION_API_KEY=${NOTION_API_KEY}
    command: ["python3", "reports/notion_sync.py"]
```

### 3.7 .env File

```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_db_password
NOTION_API_KEY=secret_xxxxxxxxx
```

**Never commit `.env` to git.** Add it to `.gitignore`.

---

## Step 4: Create n8n Workflow to Collect Data

### 4.1 Workflow: "Notion Timer → PostgreSQL Sync - Midnight"

This workflow runs once daily at midnight to pull completed sessions from Notion into the database.

**Workflow nodes:**

```
Schedule Trigger (12:00am AEST)
  → SSH Command (docker compose run --rm notion-sync)
    → Parse Result
      → Has Errors? (IF: exitCode > 0)
        → YES: SMS Error Alert
        → NO: done
```

### 4.2 Schedule Trigger

- **Trigger:** Cron
- **Expression:** `0 0 * * *` (midnight daily)
- **Timezone:** Australia/Sydney (AEST/AEDT)

### 4.3 SSH Command Node

```bash
cd ~/YewseoYewooWeeklyReport && docker compose run --rm notion-sync
```

- SSH credentials configured in n8n (host, user, private key)
- `--rm` flag removes the container after execution (no stale containers)

### 4.4 Error Detection — The exitCode Lesson

**CRITICAL LESSON: Check `exitCode`, NOT `stderr`.**

```
❌ WRONG: if (stderr is not empty) → alert
✅ RIGHT: if (exitCode > 0) → alert
```

**Why?** Docker and Python write normal informational messages to stderr:
```
# This appears in stderr but is NOT an error:
"Querying Second Daughter's timer for unsynced entries (2026-02-15)..."
"  Found 3 unsynced entries."
```

If you trigger alerts on `stderr not empty`, you'll get false alarms on every successful run. The correct check is:

```javascript
// In n8n IF node expression:
{{ $json.exitCode > 0 }}
```

### 4.5 SMS Error Alert

On error, send an SMS to the parent with:
- Workflow name
- Error output (stdout + stderr)
- Timestamp

---

## Step 5: Create Python Report Scripts and Update Docker

### 5.1 daily_report.py — Daily SMS Report

Generates a per-person daily report showing today's activity totals with 7-day rolling averages and trend arrows.

**Output format:**
```
[Second Daughter] Daily Report - Feb 13 (Fri)

Study: 3h0m ↓ (7d avg: 5h12m)
  Maths        2h0m → (avg 2h0m)
  Chemistry    1h0m ↓ (avg 1h48m)
  Physics        -  ↓ (avg 36m)

Workout: 3h0m ↑ (7d avg: 42m)
  Tennis       3h0m

Rest: not logged
```

**Trend arrows:**
- `↑` — more than 10% above 7-day average
- `↓` — more than 10% below 7-day average
- `→` — within 10% of average
- `NEW` — no prior history

**Key SQL pattern — 7-day rolling average:**
```sql
SELECT
    CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
    ROUND(SUM(actual_minutes)::numeric /
          GREATEST(COUNT(DISTINCT activity_date), 1), 0) as avg_daily_minutes
FROM activity_logs
WHERE child_id = %s
  AND activity_date BETWEEN %s - INTERVAL '7 days' AND %s - INTERVAL '1 day'
GROUP BY cat;
```

**Note:** `Routine` is merged into `Rest` using `CASE WHEN` in SQL, so reports show three clean categories.

**CLI:**
```bash
python daily_report.py                              # both children, today, text
python daily_report.py --child_id 1 --format json   # Second Daughter only, JSON output
python daily_report.py --date 2026-02-13            # specific date
```

### 5.2 weekly_report.py — Weekly SMS + HTML Report

Generates weekly totals with 4-week rolling averages. Produces both SMS (plain text) and HTML (email) output.

**SMS output:**
```
Weekly Report: Feb 9 - Feb 15

[Second Daughter]
Study: 22h30m ↑ (4wk avg: 19h45m)
  Maths  10h0m ↑ | Chem  7h30m ↑
  Physics 3h30m → | JMSS  1h0m NEW
Workout: 5h30m ↑ (4wk avg: 2h30m)
  Jogging 4x 2h0m → | Tennis 1x 3h0m NEW
Days active: 5/7 (4wk avg: 4.5/7)
```

**HTML email structure:**
1. Summary cards per child — Study (blue `#E3F2FD`), Workout (green `#E8F5E9`), Rest (orange `#FFF3E0`)
2. Study breakdown table — Subject | This Week | 4wk Avg | Trend
3. Workout breakdown table — Type | Sessions | Total Time
4. Daily breakdown table — Day | Study | Workout | Rest

**Key SQL pattern — 4-week rolling average:**
```sql
SELECT
    CASE WHEN category = 'Routine' THEN 'Rest' ELSE category::text END as cat,
    ROUND(SUM(actual_minutes)::numeric /
          GREATEST(COUNT(DISTINCT DATE_TRUNC('week', activity_date)), 1), 0)
          as avg_weekly_minutes
FROM activity_logs
WHERE child_id = %s
  AND activity_date BETWEEN %s - INTERVAL '34 days' AND %s - INTERVAL '7 days'
GROUP BY cat;
```

**CLI:**
```bash
python weekly_report.py                                    # both, this week, text
python weekly_report.py --child_id 2 --format html         # First Daughter, HTML
python weekly_report.py --week-ending 2026-02-15 --format json  # JSON
```

### 5.3 Update docker-compose.yml

Add report services that share the same Dockerfile but run different commands:

```yaml
services:
  notion-sync:
    build: .
    volumes:
      - ./reports:/app/reports:ro
    environment:
      - TZ=Australia/Sydney
      - DB_HOST=adventuretube.net
      - DB_PORT=5432
      - DB_NAME=family_member_schedule
      - DB_USER=${POSTGRES_USER}
      - DB_PASSWORD=${POSTGRES_PASSWORD}
      - NOTION_API_KEY=${NOTION_API_KEY}
    command: ["python3", "reports/notion_sync.py"]

  daily-report:
    build: .
    volumes:
      - ./reports:/app/reports:ro
    environment:
      - TZ=Australia/Sydney
      - DB_HOST=adventuretube.net
      - DB_PORT=5432
      - DB_NAME=family_member_schedule
      - DB_USER=${POSTGRES_USER}
      - DB_PASSWORD=${POSTGRES_PASSWORD}
    command: ["python3", "reports/daily_report.py"]

  weekly-report:
    build: .
    volumes:
      - ./reports:/app/reports:ro
    environment:
      - TZ=Australia/Sydney
      - DB_HOST=adventuretube.net
      - DB_PORT=5432
      - DB_NAME=family_member_schedule
      - DB_USER=${POSTGRES_USER}
      - DB_PASSWORD=${POSTGRES_PASSWORD}
    command: ["python3", "reports/weekly_report.py"]
```

**Pattern:** Same image, different `command`. The `notion-sync` service needs `NOTION_API_KEY`; report services don't (they only read from PostgreSQL).

---

## Step 6: Create n8n Workflows for Report Automation

### 6.1 Key Design Decision: Separate Workflows Per Person

**Don't** combine both people into one workflow. Use separate workflows because:

- **Different schedules** — stagger times to avoid Docker container conflicts
- **Independent failures** — if one person's report fails, the other still sends
- **Simpler SMS routing** — each workflow sends to the right phone number
- **Easier to pause/modify** — disable one person's workflow without affecting the other

### 6.2 Daily Report Workflows

**Workflow: "First Daughter Daily Report - 7am"**
```
Schedule Trigger (7:00am AEST)
  → SSH: cd ~/YewseoYewooWeeklyReport && docker compose run --rm daily-report python3 reports/daily_report.py --child_id 2 --format json
    → Parse JSON
      → IF exitCode > 0 → SMS Error Alert to parents
      → ELSE → SMS report to First Daughter + SMS report to parents
```

**Workflow: "Second Daughter Daily Report - 7:10am"**
```
Schedule Trigger (7:10am AEST)
  → SSH: cd ~/YewseoYewooWeeklyReport && docker compose run --rm daily-report python3 reports/daily_report.py --child_id 1 --format json
    → Parse JSON
      → IF exitCode > 0 → SMS Error Alert to parents
      → ELSE → SMS report to Second Daughter + SMS report to parents
```

**Why stagger by 10 minutes?** Docker Compose can't run two instances of the same service simultaneously. If both trigger at the same time, one will fail with a container name conflict.

### 6.3 Weekly Report Workflows

**Workflow: "First Daughter Weekly Report - Sunday 9:30pm"**
```
Schedule Trigger (Sunday 9:30pm AEST)
  → SSH: docker compose run --rm weekly-report python3 reports/weekly_report.py --child_id 2 --format json
    → Parse JSON
      → IF exitCode > 0 → SMS Error Alert
      → ELSE → SMS report to First Daughter + SMS report to parents
             → Email HTML report to parents
```

**Workflow: "Second Daughter Weekly Report - Sunday 9:40pm"**
```
Schedule Trigger (Sunday 9:40pm AEST)
  → SSH: docker compose run --rm weekly-report python3 reports/weekly_report.py --child_id 1 --format json
    → Parse JSON
      → IF exitCode > 0 → SMS Error Alert
      → ELSE → SMS report to Second Daughter + SMS report to parents
             → Email HTML report to parents
```

### 6.4 Workflow Node Configuration

**SSH node:**
- Credentials: SSH key-based auth to the host running Docker
- Command: full `cd ... && docker compose run --rm ...` in one line

**IF node (error check):**
```javascript
// Check exitCode, NOT stderr
{{ $json.exitCode > 0 }}
```

**Twilio SMS node:**
- Credentials: Twilio API (configured in n8n credentials)
- From: your Twilio number (E.164 format)
- To: recipient's verified number (E.164 format)
- Message: `{{ $json.stdout }}` (or parsed JSON field)

---

## Lessons Learned

### 1. Tamper-Proof Timestamps
Use Notion's `created_time` and `last_edited_time` instead of manual date fields. Users cannot edit these system timestamps, making duration calculations trustworthy.

### 2. Per-Person Databases Beat Shared Databases
A shared database with a "Who" dropdown adds complexity (filtering, permissions, accidental edits). Separate databases are cleaner — the database ID IS the person identity.

### 3. Docker stderr Is Not an Error
Docker and Python write informational messages to stderr. **Never trigger error alerts on `stderr not empty`** — always check `exitCode > 0`. This single mistake caused weeks of false alarm alerts before we figured it out.

### 4. Separate Workflows Per Person
Combined workflows are harder to debug, modify, and schedule. One workflow per person per report type is more verbose but vastly simpler to maintain.

### 5. Stagger Scheduled Times
Docker Compose service names must be unique per running container. If two workflows trigger the same service simultaneously, one fails. Stagger by 10 minutes.

### 6. Hide System Fields from Users
The `Synced` checkbox is infrastructure — users should never see or touch it. Hide it in the Notion database view settings.

### 7. Mount Scripts, Don't Bake Them
Using `volumes: ./reports:/app/reports:ro` means you can edit Python scripts and immediately re-run without rebuilding the Docker image. Only rebuild when dependencies change.

### 8. Validate Phone Numbers Before Building Workflows
Twilio requires E.164 format (`+61412345678`) and trial accounts require recipient verification. Test SMS delivery manually before wiring it into automation — silent delivery failures waste hours of debugging.

### 9. Configure MCP Servers First
Setting up PostgreSQL and n8n MCP servers in Claude Code before starting development lets you query the database and manage workflows directly from your terminal. This eliminates context-switching and makes iterating much faster.

---

## Reproduction Checklist

To adapt this system for a new project (e.g., wife's health improvement advisor):

### Database
- [ ] Create a new PostgreSQL database (or new tables in existing one)
- [ ] Define your enum categories (e.g., `Exercise`, `Nutrition`, `Sleep`, `Medication`)
- [ ] Create tables: people, activity types, activity_logs
- [ ] Seed reference data (people, their activity types)

### MCP Servers
- [ ] Configure PostgreSQL MCP server in Claude Code with the new database URL
- [ ] Configure n8n MCP server in Claude Code with API key
- [ ] Verify both connections work (`n8n_health_check`, test SQL query)

### Twilio
- [ ] Get Twilio Account SID, Auth Token, and phone number
- [ ] Verify all recipient phone numbers in Twilio Console (trial mode)
- [ ] Test send an SMS manually to confirm delivery
- [ ] Configure Twilio credentials in n8n

### Notion
- [ ] Create a Notion integration and get the API key
- [ ] Create one timer database **per person** (not shared)
- [ ] Set up fields: Subject (select), Done (checkbox), Created, Finished, Duration (formula), Notes, Synced (hidden checkbox)
- [ ] Populate each Subject dropdown with that person's activities
- [ ] Share databases with integration + share with users as guests

### Python Scripts
- [ ] Update `config.py`: new DB config, new Notion DB IDs, new subject/workout mappings
- [ ] Update `notion_sync.py`: adjust `parse_entry()` if categories differ
- [ ] Update `daily_report.py` / `weekly_report.py`: adjust formatting, categories, report structure
- [ ] Update `db.py` if connection pattern changes

### Docker
- [ ] Update `.env` with new credentials
- [ ] Update `docker-compose.yml`: service names, env vars, commands
- [ ] Dockerfile likely unchanged (same Python deps)
- [ ] Test: `docker compose run --rm notion-sync --dry-run`

### n8n Workflows
- [ ] Create midnight sync workflow (Schedule → SSH → Parse → Error check → SMS alert)
- [ ] Create daily report workflows — **one per person, staggered times**
- [ ] Create weekly report workflows — **one per person, staggered times**
- [ ] Set error detection to `exitCode > 0` (NOT `stderr not empty`)
- [ ] Configure SMS nodes with verified Twilio numbers (E.164 format)
- [ ] Test each workflow manually before activating schedules
