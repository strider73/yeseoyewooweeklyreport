import os

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "adventuretube.net"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "family_member_schedule"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

CHILDREN = {1: "Yewoo", 2: "Yeseo"}

# Max duration per session (minutes) - entries exceeding this are corrupted
MAX_DURATION = {1: 180, 2: 240}  # Yewoo: 180, Yeseo: 240
CHILDREN_KR = {1: "여우", 2: "예서"}

TIMEZONE = "Australia/Melbourne"

# Notion per-kid timer databases: child_id -> database_id
NOTION_DB_IDS = {
    1: "7b628dc68fee4d5bad66a3dbebb5560e",  # Yewoo Timer
    2: "9662c755a6b249f2bfa6f1392c1d9b82",  # Yeseo Timer
}

# Maps: child_id -> {subject_name: subject_id}
SUBJECT_IDS = {
    1: {  # Yewoo
        "Maths": 35, "Chemistry": 36, "Physics": 37,
        "Reading": 38, "Biology": 47, "JMSS Prep": 48,
        "SR": 49, "General A": 50,
    },
    2: {  # Yeseo
        "Piano Practice": 39, "Music Theory": 40, "Music Composition": 41,
        "Review/Planning": 42, "Chemistry": 43, "Legal Studies": 44,
        "Methods": 45, "Literature": 46, "VCE Music": 51,
    },
}

# Maps: child_id -> {workout_name: workout_id}
WORKOUT_IDS = {
    1: {"Jogging": 9, "Tennis": 11},   # Yewoo
    2: {"Jogging": 10},                 # Yeseo
}

# Reverse lookup: "Who" select -> child_id
CHILD_NAME_TO_ID = {"Yewoo": 1, "Yeseo": 2}

# Activity title aliases → canonical subject/workout name
# Used when Subject select is empty and we fall back to Activity title
ACTIVITY_ALIASES = {
    "Jog": "Jogging",
    "Piano": "Piano Practice",
    "Dinner": "Rest",
    "Rest": "Rest",
    "Sleep": "Rest",
    "Break": "Rest",
}
