"""
UPSC Spaced Repetition Tracker — Flask Backend
Stores all data in a local JSON file for persistence.
"""

import json
import os
import time
import math
import uuid
import threading
import base64
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import atexit

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))
from flask import (Flask, render_template, request, jsonify, send_file,
                     session, redirect, url_for)

app = Flask(__name__)

# Persistent secret key — stored in a file so sessions survive restarts
_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".flask_secret")
if os.path.exists(_SECRET_FILE):
    with open(_SECRET_FILE, "r") as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(_SECRET_FILE, "w") as f:
        f.write(app.secret_key)

# ── Authentication credentials ───────────────────────────────────────────────
AUTH_USERNAME = "kishore"
AUTH_PASSWORD_HASH = hashlib.sha256("number1##".encode()).hexdigest()


@app.before_request
def require_login():
    """Block every request unless the user is logged in (or visiting /login)."""
    allowed = ("/login", "/static/")
    if any(request.path.startswith(a) for a in allowed):
        return None
    if not session.get("logged_in"):
        return redirect(url_for("login_page"))


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_FILE = os.path.join(DATA_DIR, "tracker_data.json")
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".html", ".htm"}


# =============================================================================
#  GITHUB SYNC — persist data across Render free-tier deploys
# =============================================================================
# Set these env vars on Render:
#   GITHUB_TOKEN  — personal access token (repo scope)
#   GITHUB_REPO   — e.g. "kisho/UPSC_TRACKER"
#   GITHUB_BRANCH — default "main"

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
_GITHUB_FILE_PATH = "data/tracker_data.json"  # path inside the repo


def _gh_api(endpoint, method="GET", body=None):
    """Call GitHub REST API. Returns parsed JSON or None on failure."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "UPSC-Tracker",
    }
    data_bytes = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[GitHub Sync] API error ({method} {endpoint}): {e}")
        return None


def _gh_fetch_data():
    """Download tracker_data.json from GitHub. Returns (dict, sha) or (None, None)."""
    result = _gh_api(f"contents/{_GITHUB_FILE_PATH}?ref={GITHUB_BRANCH}")
    if not result or "content" not in result:
        return None, None
    content = base64.b64decode(result["content"]).decode("utf-8")
    return json.loads(content), result["sha"]


def _gh_push_data(data_dict):
    """Push tracker_data.json to GitHub (create or update)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    # Get current SHA (needed for update)
    existing = _gh_api(f"contents/{_GITHUB_FILE_PATH}?ref={GITHUB_BRANCH}")
    sha = existing.get("sha") if existing and "sha" in existing else None

    content_b64 = base64.b64encode(
        json.dumps(data_dict, indent=2, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    body = {
        "message": f"Auto-sync tracker data ({datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')})",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        body["sha"] = sha
    _gh_api(f"contents/{_GITHUB_FILE_PATH}", method="PUT", body=body)


_pending_push = None  # track the latest push thread

def _gh_push_async(data_dict):
    """Push to GitHub in a background thread so save_data stays fast."""
    global _pending_push
    t = threading.Thread(target=_gh_push_data, args=(data_dict,), daemon=True)
    _pending_push = t
    t.start()


@atexit.register
def _wait_for_pending_push():
    """On shutdown, wait for the last GitHub push to finish so no data is lost."""
    if _pending_push and _pending_push.is_alive():
        print("[GitHub Sync] Waiting for final push to complete...")
        _pending_push.join(timeout=20)


# =============================================================================
#  DATA LAYER
# =============================================================================

def default_data():
    return {
        "subjects": [],
        "settings": {
            "weekdayHours": 6,
            "weekendHours": 12,
            "revisionMins": 60,
            "weekendRevHrs": 3,
            "intervals": {"r1": 1, "r3": 5, "r7": 14, "r30": 35},
            "activityHours": dict(DEFAULT_ACTIVITY_HOURS),
            "ntfy": {
                "enabled": False,
                "topic": "",
                "server": "https://ntfy.sh",
            },
        },
        "completedRevisions": {},
        "completedPractice": {},
        "cumulativeRevisions": {
            "sectionalBatches": [],
            "subjectRevisions": [],
            "pendingTopics": [],
        },
        "version": 2,
    }


_first_load = True  # Track first load after process start (fresh deploy)

def load_data():
    global _first_load
    # On first load after startup, ALWAYS fetch from GitHub API.
    # This is critical because git clone brings the old committed JSON,
    # but the API has the latest data pushed by the previous instance.
    if _first_load and GITHUB_TOKEN and GITHUB_REPO:
        _first_load = False
        gh_data, _ = _gh_fetch_data()
        if gh_data and gh_data.get("subjects"):
            print("[GitHub Sync] Restored latest data from GitHub API")
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(gh_data, f, indent=2, ensure_ascii=False)
            # Fall through to normal load + migration logic below
        else:
            print("[GitHub Sync] Could not fetch from API, using local file")
    _first_load = False

    if not os.path.exists(DATA_FILE):
        data = default_data()
        save_data(data)
        return data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all keys exist
        if "settings" not in data:
            data["settings"] = default_data()["settings"]
        if "intervals" not in data["settings"]:
            data["settings"]["intervals"] = {"r1": 1, "r3": 5, "r7": 14, "r30": 35}
        if "ntfy" not in data["settings"]:
            data["settings"]["ntfy"] = {"enabled": False, "topic": "", "server": "https://ntfy.sh"}
        if "activityHours" not in data["settings"]:
            data["settings"]["activityHours"] = dict(DEFAULT_ACTIVITY_HOURS)
        else:
            # Merge with defaults to ensure all keys exist
            for k, v in DEFAULT_ACTIVITY_HOURS.items():
                if k not in data["settings"]["activityHours"]:
                    data["settings"]["activityHours"][k] = v
        if "completedRevisions" not in data:
            data["completedRevisions"] = {}
        if "completedPractice" not in data:
            data["completedPractice"] = {}
        if "cumulativeRevisions" not in data:
            data["cumulativeRevisions"] = {
                "sectionalBatches": [],
                "subjectRevisions": [],
                "pendingTopics": [],
            }
        # Auto-migrate: estimatedDays → estimatedHours
        for subj in data.get("subjects", []):
            for topic in subj.get("topics", []):
                if "estimatedHours" not in topic:
                    days = topic.get("estimatedDays", 3)
                    topic["estimatedHours"] = round(days * 2.5, 1)
        # Data integrity: fix topics with all 12 revisions done but wrong status
        _fix_mastery_status(data)
        return data
    except Exception:
        return default_data()


def _fix_mastery_status(data):
    """Auto-correct topics that have all 12 revisions done but status != mastered.
    This handles race conditions from rapid concurrent marking."""
    types = ["R1", "PYQ", "ERA", "R3", "MN", "CA", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30"]
    fixed = False
    for subj in data.get("subjects", []):
        for topic in subj.get("topics", []):
            if topic["status"] == "completed":
                all_done = all(
                    f"{topic['id']}_{t}" in data.get("completedRevisions", {})
                    for t in types
                )
                if all_done:
                    topic["status"] = "mastered"
                    # Ensure it's in pendingTopics for cumulative revision
                    cum = data.get("cumulativeRevisions", {})
                    pending = cum.get("pendingTopics", [])
                    in_pending = any(p["topicId"] == topic["id"] for p in pending)
                    in_batch = any(
                        topic["id"] in b.get("topicIds", [])
                        for b in cum.get("sectionalBatches", [])
                    )
                    if not in_pending and not in_batch:
                        pending.append({
                            "topicId": topic["id"],
                            "topicName": topic["name"],
                            "subjectId": subj["id"],
                            "subjectName": subj["name"],
                            "roi": topic.get("roi", "medium"),
                            "masteredAt": today_str(),
                        })
                    fixed = True
    if fixed:
        save_data(data)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Push to GitHub in background so live progress survives redeploys
    _gh_push_async(data)


def gen_id():
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


# =============================================================================
#  UTILITY HELPERS
# =============================================================================

def today_str():
    return datetime.now(IST).strftime("%Y-%m-%d")


def add_days(date_str, days):
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def get_next_sunday(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    dow = d.weekday()  # Monday=0, Sunday=6
    if dow == 6:
        return date_str
    days_until_sunday = 6 - dow
    d += timedelta(days=days_until_sunday)
    return d.strftime("%Y-%m-%d")


def is_weekend(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.weekday() in (5, 6)  # Sat=5, Sun=6


def get_next_saturday(date_str):
    """Get the next Saturday on or after the given date."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    dow = d.weekday()  # Monday=0, Sunday=6
    if dow == 5:  # Already Saturday
        return date_str
    days_until_sat = (5 - dow) % 7
    if days_until_sat == 0:
        days_until_sat = 7
    d += timedelta(days=days_until_sat)
    return d.strftime("%Y-%m-%d")


# =============================================================================
#  CUMULATIVE REVISION — SCIENTIFIC SCHEDULING
# =============================================================================
# Based on Ebbinghaus forgetting curve + spacing effect + interleaving:
#
# SECTIONAL BATCHES (5-10 mastered topics, cross-subject):
#   Round 1: Next weekend after batch forms (~7 days) — initial consolidation
#   Round 2: 3 weeks after Round 1 (21 days) — intermediate spacing
#   Round 3: 8 weeks after Round 2 (56 days) — long-term consolidation
#
# SUBJECT-LEVEL REVISIONS (all very-high+high+med ROI topics mastered in a subject):
#   Round 1: 2 weeks after trigger (14 days)
#   Round 2: 6 weeks after trigger (42 days)
#   Round 3: 14 weeks after trigger (98 days)
#   Round 4: 24 weeks after trigger (168 days)
#
# All sessions are scheduled on Saturdays (start of weekend) for 2-day blocks.

SECTIONAL_INTERVALS = [0, 21, 56]  # days after previous round
SUBJECT_INTERVALS = [14, 42, 98, 168]  # days after trigger date
MIN_BATCH_SIZE = 5
MAX_BATCH_SIZE = 10
MAX_CUM_SESSIONS_PER_WEEKEND = 1  # max cumulative sessions on a single weekend
CUM_SESSION_HOURS = 3  # assumed hours per cumulative session
MAX_WEEKEND_CUM_HOURS = 6  # hard cap for cumulative work on any weekend


def get_occupied_weekends(data):
    """Return dict of Saturday-date → count of incomplete cumulative sessions."""
    occupied = {}
    cum = data.get("cumulativeRevisions", {})
    for batch in cum.get("sectionalBatches", []):
        for sess in batch.get("sessions", []):
            if not sess["completed"]:
                d = sess["scheduledDate"]
                occupied[d] = occupied.get(d, 0) + 1
    for sr in cum.get("subjectRevisions", []):
        for sess in sr.get("sessions", []):
            if not sess["completed"]:
                d = sess["scheduledDate"]
                occupied[d] = occupied.get(d, 0) + 1
    return occupied


def find_available_weekend(base_date, occupied, max_per_weekend=MAX_CUM_SESSIONS_PER_WEEKEND):
    """Find the earliest Saturday on/after base_date that isn't fully booked."""
    candidate = get_next_saturday(base_date)
    # Search up to 52 weeks ahead
    for _ in range(52):
        if occupied.get(candidate, 0) < max_per_weekend:
            return candidate
        candidate = get_next_saturday(add_days(candidate, 7))
    return candidate  # fallback


def schedule_sectional_batch(batch_creation_date, topics_info, occupied=None):
    """Create a sectional batch with scientifically spaced weekend sessions.
    Respects occupied weekends to avoid overloading."""
    if occupied is None:
        occupied = {}
    sessions = []
    # Round 1: next available weekend
    r1_base = add_days(batch_creation_date, 1)
    r1_date = find_available_weekend(r1_base, occupied)
    occupied[r1_date] = occupied.get(r1_date, 0) + 1
    sessions.append({
        "round": 1,
        "scheduledDate": r1_date,
        "completed": False,
        "completedAt": None,
    })
    # Round 2: 3 weeks after round 1
    r2_base = add_days(r1_date, SECTIONAL_INTERVALS[1])
    r2_date = find_available_weekend(r2_base, occupied)
    occupied[r2_date] = occupied.get(r2_date, 0) + 1
    sessions.append({
        "round": 2,
        "scheduledDate": r2_date,
        "completed": False,
        "completedAt": None,
    })
    # Round 3: 8 weeks after round 2
    r3_base = add_days(r2_date, SECTIONAL_INTERVALS[2])
    r3_date = find_available_weekend(r3_base, occupied)
    occupied[r3_date] = occupied.get(r3_date, 0) + 1
    sessions.append({
        "round": 3,
        "scheduledDate": r3_date,
        "completed": False,
        "completedAt": None,
    })
    return {
        "id": gen_id(),
        "topicIds": [t["topicId"] for t in topics_info],
        "topicDetails": topics_info,
        "createdAt": batch_creation_date,
        "sessions": sessions,
    }


def schedule_subject_revision(subject_id, subject_name, trigger_date, occupied=None):
    """Create subject-level revision sessions with expanding intervals.
    Avoids weekends already booked by other sessions."""
    if occupied is None:
        occupied = {}
    sessions = []
    for i, days_after in enumerate(SUBJECT_INTERVALS):
        base_date = add_days(trigger_date, days_after)
        sched_date = find_available_weekend(base_date, occupied)
        occupied[sched_date] = occupied.get(sched_date, 0) + 1
        sessions.append({
            "round": i + 1,
            "scheduledDate": sched_date,
            "completed": False,
            "completedAt": None,
        })
    return {
        "subjectId": subject_id,
        "subjectName": subject_name,
        "triggeredAt": trigger_date,
        "sessions": sessions,
    }


def check_and_create_batches(data):
    """Check if pending mastered topics can form a sectional batch.
    Auto-creates batches when >= MIN_BATCH_SIZE topics are pending.
    Also checks for subject-level revision triggers.
    Respects weekend capacity limits — max 1 cumulative session per weekend.
    Returns True if any changes were made."""
    changed = False
    cum = data["cumulativeRevisions"]
    pending = cum["pendingTopics"]

    # Build a map of already-occupied weekends
    occupied = get_occupied_weekends(data)

    # Auto-batch when enough topics accumulate
    while len(pending) >= MIN_BATCH_SIZE:
        batch_size = min(len(pending), MAX_BATCH_SIZE)
        batch_topics = pending[:batch_size]
        cum["pendingTopics"] = pending[batch_size:]
        pending = cum["pendingTopics"]

        batch = schedule_sectional_batch(today_str(), batch_topics, occupied)
        cum["sectionalBatches"].append(batch)
        changed = True

        # Notify
        topic_names = [t["topicName"] for t in batch_topics]
        send_ntfy(
            "Sectional Revision Batch Created!",
            f"A new batch of {len(batch_topics)} mastered topics\n"
            f"is ready for cumulative revision!\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Topics: {', '.join(topic_names[:5])}{'...' if len(topic_names) > 5 else ''}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Sessions scheduled for weekends:\n"
            + '\n'.join(f"  Round {s['round']}: {s['scheduledDate']}" for s in batch["sessions"])
            + f"\n━━━━━━━━━━━━━━━━━━\n"
            f"Interleaved cross-topic review!",
            tags=["brain", "calendar"],
            priority=4,
        )

    # Check subject-level triggers
    for subj in data["subjects"]:
        # Skip if already has a subject revision
        existing = [sr for sr in cum["subjectRevisions"] if sr["subjectId"] == subj["id"]]
        if existing:
            continue

        # Check if all very-high+high+medium ROI topics are mastered
        hm_topics = [t for t in subj["topics"] if t.get("roi") in ("very-high", "high", "medium")]
        if len(hm_topics) == 0:
            continue
        all_mastered = all(t["status"] == "mastered" for t in hm_topics)
        if all_mastered:
            sr = schedule_subject_revision(subj["id"], subj["name"], today_str(), occupied)
            cum["subjectRevisions"].append(sr)
            changed = True

            send_ntfy(
                f"Subject Revision Triggered: {subj['name']}!",
                f"All VERY HIGH + HIGH + MEDIUM ROI topics in {subj['name']}\n"
                f"are now MASTERED!\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Full subject revision sessions scheduled:\n"
                + '\n'.join(f"  Round {s['round']}: {s['scheduledDate']}" for s in sr["sessions"])
                + f"\n━━━━━━━━━━━━━━━━━━\n"
                f"Deep consolidation of entire subject!",
                tags=["trophy", "calendar", "star"],
                priority=5,
                subject_topic=subj.get("ntfyTopic") or None,
            )

    return changed


def reschedule_conflicting_sessions(data):
    """Deconflict all cumulative sessions so no weekend has > MAX_CUM_SESSIONS_PER_WEEKEND.
    Preserves completed sessions and only moves incomplete ones."""
    cum = data["cumulativeRevisions"]

    # Collect all incomplete sessions with references
    all_sessions = []
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if not sess["completed"]:
                all_sessions.append({
                    "session": sess,
                    "type": "sectional",
                    "label": f"Batch {batch['id'][:6]} R{sess['round']}",
                })
    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if not sess["completed"]:
                all_sessions.append({
                    "session": sess,
                    "type": "subject",
                    "label": f"{sr['subjectName']} R{sess['round']}",
                })

    # Sort by current scheduled date
    all_sessions.sort(key=lambda x: x["session"]["scheduledDate"])

    # Rebuild occupied map from completed sessions only
    occupied = {}
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if sess["completed"]:
                d = sess["scheduledDate"]
                occupied[d] = occupied.get(d, 0) + 1
    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if sess["completed"]:
                d = sess["scheduledDate"]
                occupied[d] = occupied.get(d, 0) + 1

    # Reassign each incomplete session to the nearest available weekend
    for entry in all_sessions:
        sess = entry["session"]
        base_date = sess["scheduledDate"]  # keep near the originally intended date
        new_date = find_available_weekend(base_date, occupied)
        sess["scheduledDate"] = new_date
        occupied[new_date] = occupied.get(new_date, 0) + 1

    save_data(data)


def add_topic_to_pending(data, topic_id, topic_name, subj_id, subj_name, roi):
    """Add a mastered topic to the pending pool for cumulative revision."""
    cum = data["cumulativeRevisions"]
    # Avoid duplicates
    if any(p["topicId"] == topic_id for p in cum["pendingTopics"]):
        return
    # Also avoid if already in a batch
    for batch in cum["sectionalBatches"]:
        if topic_id in batch["topicIds"]:
            return

    cum["pendingTopics"].append({
        "topicId": topic_id,
        "topicName": topic_name,
        "subjectId": subj_id,
        "subjectName": subj_name,
        "roi": roi,
        "masteredAt": today_str(),
    })


# =============================================================================
#  NTFY NOTIFICATION HELPER
# =============================================================================

def send_ntfy(title, message, tags=None, priority=3, click=None, subject_topic=None):
    """Send a push notification via ntfy.sh (non-blocking).
    
    If subject_topic is provided AND non-empty, sends to that topic instead
    of the global one. Falls back to global topic if subject_topic is empty.
    """
    data = load_data()
    ntfy_cfg = data.get("settings", {}).get("ntfy", {})
    if not ntfy_cfg.get("enabled"):
        return

    server = ntfy_cfg.get("server", "https://ntfy.sh").rstrip("/")
    
    # Determine which topic to send to
    topic = subject_topic if subject_topic else ntfy_cfg.get("topic", "")
    if not topic:
        return

    url = f"{server}/{topic}"

    def _send():
        try:
            headers = {
                "Title": title.encode("utf-8"),
                "Priority": str(priority),
            }
            if tags:
                headers["Tags"] = ",".join(tags)
            if click:
                headers["Click"] = click

            req = urllib.request.Request(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[ntfy] Failed to send notification: {e}")

    threading.Thread(target=_send, daemon=True).start()


def check_topic_mastery(data, topic_id):
    """Check if all 12 revision stages are done for a topic → mastered!"""
    types = ["R1", "PYQ", "ERA", "R3", "MN", "CA", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30"]
    all_done = all(f"{topic_id}_{t}" in data["completedRevisions"] for t in types)
    return all_done


# =============================================================================
#  PROGRESSIVE TIME ESTIMATOR
# =============================================================================

MAX_PARALLEL_TOPICS = 2  # Max topics being learned simultaneously

# =============================================================================
#  ACTIVITY DURATION DEFAULTS (hours)
# =============================================================================
DEFAULT_ACTIVITY_HOURS = {
    "R1": 1.5,                # 1st Revision (Recall)
    "PYQ": 1.0,               # PYQ Practice
    "ERA": 1.0,               # Error Analysis
    "R3": 1.0,                # 2nd Revision (Active Recall)
    "MN": 1.0,                # Micro Note Making
    "CA": 1.0,                # Current Affairs + Mapping
    "MCQ": 0.5,               # MCQ Practice (30 min)
    "MCQA": 0.5,              # MCQ Analysis (30 min)
    "R7": 1.5,                # 3rd Revision (Consolidation)
    "MVA": 1.0,               # Mains Value Addition
    "MAINS": 1.5,             # Mains Answer Writing
    "R30": 1.0,               # Final Revision
    "sectionalBatch": 12,     # 1 full weekend (Sat+Sun)
    "subjectRevision": 24,    # 2 full weekends
}


def get_activity_hours(settings):
    """Get activity duration map, merging user settings with defaults."""
    return {**DEFAULT_ACTIVITY_HOURS, **settings.get("activityHours", {})}


def day_diff(d1_str, d2_str):
    """Return integer days between two YYYY-MM-DD strings (d2 - d1)."""
    dt1 = datetime.strptime(d1_str, "%Y-%m-%d")
    dt2 = datetime.strptime(d2_str, "%Y-%m-%d")
    return (dt2 - dt1).days


def _simulate_learning_for_date(data, target_date, resolved_schedules=None):
    """Simulate day-by-day learning allocation up to target_date.

    Learning topics consume ALL available budget (after non-learning tasks),
    distributed proportionally by remaining hours.  Topics finish as fast as
    the daily budget allows — no artificial 2.5 h/day cap.

    Returns {topicId: {"hours": float, "topicId", "topicName", "subjectName",
                        "subjectId", "remaining": float}}
    """
    settings = data["settings"]
    act_hrs = get_activity_hours(settings)
    wkday_budget = settings.get("weekdayHours", 6)
    wkend_budget = settings.get("weekendHours", 12)
    today = today_str()

    if resolved_schedules is None:
        resolved_schedules, _ = resolve_all_revision_schedules(data)

    # --- Pre-build non-learning demand map (date → hours) ---------------
    non_learn_map = {}
    completed_revs = data.get("completedRevisions", {})
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] not in ("completed", "mastered"):
                continue
            sched = resolved_schedules.get(topic["id"])
            if not sched:
                continue
            for _key, rev in sched.items():
                d = rev["date"]
                rev_key = f"{topic['id']}_{rev['type']}"
                if rev_key not in completed_revs:
                    non_learn_map[d] = non_learn_map.get(d, 0) + act_hrs.get(rev["type"], 1.0)

    cum = data.get("cumulativeRevisions", {})
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if sess["completed"]:
                continue
            sat = sess["scheduledDate"]
            batch_day_hrs = act_hrs.get("sectionalBatch", 12) / 2
            for d in (sat, add_days(sat, 1)):
                non_learn_map[d] = non_learn_map.get(d, 0) + batch_day_hrs
    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if sess["completed"]:
                continue
            sat = sess["scheduledDate"]
            subj_day_hrs = act_hrs.get("subjectRevision", 24) / 4
            for d in (sat, add_days(sat, 1), add_days(sat, 7), add_days(sat, 8)):
                non_learn_map[d] = non_learn_map.get(d, 0) + subj_day_hrs

    # --- Collect learning topics ----------------------------------------
    learning_items = []
    earliest_start = None
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] != "learning":
                continue
            start = topic.get("startDate") or today
            learning_items.append({
                "topicId": topic["id"],
                "topicName": topic["name"],
                "subjectName": subj["name"],
                "subjectId": subj["id"],
                "start": start,
                "remaining": topic.get("estimatedHours", 7.5),
            })
            if earliest_start is None or start < earliest_start:
                earliest_start = start

    if not learning_items or earliest_start > target_date:
        return {}

    # --- Day-by-day simulation ------------------------------------------
    allocations = {}
    current = earliest_start
    for _ in range(365):                     # safety cap
        if current > target_date:
            break

        budget = wkend_budget if is_weekend(current) else wkday_budget
        non_learn = non_learn_map.get(current, 0)
        available = max(0, budget - non_learn)

        active = [lt for lt in learning_items
                  if lt["start"] <= current and lt["remaining"] > 0.01]
        if not active:
            current = add_days(current, 1)
            continue

        total_remaining = sum(lt["remaining"] for lt in active)
        to_allocate = min(available, total_remaining)

        if to_allocate > 0.01:
            for lt in active:
                share = (lt["remaining"] / total_remaining) * to_allocate
                lt["remaining"] = round(lt["remaining"] - share, 2)
                if current == target_date:
                    allocations[lt["topicId"]] = {
                        "hours": round(share, 1),
                        "topicId": lt["topicId"],
                        "topicName": lt["topicName"],
                        "subjectName": lt["subjectName"],
                        "subjectId": lt["subjectId"],
                        "remaining": round(lt["remaining"], 1),
                    }

        current = add_days(current, 1)

    return allocations


def compute_daily_load(data, date_str, include_overdue=False, resolved_schedules=None):
    """Compute all scheduled activities and total hours for a given date.

    Uses priority-based budget allocation:
      Revision (R1>R3>R7>R30) > Learning > MN > MCQ,PYQ,ERA,MCQA,CA > MVA,MAINS > Cumulative
    Items that don't fit the daily budget are marked as spillover.
    """
    # Priority map: lower number = higher priority = stays on today
    ACTIVITY_PRIORITY = {
        "R1": 10, "R3": 11, "R7": 12, "R30": 13,
        "learning": 20,
        "MN": 30,
        "PYQ": 40, "ERA": 40, "MCQ": 40, "MCQA": 40, "CA": 40,
        "MVA": 50, "MAINS": 50,
        "cumulative_sectional": 60, "cumulative_subject": 60,
    }

    settings = data["settings"]
    act_hrs = get_activity_hours(settings)
    wknd = is_weekend(date_str)
    budget = settings.get("weekendHours", 12) if wknd else settings.get("weekdayHours", 6)
    today = today_str()

    if resolved_schedules is None:
        resolved_schedules, _ = resolve_all_revision_schedules(data)

    done_activities = []    # completed revisions (display only, no budget)
    pending_demands = []    # all uncompleted items with full hours + priority

    # ── 1. Revision tasks from completed/mastered topics ────────────────
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] not in ("completed", "mastered"):
                continue
            if not topic.get("completionDate"):
                continue
            schedule = resolved_schedules.get(topic["id"])
            if not schedule:
                continue
            for key, rev in schedule.items():
                target_date = rev["date"]
                rev_key = f"{topic['id']}_{rev['type']}"
                done = rev_key in data["completedRevisions"]

                is_overdue = target_date < today and not done
                show = (target_date == date_str) or (
                    include_overdue and date_str == today and is_overdue
                )
                if not show:
                    continue

                hrs = act_hrs.get(rev["type"], 1.0)
                item = {
                    "category": "revision",
                    "revType": rev["type"],
                    "topicId": topic["id"],
                    "topicName": topic["name"],
                    "subjectName": subj["name"],
                    "hours": hrs,
                    "done": done,
                    "overdue": is_overdue,
                    "priority": ACTIVITY_PRIORITY.get(rev["type"], 50),
                }
                if done:
                    done_activities.append(item)
                else:
                    pending_demands.append(item)

    # ── 2. Learning activities (topics currently in learning status) ────
    #    Simulates day-by-day from start dates so ALL free budget goes to
    #    learning, distributed proportionally by remaining hours.
    learning_allocs = _simulate_learning_for_date(data, date_str, resolved_schedules)
    for alloc in learning_allocs.values():
        pending_demands.append({
            "category": "learning",
            "topicId": alloc["topicId"],
            "topicName": alloc["topicName"],
            "subjectName": alloc["subjectName"],
            "hours": alloc["hours"],
            "done": False,
            "priority": ACTIVITY_PRIORITY["learning"],
        })

    # ── 3. Cumulative sessions ──────────────────────────────────────────
    cum = data.get("cumulativeRevisions", {})
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if sess["completed"]:
                continue
            sat = sess["scheduledDate"]
            sun = add_days(sat, 1)
            batch_day_hrs = act_hrs.get("sectionalBatch", 12) / 2
            if date_str in (sat, sun):
                pending_demands.append({
                    "category": "cumulative_sectional",
                    "batchId": batch["id"],
                    "round": sess["round"],
                    "topicCount": len(batch.get("topicIds", [])),
                    "hours": batch_day_hrs,
                    "done": False,
                    "priority": ACTIVITY_PRIORITY["cumulative_sectional"],
                })

    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if sess["completed"]:
                continue
            sat = sess["scheduledDate"]
            sun = add_days(sat, 1)
            subj_day_hrs = act_hrs.get("subjectRevision", 24) / 4
            sat2 = add_days(sat, 7)
            sun2 = add_days(sat, 8)
            if date_str in (sat, sun, sat2, sun2):
                pending_demands.append({
                    "category": "cumulative_subject",
                    "subjectId": sr["subjectId"],
                    "subjectName": sr["subjectName"],
                    "round": sess["round"],
                    "hours": subj_day_hrs,
                    "done": False,
                    "priority": ACTIVITY_PRIORITY["cumulative_subject"],
                })

    # ── 4. Priority-based budget allocation ─────────────────────────────
    pending_demands.sort(key=lambda a: a["priority"])

    activities = list(done_activities)   # done items always appear (display only)
    total_hours = 0.0
    spillover_hours = 0.0
    total_demand = round(sum(a["hours"] for a in pending_demands), 1)
    spillover_items = []   # items (or partial) that didn't fit

    for item in pending_demands:
        if total_hours + item["hours"] <= budget + 0.01:
            # Fits entirely
            activities.append(item)
            total_hours += item["hours"]
        elif total_hours < budget:
            # Partially fits — split: today gets what fits, rest spills
            fits = round(budget - total_hours, 1)
            spills = round(item["hours"] - fits, 1)
            today_item = dict(item, hours=fits)
            activities.append(today_item)
            total_hours += fits
            spillover_hours += spills
            spill_label = item.get("revType") or item["category"]
            spillover_items.append({"label": spill_label, "hours": spills})
        else:
            # Doesn't fit at all — full spillover
            spillover_hours += item["hours"]
            spill_label = item.get("revType") or item["category"]
            spillover_items.append({"label": spill_label, "hours": item["hours"]})

    total_hours = round(total_hours, 1)
    spillover_hours = round(spillover_hours, 1)
    rev_hrs = round(sum(a["hours"] for a in activities if a["category"] == "revision" and not a["done"]), 1)
    learn_hrs = round(sum(a["hours"] for a in activities if a["category"] == "learning"), 1)
    cum_hrs = round(sum(a["hours"] for a in activities if a["category"].startswith("cumulative")), 1)
    return {
        "date": date_str,
        "isWeekend": wknd,
        "budget": budget,
        "totalHours": total_hours,
        "totalDemand": total_demand,
        "remaining": round(max(0, budget - total_hours), 1),
        "overloaded": total_demand > budget,
        "overloadHours": round(max(0, total_demand - budget), 1),
        "spilloverHours": spillover_hours,
        "spilloverItems": spillover_items,
        "activities": activities,
        "utilization": round(min(100, total_hours / budget * 100)) if budget > 0 else 0,
        "revisionHours": rev_hrs,
        "learningHours": learn_hrs,
        "cumulativeHours": cum_hrs,
    }


def build_daily_schedule(data, days_ahead=14):
    """Build a time-budget schedule for the next N days."""
    today = today_str()
    resolved, _ = resolve_all_revision_schedules(data)
    schedule = []
    for i in range(days_ahead):
        d = add_days(today, i)
        load = compute_daily_load(data, d, include_overdue=(i == 0),
                                  resolved_schedules=resolved)
        schedule.append(load)
    return schedule


def estimate_all_timelines(data):
    """Capacity-aware timeline estimator.

    Simulates day-by-day scheduling considering:
    - Time budgets: weekday (6h) vs weekend (12h)
    - Activity durations: each revision type has a specific hour cost
    - Revision load: already-completed topics create fixed revision obligations
    - Learning capacity: only learns when daily budget has room after revisions
    - Spillover: if a day is full, learning spills to next day
    - Weekend utilization: free weekend hours used for extra learning

    Returns estimated dates for all topics through the full pipeline.
    """
    today = today_str()
    settings = data["settings"]
    intervals = settings["intervals"]
    act_hrs = get_activity_hours(settings)
    weekday_budget = settings.get("weekdayHours", 6)
    weekend_budget = settings.get("weekendHours", 12)
    roi_order = {"very-high": 0, "high": 1, "medium": 2, "low": 3}

    # ── Collect all topics ────────────────────────────────────────────────
    all_topics = []
    insertion_idx = 0
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            all_topics.append({
                "id": topic["id"],
                "name": topic["name"],
                "status": topic["status"],
                "roi": topic.get("roi", "medium"),
                "estimatedHours": topic.get("estimatedHours", 7.5),
                "startDate": topic.get("startDate"),
                "completionDate": topic.get("completionDate"),
                "subjectId": subj["id"],
                "subjectName": subj["name"],
                "subjectColor": subj["color"],
                "insertionOrder": insertion_idx,
            })
            insertion_idx += 1

    # ── Step 1 + 2: Completed/Mastered — budget-aware scheduling ────────
    # Use the shared dynamic resolver so cross-topic stacking respects
    # daily hour caps. Also produces the daily_used map for simulation.
    resolved_schedules, daily_used = resolve_all_revision_schedules(data)

    estimates = {}
    for t in all_topics:
        if t["status"] in ("completed", "mastered") and t["completionDate"]:
            schedule = resolved_schedules.get(t["id"])
            if not schedule:
                continue
            mastery_date = schedule["r30"]["date"]
            done_count = sum(
                1 for tp in ["R1", "PYQ", "ERA", "R3", "MN", "CA", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30"]
                if f"{t['id']}_{tp}" in data["completedRevisions"]
            )
            estimates[t["id"]] = {
                "topicName": t["name"],
                "subjectName": t["subjectName"],
                "subjectColor": t["subjectColor"],
                "roi": t["roi"],
                "startDate": t["startDate"],
                "completionDate": t["completionDate"],
                "masteryDate": mastery_date,
                "revisionSchedule": {k: v["date"] for k, v in schedule.items()},
                "doneRevisions": done_count,
                "status": t["status"],
                "isEstimate": False,
            }

    # Add cumulative session loads to daily_used
    cum = data.get("cumulativeRevisions", {})
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if not sess["completed"]:
                sat = sess["scheduledDate"]
                sun = add_days(sat, 1)
                per_day = act_hrs.get("sectionalBatch", 12) / 2
                daily_used[sat] = daily_used.get(sat, 0) + per_day
                daily_used[sun] = daily_used.get(sun, 0) + per_day
    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if not sess["completed"]:
                sat = sess["scheduledDate"]
                sun = add_days(sat, 1)
                per_day = act_hrs.get("subjectRevision", 24) / 4
                for d in [sat, sun, add_days(sat, 7), add_days(sat, 8)]:
                    daily_used[d] = daily_used.get(d, 0) + per_day

    # ── Step 3: Prepare learning & not-started queues ────────────────────

    # Currently learning topics
    active_learning = []
    for t in all_topics:
        if t["status"] == "learning":
            start = t["startDate"] or today
            days_elapsed = max(0, day_diff(start, today))
            # Estimate hours already spent: ~2.5h per elapsed day (rough)
            hours_spent = days_elapsed * 2.5
            remaining_hrs = max(0, t["estimatedHours"] - hours_spent)
            done_count = sum(
                1 for tp in ["R1", "PYQ", "ERA", "R3", "MN", "CA", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30"]
                if f"{t['id']}_{tp}" in data["completedRevisions"]
            )
            active_learning.append({
                "id": t["id"], "name": t["name"],
                "subjectId": t["subjectId"], "subjectName": t["subjectName"],
                "subjectColor": t["subjectColor"], "roi": t["roi"],
                "estimatedHours": t["estimatedHours"],
                "startDate": start, "remainingHours": remaining_hrs,
                "doneRevisions": done_count,
            })

    # Not-started topics sorted by ROI then insertion order (addition order)
    waiting_queue = sorted(
        [t for t in all_topics if t["status"] == "not-started"],
        key=lambda t: (roi_order.get(t["roi"], 2), t["insertionOrder"]),
    )
    # Track queue position and original status
    queue_positions = {}
    original_status = {}  # track real status for not-started topics
    for idx, t in enumerate(waiting_queue):
        queue_positions[t["id"]] = idx + 1
        original_status[t["id"]] = "not-started"

    # ── Step 4: Day-by-day simulation ────────────────────────────────────
    max_days = 400  # simulate up to ~13 months
    completed_ids = set()

    for day_offset in range(max_days):
        current_date = add_days(today, day_offset)
        wknd = is_weekend(current_date)
        budget = weekend_budget if wknd else weekday_budget

        # Total revision load for this day (dynamic scheduler keeps daily_used current)
        rev_load = daily_used.get(current_date, 0)

        # Available hours for learning after revisions
        available = max(0, budget - rev_load)

        # Advance active learning topics (priority: existing learners first)
        newly_completed = []
        for lt in active_learning:
            if lt["remainingHours"] <= 0:
                continue
            # Spend as much available time as possible on this topic
            spend = min(available, lt["remainingHours"])
            if spend <= 0:
                continue
            lt["remainingHours"] = round(lt["remainingHours"] - spend, 1)
            available = round(available - spend, 1)

            if lt["remainingHours"] <= 0:
                    # Topic completes — dynamically pack revisions into budget
                    completion_date = current_date
                    schedule = calculate_revision_schedule_dynamic(
                        completion_date, intervals, act_hrs,
                        daily_used, weekday_budget, weekend_budget,
                    )
                    mastery_date = schedule["r30"]["date"]

                    estimates[lt["id"]] = {
                        "topicName": lt["name"],
                        "subjectName": lt["subjectName"],
                        "subjectColor": lt["subjectColor"],
                        "roi": lt["roi"],
                        "startDate": lt["startDate"],
                        "completionDate": completion_date,
                        "masteryDate": mastery_date,
                        "revisionSchedule": {k: v["date"] for k, v in schedule.items()},
                        "doneRevisions": lt.get("doneRevisions", 0),
                        "status": original_status.get(lt["id"], lt.get("actualStatus", "learning")),
                        "isEstimate": True,
                        "queuePosition": queue_positions.get(lt["id"], 0),
                    }
                    newly_completed.append(lt["id"])
                    completed_ids.add(lt["id"])

        # Remove completed from active learning
        active_learning = [lt for lt in active_learning if lt["id"] not in completed_ids]

        # Start new topics from waiting queue
        while (len(active_learning) < MAX_PARALLEL_TOPICS
               and waiting_queue
               and available > 0):
            new_t = waiting_queue.pop(0)
            est_hrs = new_t.get("estimatedHours", 7.5)
            lt = {
                "id": new_t["id"], "name": new_t["name"],
                "subjectId": new_t["subjectId"], "subjectName": new_t["subjectName"],
                "subjectColor": new_t["subjectColor"], "roi": new_t["roi"],
                "estimatedHours": est_hrs,
                "startDate": current_date,
                "remainingHours": est_hrs,
                "doneRevisions": 0,
                "actualStatus": "not-started",
            }

            # Deduct first session of learning
            spend = min(available, lt["remainingHours"])
            lt["remainingHours"] = round(lt["remainingHours"] - spend, 1)
            available = round(available - spend, 1)

            if lt["remainingHours"] <= 0:
                # Completes same day (1-day topic)
                completion_date = current_date
                schedule = calculate_revision_schedule_dynamic(
                    completion_date, intervals, act_hrs,
                    daily_used, weekday_budget, weekend_budget,
                )
                mains_date = schedule["r30"]["date"]

                estimates[lt["id"]] = {
                    "topicName": lt["name"],
                    "subjectName": lt["subjectName"],
                    "subjectColor": lt["subjectColor"],
                    "roi": lt["roi"],
                    "startDate": current_date,
                    "completionDate": current_date,
                    "masteryDate": mains_date,
                    "revisionSchedule": {k: v["date"] for k, v in schedule.items()},
                    "doneRevisions": 0,
                    "status": "not-started",
                    "isEstimate": True,
                    "queuePosition": queue_positions.get(lt["id"], 0),
                }
                completed_ids.add(lt["id"])
            else:
                active_learning.append(lt)

        # Exit early if everything is done
        if not active_learning and not waiting_queue:
            break

    # Handle any topics still in active learning (didn't complete in simulation window)
    for lt in active_learning:
        if lt["id"] not in estimates:
            # Rough estimate: remaining hours / 2.5h per day
            est_days_left = int(lt["remainingHours"] / 2.5) + 1
            est_completion = add_days(today, est_days_left + max_days)
            schedule = calculate_revision_schedule(est_completion, intervals)
            estimates[lt["id"]] = {
                "topicName": lt["name"],
                "subjectName": lt["subjectName"],
                "subjectColor": lt["subjectColor"],
                "roi": lt["roi"],
                "startDate": lt["startDate"],
                "completionDate": est_completion,
                "masteryDate": schedule["r30"]["date"],
                "revisionSchedule": {k: v["date"] for k, v in schedule.items()},
                "doneRevisions": lt.get("doneRevisions", 0),
                "status": original_status.get(lt["id"], lt.get("actualStatus", "learning")),
                "isEstimate": True,
                "queuePosition": queue_positions.get(lt["id"], 0),
            }

    # Handle remaining queued topics
    for idx, t in enumerate(waiting_queue):
        if t["id"] not in estimates:
            estimates[t["id"]] = {
                "topicName": t["name"],
                "subjectName": t["subjectName"],
                "subjectColor": t["subjectColor"],
                "roi": t["roi"],
                "startDate": None,
                "completionDate": None,
                "masteryDate": None,
                "revisionSchedule": {},
                "doneRevisions": 0,
                "status": "not-started",
                "isEstimate": True,
                "queuePosition": queue_positions.get(t["id"], 0),
            }

    # ── Summary stats ────────────────────────────────────────────────────
    all_mastery_dates = [e["masteryDate"] for e in estimates.values() if e.get("masteryDate")]
    overall_finish = max(all_mastery_dates) if all_mastery_dates else None
    total_not_started = sum(1 for t in all_topics if t["status"] == "not-started")
    total_learning = sum(1 for t in all_topics if t["status"] == "learning")
    total_pipeline = total_not_started + total_learning

    return {
        "estimates": estimates,
        "summary": {
            "totalTopics": len(all_topics),
            "inPipeline": total_pipeline,
            "notStarted": total_not_started,
            "learning": total_learning,
            "overallFinishDate": overall_finish,
            "parallelSlots": MAX_PARALLEL_TOPICS,
        },
    }


def find_topic_info(data, topic_id):
    """Find topic name, subject name, and subject ntfy topic by topic ID."""
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["id"] == topic_id:
                return topic["name"], subj["name"], subj.get("ntfyTopic", "")
    return "Unknown", "Unknown", ""


def calculate_revision_schedule(completion_date, intervals):
    """Static single-topic preview schedule (used for ntfy notifications).

    Two-phase design:
      Phase 1 — RIGID stages (spaced repetition + deep work, get their own slots):
        R1, R3, MN, R7, MVA, MAINS, R30
      Phase 2 — FLEXIBLE clusters (practice & analysis, packed atomically):
        [PYQ + ERA]       on R1 day (recall + immediate practice)
        [CA + MCQ + MCQA] day after MN (applied practice cluster)

    MN is standalone — never shares a day with other stage types of the same topic.
    """
    # ── Phase 1: Rigid stages ───────────────────────────────────────
    r1 = add_days(completion_date, intervals["r1"])

    r3_raw = add_days(completion_date, intervals["r3"])
    r3 = max(r3_raw, add_days(r1, 1))

    mn_date = add_days(r3, 1)                     # standalone day

    ca_date  = add_days(mn_date, 1)               # practice cluster day
    mcq_date = ca_date
    mcqa_date = ca_date

    r7_raw = add_days(completion_date, intervals["r7"])
    r7 = get_next_sunday(max(r7_raw, add_days(mcqa_date, 5)))

    mva_date = add_days(r7, 7)
    mains_date = add_days(mva_date, 1)

    r30_raw = add_days(completion_date, intervals["r30"])
    r30 = max(r30_raw, add_days(mains_date, 14))

    # ── Phase 2: Flexible clusters on rigid days ────────────────────
    pyq_date = r1                                  # same day as R1
    era_date = r1

    return {
        "r1":    {"date": r1,         "type": "R1",    "label": "1st Revision (Recall)"},
        "pyq":   {"date": pyq_date,   "type": "PYQ",   "label": "PYQ Practice"},
        "era":   {"date": era_date,   "type": "ERA",   "label": "Error Analysis"},
        "r3":    {"date": r3,         "type": "R3",    "label": "2nd Revision (Active Recall)"},
        "mn":    {"date": mn_date,    "type": "MN",    "label": "Micro Note Making"},
        "ca":    {"date": ca_date,    "type": "CA",    "label": "Current Affairs + Mapping"},
        "mcq":   {"date": mcq_date,   "type": "MCQ",   "label": "MCQ Practice"},
        "mcqa":  {"date": mcqa_date,  "type": "MCQA",  "label": "MCQ Analysis"},
        "r7":    {"date": r7,         "type": "R7",    "label": "3rd Revision (Weekend Consolidation)"},
        "mva":   {"date": mva_date,   "type": "MVA",   "label": "Mains Value Addition"},
        "mains": {"date": mains_date, "type": "MAINS", "label": "Mains Answer Writing"},
        "r30":   {"date": r30,        "type": "R30",   "label": "Final Revision"},
    }


def calculate_revision_schedule_dynamic(completion_date, intervals, act_hrs,
                                        daily_used, weekday_budget, weekend_budget):
    """Budget-aware two-phase revision scheduling (used by timeline estimator).

    Phase 1 — RIGID stages placed first (spaced repetition integrity):
      R1, R3, MN (standalone), R7 (Sunday), MVA, MAINS, R30
      Each respects minimum neurological gaps and anchored intervals.

    Phase 2 — FLEXIBLE clusters packed into available budget gaps:
      [PYQ + ERA]       → atomic cluster, earliest slot from R1 day
      [CA + MCQ + MCQA] → atomic cluster, earliest slot from day after MN

    Key rules:
      • MN never shares a day with other stages of this topic
      • Flexible clusters are atomic — the whole cluster fits or moves to next day
      • daily_used is modified in-place (shared budget map)
    """
    def _budget(d):
        return weekend_budget if is_weekend(d) else weekday_budget

    def _avail(d):
        return _budget(d) - daily_used.get(d, 0)

    def _fit(earliest, hrs, sunday_only=False):
        c = get_next_sunday(earliest) if sunday_only else earliest
        for _ in range(120):
            if _avail(c) >= hrs - 0.01:
                return c
            c = add_days(c, 1)
            if sunday_only:
                c = get_next_sunday(c)
        return c

    def _commit(d, hrs):
        daily_used[d] = daily_used.get(d, 0) + hrs

    # ── Phase 1: Rigid stages ───────────────────────────────────────
    r1 = _fit(add_days(completion_date, intervals["r1"]), act_hrs.get("R1", 1.5))
    _commit(r1, act_hrs.get("R1", 1.5))

    r3_earliest = max(add_days(completion_date, intervals["r3"]), add_days(r1, 1))
    r3 = _fit(r3_earliest, act_hrs.get("R3", 1.0))
    _commit(r3, act_hrs.get("R3", 1.0))

    # MN — standalone: must not share day with this topic's other stages
    mn = _fit(add_days(r3, 1), act_hrs.get("MN", 2.0))
    _commit(mn, act_hrs.get("MN", 2.0))

    r7_earliest = max(add_days(completion_date, intervals["r7"]), add_days(mn, 5))
    r7 = _fit(r7_earliest, act_hrs.get("R7", 1.5), sunday_only=True)
    _commit(r7, act_hrs.get("R7", 1.5))

    mva = _fit(add_days(r7, 7), act_hrs.get("MVA", 1.0))
    _commit(mva, act_hrs.get("MVA", 1.0))

    mains = _fit(add_days(mva, 1), act_hrs.get("MAINS", 1.5))
    _commit(mains, act_hrs.get("MAINS", 1.5))

    r30_earliest = max(add_days(completion_date, intervals["r30"]), add_days(mains, 14))
    r30 = _fit(r30_earliest, act_hrs.get("R30", 1.0))
    _commit(r30, act_hrs.get("R30", 1.0))

    # ── Phase 2: Flexible clusters ──────────────────────────────────
    # [PYQ + ERA]: atomic, try R1 day first, skip this topic's MN day
    cluster_a = act_hrs.get("PYQ", 0.5) + act_hrs.get("ERA", 0.5)
    cand = r1
    for _ in range(120):
        if cand != mn and _avail(cand) >= cluster_a - 0.01:
            break
        cand = add_days(cand, 1)
    _commit(cand, cluster_a)
    pyq_date = era_date = cand

    # [CA + MCQ + MCQA]: atomic, from day after MN, skip this topic's MN day
    cluster_b = act_hrs.get("CA", 1.0) + act_hrs.get("MCQ", 0.5) + act_hrs.get("MCQA", 0.5)
    cand = add_days(mn, 1)
    for _ in range(120):
        if cand != mn and _avail(cand) >= cluster_b - 0.01:
            break
        cand = add_days(cand, 1)
    _commit(cand, cluster_b)
    ca_date = mcq_date = mcqa_date = cand

    return {
        "r1":    {"date": r1,         "type": "R1",    "label": "1st Revision (Recall)"},
        "pyq":   {"date": pyq_date,   "type": "PYQ",   "label": "PYQ Practice"},
        "era":   {"date": era_date,   "type": "ERA",   "label": "Error Analysis"},
        "r3":    {"date": r3,         "type": "R3",    "label": "2nd Revision (Active Recall)"},
        "mn":    {"date": mn,         "type": "MN",    "label": "Micro Note Making"},
        "ca":    {"date": ca_date,    "type": "CA",    "label": "Current Affairs + Mapping"},
        "mcq":   {"date": mcq_date,   "type": "MCQ",   "label": "MCQ Practice"},
        "mcqa":  {"date": mcqa_date,  "type": "MCQA",  "label": "MCQ Analysis"},
        "r7":    {"date": r7,         "type": "R7",    "label": "3rd Revision (Weekend Consolidation)"},
        "mva":   {"date": mva,        "type": "MVA",   "label": "Mains Value Addition"},
        "mains": {"date": mains,      "type": "MAINS", "label": "Mains Answer Writing"},
        "r30":   {"date": r30,        "type": "R30",   "label": "Final Revision"},
    }


def resolve_all_revision_schedules(data):
    """Global two-phase budget-aware scheduling for ALL completed topics.

    Phase 1 — ALL topics' rigid stages are placed first:
      R1, R3, MN, R7, MVA, MAINS, R30
      Spaced repetition anchors get absolute priority over practice tasks.

    Phase 2 — ALL topics' flexible clusters fill remaining budget gaps:
      [PYQ + ERA], [CA + MCQ + MCQA]
      Placed as atomic units for maximum daily utilization.

    Global two-phase ensures rigid stages never get displaced by another
    topic's flexible practice — the core spaced repetition timing is sacred.

    Returns: (resolved, daily_used)
      resolved  = {topic_id: schedule_dict}
      daily_used = {date_str: hours_committed}
    """
    settings = data["settings"]
    intervals = settings["intervals"]
    act_hrs = get_activity_hours(settings)
    weekday_budget = settings.get("weekdayHours", 6)
    weekend_budget = settings.get("weekendHours", 12)

    def _budget(d):
        return weekend_budget if is_weekend(d) else weekday_budget

    def _avail(d):
        return _budget(d) - daily_used.get(d, 0)

    def _fit(earliest, hrs, sunday_only=False):
        c = get_next_sunday(earliest) if sunday_only else earliest
        for _ in range(120):
            if _avail(c) >= hrs - 0.01:
                return c
            c = add_days(c, 1)
            if sunday_only:
                c = get_next_sunday(c)
        return c

    def _commit(d, hrs):
        daily_used[d] = daily_used.get(d, 0) + hrs

    # Collect all completed/mastered topics, sorted by completion date
    topics = []
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] in ("completed", "mastered") and topic.get("completionDate"):
                topics.append(topic)
    topics.sort(key=lambda t: t["completionDate"])

    daily_used = {}
    rigid = {}   # topic_id → {r1, r3, mn, r7, mva, mains, r30}

    # ── PHASE 1: Place rigid stages for ALL topics ──────────────────
    for t in topics:
        cd = t["completionDate"]
        tid = t["id"]

        r1 = _fit(add_days(cd, intervals["r1"]), act_hrs.get("R1", 1.5))
        _commit(r1, act_hrs.get("R1", 1.5))

        r3_e = max(add_days(cd, intervals["r3"]), add_days(r1, 1))
        r3 = _fit(r3_e, act_hrs.get("R3", 1.0))
        _commit(r3, act_hrs.get("R3", 1.0))

        mn = _fit(add_days(r3, 1), act_hrs.get("MN", 2.0))
        _commit(mn, act_hrs.get("MN", 2.0))

        r7_e = max(add_days(cd, intervals["r7"]), add_days(mn, 5))
        r7 = _fit(r7_e, act_hrs.get("R7", 1.5), sunday_only=True)
        _commit(r7, act_hrs.get("R7", 1.5))

        mva = _fit(add_days(r7, 7), act_hrs.get("MVA", 1.0))
        _commit(mva, act_hrs.get("MVA", 1.0))

        mains = _fit(add_days(mva, 1), act_hrs.get("MAINS", 1.5))
        _commit(mains, act_hrs.get("MAINS", 1.5))

        r30_e = max(add_days(cd, intervals["r30"]), add_days(mains, 14))
        r30 = _fit(r30_e, act_hrs.get("R30", 1.0))
        _commit(r30, act_hrs.get("R30", 1.0))

        rigid[tid] = {
            "r1": r1, "r3": r3, "mn": mn, "r7": r7,
            "mva": mva, "mains": mains, "r30": r30,
        }

    # ── PHASE 2: Place flexible clusters for ALL topics ─────────────
    resolved = {}
    for t in topics:
        tid = t["id"]
        rd = rigid[tid]

        # [PYQ + ERA]: atomic, from R1 day, skip this topic's MN day
        cluster_a = act_hrs.get("PYQ", 0.5) + act_hrs.get("ERA", 0.5)
        cand = rd["r1"]
        for _ in range(120):
            if cand != rd["mn"] and _avail(cand) >= cluster_a - 0.01:
                break
            cand = add_days(cand, 1)
        _commit(cand, cluster_a)
        pyq_date = era_date = cand

        # [CA + MCQ + MCQA]: atomic, from day after MN, skip MN day
        cluster_b = act_hrs.get("CA", 1.0) + act_hrs.get("MCQ", 0.5) + act_hrs.get("MCQA", 0.5)
        cand = add_days(rd["mn"], 1)
        for _ in range(120):
            if cand != rd["mn"] and _avail(cand) >= cluster_b - 0.01:
                break
            cand = add_days(cand, 1)
        _commit(cand, cluster_b)
        ca_date = mcq_date = mcqa_date = cand

        resolved[tid] = {
            "r1":    {"date": rd["r1"],    "type": "R1",    "label": "1st Revision (Recall)"},
            "pyq":   {"date": pyq_date,    "type": "PYQ",   "label": "PYQ Practice"},
            "era":   {"date": era_date,    "type": "ERA",   "label": "Error Analysis"},
            "r3":    {"date": rd["r3"],    "type": "R3",    "label": "2nd Revision (Active Recall)"},
            "mn":    {"date": rd["mn"],    "type": "MN",    "label": "Micro Note Making"},
            "ca":    {"date": ca_date,     "type": "CA",    "label": "Current Affairs + Mapping"},
            "mcq":   {"date": mcq_date,    "type": "MCQ",   "label": "MCQ Practice"},
            "mcqa":  {"date": mcqa_date,   "type": "MCQA",  "label": "MCQ Analysis"},
            "r7":    {"date": rd["r7"],    "type": "R7",    "label": "3rd Revision (Weekend Consolidation)"},
            "mva":   {"date": rd["mva"],   "type": "MVA",   "label": "Mains Value Addition"},
            "mains": {"date": rd["mains"], "type": "MAINS", "label": "Mains Answer Writing"},
            "r30":   {"date": rd["r30"],   "type": "R30",   "label": "Final Revision"},
        }

    return resolved, daily_used


def get_tasks_for_date(data, date_str, resolved_schedules=None):
    """Return all revision / practice tasks scheduled for a specific date."""
    if resolved_schedules is None:
        resolved_schedules, _ = resolve_all_revision_schedules(data)
    tasks = []
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] != "completed" or not topic.get("completionDate"):
                continue
            schedule = resolved_schedules.get(topic["id"])
            if not schedule:
                continue
            for key, rev in schedule.items():
                if rev["date"] == date_str:
                    rev_key = f"{topic['id']}_{rev['type']}"
                    done = rev_key in data["completedRevisions"]
                    overdue = date_str < today_str() and not done
                    tasks.append({
                        "topicId": topic["id"],
                        "subjectId": subj["id"],
                        "subjectName": subj["name"],
                        "subjectColor": subj["color"],
                        "topicName": topic["name"],
                        "topicROI": topic.get("roi", "medium"),
                        "type": rev["type"],
                        "label": rev["label"],
                        "date": rev["date"],
                        "done": done,
                        "overdue": overdue,
                    })
    return tasks


def get_overdue_tasks(data, resolved_schedules=None):
    """Return all tasks from past dates that haven't been completed."""
    if resolved_schedules is None:
        resolved_schedules, _ = resolve_all_revision_schedules(data)
    today = today_str()
    tasks = []
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] != "completed" or not topic.get("completionDate"):
                continue
            schedule = resolved_schedules.get(topic["id"])
            if not schedule:
                continue
            for key, rev in schedule.items():
                if rev["date"] < today:
                    rev_key = f"{topic['id']}_{rev['type']}"
                    if rev_key not in data["completedRevisions"]:
                        tasks.append({
                            "topicId": topic["id"],
                            "subjectId": subj["id"],
                            "subjectName": subj["name"],
                            "subjectColor": subj["color"],
                            "topicName": topic["name"],
                            "type": rev["type"],
                            "label": rev["label"],
                            "date": rev["date"],
                            "done": False,
                            "overdue": True,
                        })
    tasks.sort(key=lambda t: t["date"])
    return tasks


# =============================================================================
#  ROUTES — Authentication
# =============================================================================

@app.route("/login", methods=["GET", "POST"])
def login_page():
    """Show login form (GET) or validate credentials (POST)."""
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        if username == AUTH_USERNAME and pw_hash == AUTH_PASSWORD_HASH:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# =============================================================================
#  ROUTES — Pages
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html", cache_bust=int(time.time()))


# =============================================================================
#  ROUTES — HTML File Hosting
# =============================================================================

@app.route("/api/uploads", methods=["GET"])
def list_uploads():
    """Return list of uploaded HTML files with their view URLs."""
    files = []
    for fname in sorted(os.listdir(UPLOADS_DIR)):
        ext = os.path.splitext(fname)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            fpath = os.path.join(UPLOADS_DIR, fname)
            stat = os.stat(fpath)
            files.append({
                "name": fname,
                "size": stat.st_size,
                "uploaded": datetime.fromtimestamp(stat.st_mtime, tz=IST).strftime("%Y-%m-%d %H:%M"),
                "url": f"/view/{fname}",
            })
    return jsonify(files)


@app.route("/api/uploads", methods=["POST"])
def upload_html():
    """Upload one or more HTML files."""
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400
    uploaded = []
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        # Sanitise filename: keep only safe characters
        from werkzeug.utils import secure_filename as _sec
        safe_name = _sec(f.filename)
        if not safe_name:
            continue
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        dest = os.path.join(UPLOADS_DIR, safe_name)
        f.save(dest)
        uploaded.append(safe_name)
    if not uploaded:
        return jsonify({"error": "No valid HTML files uploaded"}), 400
    return jsonify({"ok": True, "files": uploaded})


@app.route("/api/uploads/<filename>", methods=["DELETE"])
def delete_upload(filename):
    """Delete an uploaded HTML file."""
    from werkzeug.utils import secure_filename as _sec
    safe = _sec(filename)
    fpath = os.path.join(UPLOADS_DIR, safe)
    if not os.path.isfile(fpath):
        return jsonify({"error": "File not found"}), 404
    os.remove(fpath)
    return jsonify({"ok": True})


@app.route("/view/<filename>")
def view_upload(filename):
    """Serve an uploaded HTML file."""
    from werkzeug.utils import secure_filename as _sec
    safe = _sec(filename)
    fpath = os.path.join(UPLOADS_DIR, safe)
    if not os.path.isfile(fpath):
        return "File not found", 404
    return send_file(fpath, mimetype="text/html")


# =============================================================================
#  ROUTES — API
# =============================================================================

@app.route("/api/data", methods=["GET"])
def api_get_data():
    """Return the full data store."""
    return jsonify(load_data())


@app.route("/api/data", methods=["PUT"])
def api_put_data():
    """Overwrite the full data store (for import / settings save)."""
    data = request.get_json(force=True)
    save_data(data)
    return jsonify({"ok": True})


# ---- Subjects ----

@app.route("/api/subjects", methods=["POST"])
def api_add_subject():
    body = request.get_json(force=True)
    data = load_data()
    subj = {
        "id": gen_id(),
        "name": body["name"],
        "roi": body.get("roi", "high"),
        "color": body.get("color", "#6366f1"),
        "ntfyTopic": body.get("ntfyTopic", ""),
        "notes": body.get("notes", ""),
        "topics": [],
        "createdAt": today_str(),
    }
    data["subjects"].append(subj)
    save_data(data)

    ntfy_channel = subj["ntfyTopic"] or None
    send_ntfy(
        "New Subject Added",
        f"Subject: {subj['name']}\n"
        f"Priority: {subj['roi'].upper()} ROI\n"
        f"Color: {subj['color']}\n"
        f"Channel: {subj['ntfyTopic'] or 'Global'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ready to add micro-topics!",
        tags=["books", "sparkles"],
        priority=3,
        subject_topic=ntfy_channel,
    )

    return jsonify(subj)


@app.route("/api/subjects/<subj_id>", methods=["DELETE"])
def api_delete_subject(subj_id):
    data = load_data()
    deleted = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    data["subjects"] = [s for s in data["subjects"] if s["id"] != subj_id]
    save_data(data)

    if deleted:
        topic_count = len(deleted.get("topics", []))
        send_ntfy(
            "Subject Deleted",
            f"Subject: {deleted['name']}\n"
            f"Topics removed: {topic_count}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"This action cannot be undone.",
            tags=["wastebasket"],
            priority=2,
            subject_topic=deleted.get("ntfyTopic") or None,
        )

    return jsonify({"ok": True})


# ---- Topics ----

@app.route("/api/subjects/<subj_id>/topics", methods=["POST"])
def api_add_topic(subj_id):
    body = request.get_json(force=True)
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    topic = {
        "id": gen_id(),
        "name": body["name"],
        "estimatedHours": round(float(body.get("estimatedHours", 7.5)), 1),
        "roi": body.get("roi", "high"),
        "notes": body.get("notes", ""),
        "status": "not-started",
        "startDate": None,
        "completionDate": None,
        "createdAt": today_str(),
    }
    subj["topics"].append(topic)
    save_data(data)

    send_ntfy(
        "New Topic Added",
        f"Topic: {topic['name']}\n"
        f"Subject: {subj['name']}\n"
        f"Est. Duration: {topic['estimatedHours']}h\n"
        f"Priority: {topic['roi'].upper()} ROI\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Start learning when ready!",
        tags=["memo", "pencil"],
        priority=3,
        subject_topic=subj.get("ntfyTopic") or None,
    )

    return jsonify(topic)


@app.route("/api/subjects/<subj_id>/topics/<topic_id>", methods=["PUT"])
def api_edit_topic(subj_id, topic_id):
    """Edit a topic's name, estimatedHours, and/or ROI priority."""
    body = request.get_json(force=True)
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    topic = next((t for t in subj["topics"] if t["id"] == topic_id), None)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404

    changes = []
    if "name" in body and body["name"].strip():
        old_name = topic["name"]
        topic["name"] = body["name"].strip()
        if old_name != topic["name"]:
            changes.append(f"Name: {old_name} → {topic['name']}")
            # Update name in cumulative revision pending pool
            cum = data.get("cumulativeRevisions", {})
            for pt in cum.get("pendingTopics", []):
                if pt.get("topicId") == topic_id:
                    pt["topicName"] = topic["name"]
    if "estimatedHours" in body:
        old_hrs = topic.get("estimatedHours", 7.5)
        topic["estimatedHours"] = max(0.5, min(100, round(float(body["estimatedHours"]), 1)))
        if old_hrs != topic["estimatedHours"]:
            changes.append(f"Est. Hours: {old_hrs}h → {topic['estimatedHours']}h")
    if "roi" in body and body["roi"] in ("very-high", "high", "medium", "low"):
        old_roi = topic.get("roi", "medium")
        topic["roi"] = body["roi"]
        if old_roi != topic["roi"]:
            changes.append(f"ROI: {old_roi.upper()} → {topic['roi'].upper()}")
            # Update ROI in cumulative revision pending pool
            cum = data.get("cumulativeRevisions", {})
            for pt in cum.get("pendingTopics", []):
                if pt.get("topicId") == topic_id:
                    pt["roi"] = topic["roi"]

    if changes:
        save_data(data)
        send_ntfy(
            f"Topic Updated: {topic['name']}",
            f"Subject: {subj['name']}\n"
            f"Changes:\n" + "\n".join(f"  • {c}" for c in changes),
            tags=["pencil2"],
            priority=2,
            subject_topic=subj.get("ntfyTopic") or None,
        )

    return jsonify({"ok": True, "topic": topic})


@app.route("/api/subjects/<subj_id>/topics/<topic_id>", methods=["DELETE"])
def api_delete_topic(subj_id, topic_id):
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    deleted_topic = next((t for t in subj["topics"] if t["id"] == topic_id), None)
    subj["topics"] = [t for t in subj["topics"] if t["id"] != topic_id]
    # Clean revisions
    keys_to_remove = [k for k in data["completedRevisions"] if k.startswith(topic_id)]
    for k in keys_to_remove:
        del data["completedRevisions"][k]
    save_data(data)

    if deleted_topic:
        send_ntfy(
            "Topic Deleted",
            f"Topic: {deleted_topic['name']}\n"
            f"Subject: {subj['name']}\n"
            f"Revisions cleared: {len(keys_to_remove)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"All revision data removed.",
            tags=["wastebasket"],
            priority=2,
            subject_topic=subj.get("ntfyTopic") or None,
        )

    return jsonify({"ok": True})


@app.route("/api/subjects/<subj_id>/topics/<topic_id>/start", methods=["POST"])
def api_start_topic(subj_id, topic_id):
    data = load_data()
    # Enforce parallel learning limit: count all currently-learning topics
    learning_count = sum(
        1
        for s in data["subjects"]
        for t in s.get("topics", [])
        if t["status"] == "learning"
    )
    if learning_count >= MAX_PARALLEL_TOPICS:
        return jsonify({
            "error": f"You already have {learning_count} topics in progress. "
                     f"Complete (mark Done) a current topic before starting a new one.",
            "limitReached": True,
            "currentlyLearning": learning_count,
            "maxParallel": MAX_PARALLEL_TOPICS,
        }), 409

    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    topic = next((t for t in subj["topics"] if t["id"] == topic_id), None)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404
    topic["status"] = "learning"
    topic["startDate"] = today_str()
    save_data(data)

    send_ntfy(
        "Started Learning",
        f"Topic: {topic['name']}\n"
        f"Subject: {subj['name']}\n"
        f"Started: {today_str()}\n"
        f"Est. Duration: {topic.get('estimatedHours', '?')}h\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Focus and conquer!",
        tags=["rocket", "brain"],
        priority=3,
        subject_topic=subj.get("ntfyTopic") or None,
    )

    return jsonify(topic)


@app.route("/api/subjects/<subj_id>/topics/<topic_id>/complete", methods=["POST"])
def api_complete_topic(subj_id, topic_id):
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    topic = next((t for t in subj["topics"] if t["id"] == topic_id), None)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404
    topic["status"] = "completed"
    topic["completionDate"] = today_str()
    save_data(data)
    schedule = calculate_revision_schedule(today_str(), data["settings"]["intervals"])

    # Build beautiful schedule summary
    sched_lines = []
    for key in ["r1", "pyq", "era", "r3", "mn", "ca", "mcq", "mcqa", "r7", "mva", "mains", "r30"]:
        rev = schedule[key]
        sched_lines.append(f"{rev['type']}: {rev['date']}")

    send_ntfy(
        "Topic Completed!",
        f"Topic: {topic['name']}\n"
        f"Subject: {subj['name']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Revision Schedule Created:\n"
        + "\n".join(sched_lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"12 stages to mastery! Keep going!",
        tags=["white_check_mark", "tada"],
        priority=4,
        subject_topic=subj.get("ntfyTopic") or None,
    )

    return jsonify({"topic": topic, "schedule": schedule})


@app.route("/api/subjects/<subj_id>/topics/<topic_id>/reset", methods=["POST"])
def api_reset_topic(subj_id, topic_id):
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    topic = next((t for t in subj["topics"] if t["id"] == topic_id), None)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404
    topic["status"] = "not-started"
    topic["startDate"] = None
    topic["completionDate"] = None
    keys_to_remove = [k for k in data["completedRevisions"] if k.startswith(topic_id)]
    for k in keys_to_remove:
        del data["completedRevisions"][k]
    save_data(data)

    send_ntfy(
        "↺ Topic Reset",
        f"Topic: {topic['name']}\n"
        f"Subject: {subj['name']}\n"
        f"Revisions cleared: {len(keys_to_remove)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Back to square one. Fresh start!",
        tags=["arrows_counterclockwise"],
        priority=2,
        subject_topic=subj.get("ntfyTopic") or None,
    )

    return jsonify(topic)


# ---- Revisions ----

@app.route("/api/revisions/mark", methods=["POST"])
def api_mark_revision():
    body = request.get_json(force=True)
    topic_id = body["topicId"]
    rev_type = body["type"]
    key = f"{topic_id}_{rev_type}"
    data = load_data()
    data["completedRevisions"][key] = int(time.time() * 1000)
    save_data(data)

    topic_name, subj_name, subj_ntfy = find_topic_info(data, topic_id)

    # Determine progress
    types = ["R1", "PYQ", "ERA", "R3", "MN", "CA", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30"]
    done_count = sum(1 for t in types if f"{topic_id}_{t}" in data["completedRevisions"])
    progress_bar = "" .join("█" if f"{topic_id}_{t}" in data["completedRevisions"] else "░" for t in types)

    type_emoji = {"R1": "R1", "PYQ": "PYQ", "ERA": "ERA", "R3": "R3", "MN": "MN", "CA": "CA", "MCQ": "MCQ", "MCQA": "MCQA", "R7": "R7", "MVA": "MVA", "R30": "R30", "MAINS": "MAINS"}
    type_desc = {"R1": "1st Revision", "PYQ": "PYQ Practice", "ERA": "Error Analysis", "R3": "2nd Revision", "MN": "Micro Note Making", "CA": "Current Affairs + Mapping", "MCQ": "MCQ Practice", "MCQA": "MCQ Analysis", "R7": "3rd Revision", "MVA": "Mains Value Addition", "MAINS": "Mains Writing", "R30": "Final Revision"}

    send_ntfy(
        f"{type_emoji.get(rev_type, '✓')} {rev_type} Revision Done!",
        f"Topic: {topic_name}\n"
        f"Subject: {subj_name}\n"
        f"Stage: {type_desc.get(rev_type, rev_type)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Progress: [{progress_bar}] {done_count}/12\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{12 - done_count} stage(s) remaining to mastery",
        tags=["white_check_mark", "fire"],
        priority=3,
        subject_topic=subj_ntfy or None,
    )

    # Check if ALL revisions are done → MASTERED!
    if check_topic_mastery(data, topic_id):
        send_ntfy(
            "TOPIC MASTERED!",
            f"********************\n"
            f"\n"
            f"Topic: {topic_name}\n"
            f"Subject: {subj_name}\n"
            f"\n"
            f"ALL 12 REVISION STAGES COMPLETE!\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"[done] R1    -- 1st Revision\n"
            f"[done] PYQ   -- PYQ Practice\n"
            f"[done] ERA   -- Error Analysis\n"
            f"[done] R3    -- 2nd Revision\n"
            f"[done] MN    -- Micro Note Making\n"
            f"[done] CA    -- Current Affairs + Mapping\n"
            f"[done] MCQ   -- MCQ Practice\n"
            f"[done] MCQA  -- MCQ Analysis\n"
            f"[done] R7    -- 3rd Revision\n"
            f"[done] MVA   -- Mains Value Addition\n"
            f"[done] MAINS -- Mains Writing\n"
            f"[done] R30   -- Final Revision\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"This topic is now deeply embedded\n"
            f"in your long-term memory!\n"
            f"\n"
            f"********************",
            tags=["trophy", "tada", "star", "brain"],
            priority=5,
            subject_topic=subj_ntfy or None,
        )

        # Auto-mark as mastered & add to cumulative revision pending pool
        for subj in data["subjects"]:
            for topic in subj["topics"]:
                if topic["id"] == topic_id:
                    topic["status"] = "mastered"
                    # Add to cumulative revision pending pool
                    add_topic_to_pending(
                        data, topic_id, topic["name"],
                        subj["id"], subj["name"],
                        topic.get("roi", "medium"),
                    )
                    # Check if a batch can be formed
                    check_and_create_batches(data)
                    save_data(data)
                    break

    return jsonify({"ok": True, "key": key})


@app.route("/api/revisions/unmark", methods=["POST"])
def api_unmark_revision():
    body = request.get_json(force=True)
    topic_id = body["topicId"]
    rev_type = body["type"]
    key = f"{topic_id}_{rev_type}"
    data = load_data()
    data["completedRevisions"].pop(key, None)
    save_data(data)

    topic_name, subj_name, subj_ntfy = find_topic_info(data, topic_id)
    send_ntfy(
        "↩ Revision Unmarked",
        f"Topic: {topic_name}\n"
        f"Subject: {subj_name}\n"
        f"Stage: {rev_type} — marked as NOT done\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"You can redo this revision.",
        tags=["leftwards_arrow_with_hook"],
        priority=2,
        subject_topic=subj_ntfy or None,
    )

    return jsonify({"ok": True})


# ---- Settings ----

@app.route("/api/ntfy/test", methods=["POST"])
def api_ntfy_test():
    """Send a test notification to verify ntfy setup."""
    data = load_data()
    ntfy_cfg = data.get("settings", {}).get("ntfy", {})
    if not ntfy_cfg.get("enabled"):
        return jsonify({"ok": False, "error": "ntfy not enabled. Enable it in settings first."})

    body = request.get_json(force=True) if request.data else {}
    subject_id = body.get("subjectId") if body else None
    
    # Determine target topic
    if subject_id:
        subj = next((s for s in data["subjects"] if s["id"] == subject_id), None)
        if not subj:
            return jsonify({"ok": False, "error": "Subject not found"})
        target_topic = subj.get("ntfyTopic", "")
        if not target_topic:
            return jsonify({"ok": False, "error": f"No ntfy topic set for '{subj['name']}'. Set one first."})
        test_title = f"Test -- {subj['name']}"
        test_body = (
            f"Notifications working for:\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Subject: {subj['name']}\n"
            f"Channel: {target_topic}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"All topic notifications for this\n"
            f"subject will arrive here!"
        )
    else:
        target_topic = ntfy_cfg.get("topic", "")
        if not target_topic:
            return jsonify({"ok": False, "error": "No global ntfy topic set. Set one in settings first."})
        test_title = "UPSC Tracker -- Test Notification"
        test_body = (
            "Notifications are working!\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "This is the GLOBAL channel.\n"
            "General notifications arrive here:\n"
            "\n"
            "Settings changed\n"
            "Data imported\n"
            "Data cleared\n"
            "\n"
            "Subject-specific notifications go\n"
            "to their own channels if configured.\n"
            "\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Your UPSC journey is tracked!"
        )

    server = ntfy_cfg.get("server", "https://ntfy.sh").rstrip("/")
    url = f"{server}/{target_topic}"

    try:
        headers = {
            "Title": test_title.encode("utf-8"),
            "Priority": "4",
            "Tags": "bell,white_check_mark,rocket",
        }
        req = urllib.request.Request(url, data=test_body.encode("utf-8"), headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=10)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/subjects/<subj_id>/ntfy", methods=["PUT"])
def api_update_subject_ntfy(subj_id):
    """Update the ntfy topic for a specific subject."""
    body = request.get_json(force=True)
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    subj["ntfyTopic"] = body.get("ntfyTopic", "")
    save_data(data)
    return jsonify({"ok": True, "subject": subj["name"], "ntfyTopic": subj["ntfyTopic"]})


@app.route("/api/settings", methods=["PUT"])
def api_save_settings():
    body = request.get_json(force=True)
    data = load_data()
    data["settings"] = body
    save_data(data)

    send_ntfy(
        "Settings Updated",
        f"Weekday: {body.get('weekdayHours', '?')}h\n"
        f"Weekend: {body.get('weekendHours', '?')}h\n"
        f"Rev Block: {body.get('revisionMins', '?')} min\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Intervals: R1={body.get('intervals', {}).get('r1', '?')}d, "
        f"R3={body.get('intervals', {}).get('r3', '?')}d, "
        f"R7={body.get('intervals', {}).get('r7', '?')}d, "
        f"R30={body.get('intervals', {}).get('r30', '?')}d\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Notifications: {'ON' if body.get('ntfy', {}).get('enabled') else 'OFF'}",
        tags=["gear"],
        priority=2,
    )

    return jsonify({"ok": True})


# ---- Dashboard helpers ----

@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    data = load_data()
    today = today_str()
    today_tasks = get_tasks_for_date(data, today)
    overdue = get_overdue_tasks(data)

    total_topics = sum(len(s["topics"]) for s in data["subjects"])
    learning = sum(1 for s in data["subjects"] for t in s["topics"] if t["status"] == "learning")
    completed = sum(1 for s in data["subjects"] for t in s["topics"] if t["status"] in ("completed", "mastered"))
    total_revisions = len(data["completedRevisions"])

    learning_topics = []
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] == "learning":
                learning_topics.append({
                    **topic,
                    "subjectName": subj["name"],
                    "subjectColor": subj["color"],
                    "subjectId": subj["id"],
                })

    # Upcoming 7 days
    upcoming = {}
    for i in range(1, 8):
        d = add_days(today, i)
        tasks = get_tasks_for_date(data, d)
        if tasks:
            upcoming[d] = tasks

    # Cumulative revision sessions for dashboard
    cum = data.get("cumulativeRevisions", {})
    cum_upcoming = []
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if not sess["completed"]:
                days_until = (datetime.strptime(sess["scheduledDate"], "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days
                if -7 <= days_until <= 14:
                    cum_upcoming.append({
                        "type": "sectional",
                        "batchId": batch["id"],
                        "round": sess["round"],
                        "date": sess["scheduledDate"],
                        "topicCount": len(batch["topicIds"]),
                        "topicDetails": batch.get("topicDetails", []),
                        "overdue": days_until < 0,
                        "isToday": days_until == 0,
                    })
    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if not sess["completed"]:
                days_until = (datetime.strptime(sess["scheduledDate"], "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days
                if -7 <= days_until <= 14:
                    cum_upcoming.append({
                        "type": "subject",
                        "subjectId": sr["subjectId"],
                        "subjectName": sr["subjectName"],
                        "round": sess["round"],
                        "date": sess["scheduledDate"],
                        "overdue": days_until < 0,
                        "isToday": days_until == 0,
                    })
    cum_upcoming.sort(key=lambda x: x["date"])

    return jsonify({
        "today": today,
        "isWeekend": is_weekend(today),
        "stats": {
            "totalTopics": total_topics,
            "learning": learning,
            "completed": completed,
            "todayTasks": len(today_tasks),
            "todayDone": sum(1 for t in today_tasks if t["done"]),
            "overdue": len(overdue),
            "totalRevisions": total_revisions,
        },
        "todayTasks": today_tasks,
        "overdueTasks": overdue,
        "learningTopics": learning_topics,
        "upcoming": upcoming,
        "cumulativeUpcoming": cum_upcoming,
        "timeBudget": compute_daily_load(data, today, include_overdue=True),
    })


# ---- Daily Plan (Time-Budget-Aware) ----

@app.route("/api/daily-plan", methods=["GET"])
def api_daily_plan():
    """Return a time-budget-aware schedule for the next 14 days.
    Shows hours committed vs available for each day."""
    data = load_data()
    days = int(request.args.get("days", 14))
    days = min(days, 60)  # cap at 60 days
    schedule = build_daily_schedule(data, days)
    act_hrs = get_activity_hours(data["settings"])
    return jsonify({
        "today": today_str(),
        "schedule": schedule,
        "activityHours": act_hrs,
        "settings": {
            "weekdayHours": data["settings"].get("weekdayHours", 6),
            "weekendHours": data["settings"].get("weekendHours", 12),
        },
    })


# ---- Today's Plan ----

@app.route("/api/today", methods=["GET"])
def api_today():
    data = load_data()
    today = today_str()
    d = datetime.strptime(today, "%Y-%m-%d")

    # Cumulative sessions due today or this weekend
    cum = data.get("cumulativeRevisions", {})
    cum_today = []
    today_sat = get_next_saturday(today)
    today_sun = add_days(today_sat, 1)
    for batch in cum.get("sectionalBatches", []):
        for sess in batch["sessions"]:
            if not sess["completed"] and sess["scheduledDate"] in (today, today_sat, today_sun):
                cum_today.append({
                    "type": "sectional",
                    "batchId": batch["id"],
                    "round": sess["round"],
                    "date": sess["scheduledDate"],
                    "topicCount": len(batch["topicIds"]),
                    "topicDetails": batch.get("topicDetails", []),
                })
            elif not sess["completed"] and sess["scheduledDate"] < today:
                cum_today.append({
                    "type": "sectional",
                    "batchId": batch["id"],
                    "round": sess["round"],
                    "date": sess["scheduledDate"],
                    "topicCount": len(batch["topicIds"]),
                    "topicDetails": batch.get("topicDetails", []),
                    "overdue": True,
                })
    for sr in cum.get("subjectRevisions", []):
        for sess in sr["sessions"]:
            if not sess["completed"] and sess["scheduledDate"] in (today, today_sat, today_sun):
                cum_today.append({
                    "type": "subject",
                    "subjectId": sr["subjectId"],
                    "subjectName": sr["subjectName"],
                    "round": sess["round"],
                    "date": sess["scheduledDate"],
                })
            elif not sess["completed"] and sess["scheduledDate"] < today:
                cum_today.append({
                    "type": "subject",
                    "subjectId": sr["subjectId"],
                    "subjectName": sr["subjectName"],
                    "round": sess["round"],
                    "date": sess["scheduledDate"],
                    "overdue": True,
                })

    return jsonify({
        "today": today,
        "dayOfWeek": d.weekday(),  # Mon=0, Sun=6
        "isWeekend": is_weekend(today),
        "settings": data["settings"],
        "todayTasks": get_tasks_for_date(data, today),
        "overdueTasks": get_overdue_tasks(data),
        "learningTopics": [
            {**t, "subjectName": s["name"], "subjectColor": s["color"], "subjectId": s["id"]}
            for s in data["subjects"] for t in s["topics"] if t["status"] == "learning"
        ],
        "cumulativeSessions": cum_today,
        "timeBudget": compute_daily_load(data, today, include_overdue=True),
    })


# ---- Calendar ----

@app.route("/api/calendar/<int:year>/<int:month>", methods=["GET"])
def api_calendar(year, month):
    """Return tasks for each day in the given month."""
    import calendar
    data = load_data()
    days_in_month = calendar.monthrange(year, month)[1]
    events = {}
    for day in range(1, days_in_month + 1):
        d = datetime(year, month, day)
        ds = d.strftime("%Y-%m-%d")
        tasks = get_tasks_for_date(data, ds)
        if tasks:
            events[ds] = tasks
    return jsonify({
        "year": year,
        "month": month,
        "firstDayOfWeek": datetime(year, month, 1).weekday(),  # Mon=0
        "daysInMonth": days_in_month,
        "events": events,
        "today": today_str(),
    })


@app.route("/api/calendar/day/<date_str>", methods=["GET"])
def api_calendar_day(date_str):
    """Return all tasks for a specific date with full details."""
    data = load_data()
    tasks = get_tasks_for_date(data, date_str)
    d = datetime.strptime(date_str, "%Y-%m-%d")
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    total = len(tasks)
    done = sum(1 for t in tasks if t["done"])
    overdue_count = sum(1 for t in tasks if t.get("overdue"))
    is_past = date_str < today_str()
    is_today = date_str == today_str()
    is_future = date_str > today_str()

    # Time budget for this day
    tb = compute_daily_load(data, date_str, include_overdue=is_today)

    return jsonify({
        "date": date_str,
        "dayName": day_names[d.weekday()],
        "isWeekend": d.weekday() in (5, 6),
        "isToday": is_today,
        "isPast": is_past,
        "isFuture": is_future,
        "total": total,
        "done": done,
        "overdue": overdue_count,
        "pending": total - done,
        "tasks": tasks,
        "timeBudget": tb,
    })


# ---- Analytics ----

@app.route("/api/analytics", methods=["GET"])
def api_analytics():
    data = load_data()
    intervals = data["settings"]["intervals"]
    total = sum(len(s["topics"]) for s in data["subjects"])
    not_started = sum(1 for s in data["subjects"] for t in s["topics"] if t["status"] == "not-started")
    learning = sum(1 for s in data["subjects"] for t in s["topics"] if t["status"] == "learning")
    completed = sum(1 for s in data["subjects"] for t in s["topics"] if t["status"] == "completed")
    mastered = sum(1 for s in data["subjects"] for t in s["topics"] if t["status"] == "mastered")

    total_expected = completed * 12
    total_done = len(data["completedRevisions"])
    compliance = round(total_done / total_expected * 100) if total_expected > 0 else 0
    overdue = len(get_overdue_tasks(data))

    # Per-type stats
    types = ["R1", "PYQ", "ERA", "R3", "MN", "CA", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30"]
    rev_stats = {t: {"total": 0, "done": 0} for t in types}
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] != "completed" or not topic.get("completionDate"):
                continue
            for t in types:
                rev_stats[t]["total"] += 1
                if f"{topic['id']}_{t}" in data["completedRevisions"]:
                    rev_stats[t]["done"] += 1

    # Subject progress
    roi_order = {"very-high": 0, "high": 1, "medium": 2, "low": 3}
    subject_progress = []
    for subj in sorted(data["subjects"], key=lambda s: roi_order.get(s["roi"], 2)):
        t_total = len(subj["topics"])
        t_done = sum(1 for t in subj["topics"] if t["status"] in ("completed", "mastered"))
        pct = round(t_done / t_total * 100) if t_total > 0 else 0
        subject_progress.append({
            "name": subj["name"], "color": subj["color"],
            "total": t_total, "done": t_done, "pct": pct,
        })

    # Lifecycle
    lifecycle = []
    for subj in data["subjects"]:
        for topic in subj["topics"]:
            if topic["status"] == "completed" and topic.get("completionDate"):
                progress = sum(1 for t in types if f"{topic['id']}_{t}" in data["completedRevisions"])
                lifecycle.append({
                    "id": topic["id"], "name": topic["name"],
                    "subjectName": subj["name"], "subjectColor": subj["color"],
                    "subjectId": subj["id"],
                    "completionDate": topic["completionDate"],
                    "progress": progress, "totalStages": len(types),
                })

    return jsonify({
        "stats": {
            "total": total, "notStarted": not_started, "learning": learning,
            "completed": completed, "mastered": mastered,
            "compliance": compliance, "totalDone": total_done,
            "totalExpected": total_expected, "overdue": overdue,
        },
        "revStats": rev_stats,
        "subjectProgress": subject_progress,
        "lifecycle": lifecycle,
    })


# ---- Topic detail (schedule + info) ----

@app.route("/api/subjects/<subj_id>/topics/<topic_id>/detail", methods=["GET"])
def api_topic_detail(subj_id, topic_id):
    data = load_data()
    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    topic = next((t for t in subj["topics"] if t["id"] == topic_id), None)
    if not topic:
        return jsonify({"error": "Topic not found"}), 404

    schedule = None
    if topic.get("completionDate"):
        resolved_schedules, _ = resolve_all_revision_schedules(data)
        schedule = resolved_schedules.get(topic["id"])
        if schedule:
            # Add done/overdue status to each step
            today = today_str()
            for key, rev in schedule.items():
                rev_key = f"{topic['id']}_{rev['type']}"
                rev["done"] = rev_key in data["completedRevisions"]
                rev["overdue"] = rev["date"] < today and not rev["done"]
                rev["isToday"] = rev["date"] == today

    # Compute timeline estimate for this topic
    timeline_result = estimate_all_timelines(data)
    topic_estimate = timeline_result["estimates"].get(topic["id"])

    return jsonify({
        "subject": {"id": subj["id"], "name": subj["name"], "color": subj["color"]},
        "topic": topic,
        "schedule": schedule,
        "estimate": topic_estimate,
        "today": today_str(),
    })


# ---- Export/Import ----

@app.route("/api/export", methods=["GET"])
def api_export():
    return send_file(DATA_FILE, as_attachment=True,
                     download_name=f"upsc_tracker_backup_{today_str()}.json")


@app.route("/api/import", methods=["POST"])
def api_import():
    body = request.get_json(force=True)
    if "subjects" not in body:
        return jsonify({"error": "Invalid data format"}), 400
    # Ensure required keys
    if "settings" not in body:
        body["settings"] = default_data()["settings"]
    if "intervals" not in body["settings"]:
        body["settings"]["intervals"] = {"r1": 1, "r3": 5, "r7": 14, "r30": 35}
    if "ntfy" not in body["settings"]:
        body["settings"]["ntfy"] = {"enabled": False, "topic": "", "server": "https://ntfy.sh"}
    if "completedRevisions" not in body:
        body["completedRevisions"] = {}
    if "completedPractice" not in body:
        body["completedPractice"] = {}
    if "cumulativeRevisions" not in body:
        body["cumulativeRevisions"] = {
            "sectionalBatches": [],
            "subjectRevisions": [],
            "pendingTopics": [],
        }
    save_data(body)

    total_subjects = len(body["subjects"])
    total_topics = sum(len(s.get("topics", [])) for s in body["subjects"])
    send_ntfy(
        "Data Imported",
        f"Successfully imported backup!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Subjects: {total_subjects}\n"
        f"Topics: {total_topics}\n"
        f"✓ Revisions: {len(body.get('completedRevisions', {}))}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"All data restored!",
        tags=["inbox_tray", "white_check_mark"],
        priority=3,
    )

    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    send_ntfy(
        "All Data Cleared",
        f"ALL study data has been erased!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Subjects: 0\n"
        f"Topics: 0\n"
        f"Revisions: 0\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Starting fresh. Let's go!",
        tags=["warning", "wastebasket"],
        priority=4,
    )
    save_data(default_data())
    return jsonify({"ok": True})


# =============================================================================
#  ROUTES — PROGRESSIVE TIME ESTIMATOR
# =============================================================================

@app.route("/api/timeline-estimate", methods=["GET"])
def api_timeline_estimate():
    """Return estimated timeline for all topics through the full pipeline."""
    data = load_data()
    result = estimate_all_timelines(data)
    return jsonify({
        "today": today_str(),
        **result,
    })


# =============================================================================
#  ROUTES — CUMULATIVE REVISION API
# =============================================================================

@app.route("/api/cumulative", methods=["GET"])
def api_cumulative():
    """Return all cumulative revision data with enriched details."""
    data = load_data()
    cum = data["cumulativeRevisions"]
    today = today_str()

    # Enrich sectional batches with subject/topic details
    enriched_batches = []
    for batch in cum["sectionalBatches"]:
        enriched = {**batch}
        # Add scheduling status
        for sess in enriched["sessions"]:
            sess["isPast"] = sess["scheduledDate"] < today
            sess["isThisWeekend"] = (
                sess["scheduledDate"] == get_next_saturday(today)
                or sess["scheduledDate"] == add_days(get_next_saturday(today), 1)
            )
            sess["isOverdue"] = sess["isPast"] and not sess["completed"]
        enriched_batches.append(enriched)

    # Enrich subject revisions
    enriched_subject = []
    for sr in cum["subjectRevisions"]:
        enriched = {**sr}
        # Find subject details
        subj = next((s for s in data["subjects"] if s["id"] == sr["subjectId"]), None)
        if subj:
            enriched["subjectColor"] = subj["color"]
            enriched["subjectROI"] = subj["roi"]
            enriched["topicCount"] = len(subj["topics"])
            enriched["masteredCount"] = sum(1 for t in subj["topics"] if t["status"] == "mastered")
        for sess in enriched["sessions"]:
            sess["isPast"] = sess["scheduledDate"] < today
            sess["isThisWeekend"] = (
                sess["scheduledDate"] == get_next_saturday(today)
                or sess["scheduledDate"] == add_days(get_next_saturday(today), 1)
            )
            sess["isOverdue"] = sess["isPast"] and not sess["completed"]
        enriched_subject.append(enriched)

    # Pending topics
    pending = cum["pendingTopics"]

    # Stats
    total_batches = len(cum["sectionalBatches"])
    total_subject_revs = len(cum["subjectRevisions"])
    upcoming_sessions = []
    for batch in cum["sectionalBatches"]:
        for sess in batch["sessions"]:
            if not sess["completed"] and sess["scheduledDate"] >= today:
                upcoming_sessions.append({
                    "type": "sectional",
                    "batchId": batch["id"],
                    "round": sess["round"],
                    "date": sess["scheduledDate"],
                    "topicCount": len(batch["topicIds"]),
                })
    for sr in cum["subjectRevisions"]:
        for sess in sr["sessions"]:
            if not sess["completed"] and sess["scheduledDate"] >= today:
                upcoming_sessions.append({
                    "type": "subject",
                    "subjectId": sr["subjectId"],
                    "subjectName": sr["subjectName"],
                    "round": sess["round"],
                    "date": sess["scheduledDate"],
                })
    upcoming_sessions.sort(key=lambda x: x["date"])

    return jsonify({
        "sectionalBatches": enriched_batches,
        "subjectRevisions": enriched_subject,
        "pendingTopics": pending,
        "upcomingSessions": upcoming_sessions[:10],
        "stats": {
            "totalBatches": total_batches,
            "totalSubjectRevisions": total_subject_revs,
            "pendingCount": len(pending),
            "upcomingCount": len(upcoming_sessions),
        },
        "today": today,
        "intervals": {
            "sectional": SECTIONAL_INTERVALS,
            "subject": SUBJECT_INTERVALS,
            "minBatch": MIN_BATCH_SIZE,
            "maxBatch": MAX_BATCH_SIZE,
        },
    })


@app.route("/api/cumulative/batch/<batch_id>/session/<int:round_num>/complete", methods=["POST"])
def api_complete_batch_session(batch_id, round_num):
    """Mark a sectional batch session as completed."""
    data = load_data()
    cum = data["cumulativeRevisions"]
    batch = next((b for b in cum["sectionalBatches"] if b["id"] == batch_id), None)
    if not batch:
        return jsonify({"error": "Batch not found"}), 404
    session = next((s for s in batch["sessions"] if s["round"] == round_num), None)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    session["completed"] = True
    session["completedAt"] = today_str()
    save_data(data)

    topic_names = [t["topicName"] for t in batch.get("topicDetails", [])]
    send_ntfy(
        f"Sectional Revision R{round_num} Complete!",
        f"Batch of {len(batch['topicIds'])} topics reviewed!\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f"Topics: {', '.join(topic_names[:5])}\\n"
        f"Round: {round_num}/3\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f"Cross-topic consolidation done!",
        tags=["white_check_mark", "brain"],
        priority=3,
    )
    return jsonify({"ok": True})


@app.route("/api/cumulative/batch/<batch_id>/session/<int:round_num>/uncomplete", methods=["POST"])
def api_uncomplete_batch_session(batch_id, round_num):
    """Unmark a sectional batch session."""
    data = load_data()
    cum = data["cumulativeRevisions"]
    batch = next((b for b in cum["sectionalBatches"] if b["id"] == batch_id), None)
    if not batch:
        return jsonify({"error": "Batch not found"}), 404
    session = next((s for s in batch["sessions"] if s["round"] == round_num), None)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    session["completed"] = False
    session["completedAt"] = None
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/cumulative/subject/<subj_id>/session/<int:round_num>/complete", methods=["POST"])
def api_complete_subject_session(subj_id, round_num):
    """Mark a subject-level revision session as completed."""
    data = load_data()
    cum = data["cumulativeRevisions"]
    sr = next((s for s in cum["subjectRevisions"] if s["subjectId"] == subj_id), None)
    if not sr:
        return jsonify({"error": "Subject revision not found"}), 404
    session = next((s for s in sr["sessions"] if s["round"] == round_num), None)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    session["completed"] = True
    session["completedAt"] = today_str()
    save_data(data)

    subj = next((s for s in data["subjects"] if s["id"] == subj_id), None)
    send_ntfy(
        f"Subject Revision R{round_num} Complete!",
        f"Full subject review done!\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f"Subject: {sr['subjectName']}\\n"
        f"Round: {round_num}/4\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f"Deep consolidation of entire subject!",
        tags=["trophy", "star"],
        priority=4,
        subject_topic=subj.get("ntfyTopic") if subj else None,
    )
    return jsonify({"ok": True})


@app.route("/api/cumulative/subject/<subj_id>/session/<int:round_num>/uncomplete", methods=["POST"])
def api_uncomplete_subject_session(subj_id, round_num):
    """Unmark a subject-level revision session."""
    data = load_data()
    cum = data["cumulativeRevisions"]
    sr = next((s for s in cum["subjectRevisions"] if s["subjectId"] == subj_id), None)
    if not sr:
        return jsonify({"error": "Subject revision not found"}), 404
    session = next((s for s in sr["sessions"] if s["round"] == round_num), None)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    session["completed"] = False
    session["completedAt"] = None
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/cumulative/force-batch", methods=["POST"])
def api_force_batch():
    """Manually create a batch from pending topics (even if < MIN_BATCH_SIZE)."""
    data = load_data()
    cum = data["cumulativeRevisions"]
    pending = cum["pendingTopics"]
    if len(pending) == 0:
        return jsonify({"error": "No pending topics to batch"}), 400

    occupied = get_occupied_weekends(data)
    batch_topics = pending[:MAX_BATCH_SIZE]
    cum["pendingTopics"] = pending[len(batch_topics):]
    batch = schedule_sectional_batch(today_str(), batch_topics, occupied)
    cum["sectionalBatches"].append(batch)
    save_data(data)
    return jsonify({"ok": True, "batch": batch})


@app.route("/api/cumulative/reschedule", methods=["POST"])
def api_reschedule_sessions():
    """Deconflict all cumulative sessions so no weekend is overloaded."""
    data = load_data()
    reschedule_conflicting_sessions(data)
    return jsonify({"ok": True})


# =============================================================================

if __name__ == "__main__":
    # One-time deconflict on startup: ensure no weekend is double-booked
    _startup_data = load_data()
    reschedule_conflicting_sessions(_startup_data)
    del _startup_data

    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n  UPSC Tracker running!")
    print(f"     Local:   http://127.0.0.1:5000")
    print(f"     Network: http://{local_ip}:5000")
    print(f"     Login:   kishore / ****\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
