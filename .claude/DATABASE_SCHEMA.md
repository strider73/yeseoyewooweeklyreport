# Database Schema: family_member_schedule

**Host:** adventuretube.net:5432
**Database:** family_member_schedule
**Schema:** public

---

## Tables

### 1. children
| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| child_id | integer (PK) | NO | auto-increment |
| name | varchar | NO | |
| age | integer | YES | |

**Current Data:**
| child_id | name | age |
|----------|------|-----|
| 1 | Yewoo | 15 |
| 2 | Yeseo | 16 |

---

### 2. subjects
| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| subject_id | integer (PK) | NO | auto-increment |
| child_id | integer (FK → children) | YES | |
| subject_name | varchar | NO | |
| is_academic | boolean | YES | true |

**Current Data:**

**Yewoo (child_id=1):**
| subject_id | subject_name | is_academic |
|------------|-------------|-------------|
| 35 | Maths | true |
| 36 | Chemistry | true |
| 37 | Physics | true |
| 38 | Reading | true |
| 47 | Biology | true |
| 48 | JMSS Prep | true |

**Yeseo (child_id=2):**
| subject_id | subject_name | is_academic |
|------------|-------------|-------------|
| 39 | Piano Practice | false |
| 40 | Music Theory | false |
| 41 | Music Composition | false |
| 42 | Review/Planning | true |
| 43 | Chemistry | true |
| 44 | Legal Studies | true |
| 45 | Methods | true |
| 46 | Literature | true |

---

### 3. workout_types
| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| workout_id | integer (PK) | NO | auto-increment |
| child_id | integer (FK → children) | YES | |
| workout_name | varchar | NO | |
| target_sessions_per_week | integer | YES | 0 |
| target_minutes_per_session | integer | YES | |

**Current Data:**
| workout_id | child_id | workout_name | sessions/week | min/session |
|------------|----------|-------------|---------------|-------------|
| 9 | 1 (Yewoo) | Jogging | 4 | 30 |
| 10 | 2 (Yeseo) | Jogging | 4 | 30 |
| 11 | 1 (Yewoo) | Tennis | 1 | 180 |

---

### 4. activity_logs
| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| log_id | integer (PK) | NO | auto-increment |
| child_id | integer (FK → children) | YES | |
| category | activity_category (enum) | NO | |
| subject_id | integer (FK → subjects) | YES | |
| workout_id | integer (FK → workout_types) | YES | |
| activity_date | date | NO | CURRENT_DATE |
| actual_minutes | integer | NO | |
| deviation_reason | text | YES | |
| created_at | timestamp | YES | CURRENT_TIMESTAMP |
| notion_page_id | text (UNIQUE) | YES | |

**Enum: activity_category** → `Study`, `Workout`, `Rest`, `Routine`

**Index:** `idx_activity_logs_notion_page_id` UNIQUE on `notion_page_id` (duplicate prevention for Notion sync)

---

### 5. weekly_goals
| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| goal_id | integer (PK) | NO | auto-increment |
| child_id | integer (FK → children) | YES | |
| week_start_date | date | NO | |
| target_study_hours | double precision | YES | |
| target_workout_count | integer | YES | |

---

## Relationships
- `activity_logs.child_id` → `children.child_id`
- `activity_logs.subject_id` → `subjects.subject_id`
- `activity_logs.workout_id` → `workout_types.workout_id`
- `subjects.child_id` → `children.child_id`
- `workout_types.child_id` → `children.child_id`
- `weekly_goals.child_id` → `children.child_id`
