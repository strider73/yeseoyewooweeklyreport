# YewseoYewooWeeklyReport

## Project Purpose
This project is a weekly report management tool for two teenage daughters:
- **Yeseo** (예서) - 16 years old
- **Yewoo** (여우) - 15 years old

The app helps them manage and track their weekly:
- **Study** - school work, assignments, study sessions
- **Workout** - exercise routines, physical activities
- **Rest** - sleep, breaks, relaxation time

## Key Principles
- Keep the UI simple and age-appropriate for teenagers
- Weekly basis tracking and reporting
- Support both daughters independently with their own data

---

## Profiles & Goals
- **Yeseo:** [YESEO.md](YESEO.md)
- **Yewoo:** [YEWOO.md](YEWOO.md)

## Weekly Schedules
- **Full schedule patterns:** [WEEKLY_SCHEDULE.md](WEEKLY_SCHEDULE.md)

## Report Templates
- **Report format reference:** [REPORT_TEMPLATES.md](REPORT_TEMPLATES.md)

---

## Notion Timer Databases
- **Yewoo Timer:** https://www.notion.so/7b628dc68fee4d5bad66a3dbebb5560e?v=9605758247c14b619c05325286763369
  - Data source: `collection://7859aff1-b16d-4a46-b0f2-c0647f39ad63`
- **Yeseo Timer:** https://www.notion.so/9662c755a6b249f2bfa6f1392c1d9b82?v=9321dc312501406c80aa415d7c63c306
  - Data source: `collection://4c02fa6f-a9ca-4fc3-aa96-4042b71ba496`

## n8n Sync Workflow
- **Notion Timer → PostgreSQL Sync:** Workflow ID `UhVSuskgC1IyuxGZ` (runs daily at 11:50pm)

## Database
- **Database:** `family_member_schedule` on `adventuretube.net:5432`
- **Full schema reference:** [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)
- **Child IDs:** Yewoo = 1, Yeseo = 2

---

## Weekly Report Structure
Each weekly report should track actual vs planned for:
1. **Study hours** per subject
2. **Workout** sessions completed
3. **Rest** quality and hours
4. Deviations from standard schedule and reasons
