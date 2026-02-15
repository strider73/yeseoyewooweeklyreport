# Daily Input Plan

## Goal
Provide a simple, low-friction way for Yeseo and Yewoo to submit their daily activity data into the `family_member_schedule` database so that daily and weekly reports can be generated automatically.

---

## Options Considered

### Option 1: Simple Web Form (Recommended)
- Mobile-friendly web page; each daughter bookmarks it on her phone
- Pre-populated fields based on their known subjects and workout types
- Submit in under 2 minutes
- Data writes directly to `activity_logs` table in PostgreSQL

### Option 2: Messaging Bot (Kakao/Telegram/Discord)
- A chatbot asks a few questions each evening
- Feels natural for teenagers who already use messaging apps
- Requires building and hosting a bot service

### Option 3: Google Form → Database Sync
- Quick to set up, no custom UI
- Responses go to Google Sheet, then sync to database via n8n or script
- Less polished, extra sync step

### Option 4: Notion Form/Page
- Notion MCP is already configured
- Each daughter fills in a daily template
- Data pulled into database periodically

---

## Recommendation: Option 1 — Simple Web Form

**Why this wins:**
- **Low friction for the kids** — one bookmark on their phone, tap and fill
- **Direct database integration** — no syncing or middleware needed
- **Full control** — fields match exactly what the database expects
- **Sustainable** — teenagers are more likely to stick with something simple and fast
- **Key rule:** if it takes more than 1–2 minutes, compliance drops off fast

---

## Web Form Design

### Authentication
- Simple child selection (Yeseo / Yewoo) — no login required for MVP
- Optional: PIN-based lightweight auth later

### Form Fields

#### 1. Header
- Child selector: `Yeseo` | `Yewoo`
- Date picker (defaults to today)

#### 2. Study Section
Fields are **pre-populated per child** from the `subjects` table:

**Yewoo's subjects:**
| Field | Subject ID | Input |
|-------|-----------|-------|
| Maths | 35 | minutes dropdown/input |
| Chemistry | 36 | minutes dropdown/input |
| Physics | 37 | minutes dropdown/input |
| Reading | 38 | minutes dropdown/input |
| Biology | 47 | minutes dropdown/input |
| JMSS Prep | 48 | minutes dropdown/input |

**Yeseo's subjects:**
| Field | Subject ID | Input |
|-------|-----------|-------|
| Piano Practice | 39 | minutes dropdown/input |
| Music Theory | 40 | minutes dropdown/input |
| Music Composition | 41 | minutes dropdown/input |
| Review/Planning | 42 | minutes dropdown/input |
| Chemistry | 43 | minutes dropdown/input |
| Legal Studies | 44 | minutes dropdown/input |
| Methods | 45 | minutes dropdown/input |
| Literature | 46 | minutes dropdown/input |

- Input style: quick-tap buttons (0, 30, 60, 90, 120 min) or manual entry
- Leave blank or 0 = skip (no row inserted)

#### 3. Workout Section
Pre-populated per child from `workout_types` table:

| Child | Workout | Workout ID | Input |
|-------|---------|-----------|-------|
| Yewoo | Jogging | 9 | minutes |
| Yewoo | Tennis | 11 | minutes |
| Yeseo | Jogging | 10 | minutes |

#### 4. Rest Section
- Single field: total rest/nap minutes (category = `Rest`)
- Optional: deviation reason text field

#### 5. Submit
- One button: **"Submit Today's Report"**
- Confirmation message on success
- Prevent duplicate submissions for same child + date

### Database Writes

Each non-zero entry creates one row in `activity_logs`:

```sql
INSERT INTO activity_logs (child_id, category, subject_id, workout_id, activity_date, actual_minutes, deviation_reason)
VALUES ($1, $2, $3, $4, $5, $6, $7);
```

- Study entries: `category='Study'`, `subject_id` set, `workout_id` NULL
- Workout entries: `category='Workout'`, `workout_id` set, `subject_id` NULL
- Rest entries: `category='Rest'`, both `subject_id` and `workout_id` NULL

---

## Tech Stack Options

### Option A: Static HTML + API endpoint
- Single HTML file with vanilla JS
- API endpoint (Python Flask/FastAPI or Node.js) to handle form submission
- Host on adventuretube.net alongside existing infrastructure

### Option B: Next.js / React app
- More polished UI, component-based
- Heavier setup, may be overkill for a simple form

### Option C: Python + Flask (lightweight)
- Single `app.py` serving the form and handling POST
- Uses psycopg2 to write to PostgreSQL
- Minimal dependencies, easy to deploy

**Suggested: Option A or C** — keep it simple.

---

## Integration with Existing Report Pipeline

```
Daily Input Flow:
  Kids fill form (phone) → API → activity_logs table
                                        ↓
  n8n cron (10pm AEST) → python daily_report.py → SMS to parents
  n8n cron (Sat 9pm)   → python weekly_report.py → SMS + Email to parents
```

No changes needed to the existing report scripts — they already read from `activity_logs`.

---

## Implementation Steps

1. **Design the form UI** — mobile-first HTML page
2. **Build the API endpoint** — receives form data, validates, inserts into PostgreSQL
3. **Deploy** — host on adventuretube.net
4. **Test** — both daughters submit test data, verify reports generate correctly
5. **Iterate** — adjust based on feedback (too many fields? add quick presets?)
