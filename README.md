# Yewoo & Yeseo Weekly Report

Activity tracking and reporting system for two teenage daughters — Yewoo (15) and Yeseo (16).

## How It Works

```
Kid's phone (Notion app)
  → Opens their timer database
  → Taps "New", picks Subject (Created time auto-stamps)
  → Studies...
  → Checks "Done" when finished (Finished time auto-stamps)
                    ↓
n8n workflow (midnight AEST daily)
  → SSHes into Pi, runs docker compose run --rm notion-sync
  → Reads Notion for completed sessions (Done=true, Synced=false)
  → Writes each session to PostgreSQL activity_logs
  → Marks Notion rows as Synced
                    ↓
Report scripts (automated via n8n)
  → daily_report.py (10pm) — SMS with trend arrows
  → weekly_report.py (Saturday 9pm) — SMS + HTML email
```

## Notion Databases

Each kid has their own timer database with tamper-proof timestamps:

| Field | Type | Purpose |
|-------|------|---------|
| Subject | select | Kid's subjects only |
| Done | checkbox | Kid checks when finished |
| Created | created_time | Auto-set, can't be edited |
| Finished | last_edited_time | Auto-set when Done is checked |
| Duration (min) | formula | Finished - Created |
| Notes | rich_text | Optional comment |
| Synced | checkbox | Hidden; set by sync script |

## Project Structure

```
├── Dockerfile              # Python 3.11-slim + deps
├── docker-compose.yml      # Mounts ./reports, passes env vars
├── reports/
│   ├── config.py           # DB config, Notion DB IDs, subject/workout mappings
│   ├── db.py               # PostgreSQL connection helper
│   ├── notion_sync.py      # Notion → PostgreSQL sync script
│   ├── daily_report.py     # Daily SMS report with 7-day averages
│   ├── weekly_report.py    # Weekly SMS + HTML email report
│   └── requirements.txt    # Python dependencies
```

## Setup

### Environment Variables

Create `.env` in the project root:

```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<password>
NOTION_API_KEY=<notion_integration_secret>
```

### Run Sync Manually

```bash
# Dry run (preview without writing)
docker compose run --rm notion-sync python3 reports/notion_sync.py --dry-run --all

# Sync today's entries
docker compose run --rm notion-sync

# Sync all unsynced entries
docker compose run --rm notion-sync python3 reports/notion_sync.py --all
```

### n8n Workflow

The workflow "Notion Timer → PostgreSQL Sync - Midnight" runs daily at 12:00am AEST:
1. SSH into Pi
2. `cd ~/YewseoYewooWeeklyReport && docker compose run --rm notion-sync`
3. On error → SMS alert

## Database

- **Host:** adventuretube.net:5432
- **Database:** family_member_schedule
- **Main table:** activity_logs (child_id, category, subject_id, workout_id, activity_date, actual_minutes)
- **Child IDs:** Yewoo = 1, Yeseo = 2
