import argparse
import csv
import hashlib
import io
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

try:
    import streamlit as st
except ImportError:
    st = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LEADERBOARD_PATH = DATA_DIR / "leaderboard.json"
HISTORY_PATH = DATA_DIR / "history.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CodingPlatformAnalytics")

FIELDS = [
    "email", "username", "roll_number", "year", "section", "branch",
    "codolio_handle", "leetcode_handle", "codeforces_handle",
    "codechef_handle", "gfg_handle", "github_handle",
]


@dataclass
class StudentProfile:
    email: str = ""
    username: str = ""
    roll_number: str = ""
    year: str = ""
    section: str = ""
    branch: str = ""
    codolio_handle: str = ""
    leetcode_handle: str = ""
    codeforces_handle: str = ""
    codechef_handle: str = ""
    gfg_handle: str = ""
    github_handle: str = ""


@dataclass
class CodingMetrics:
    email: str
    username: str
    roll_number: str
    year: str
    section: str
    branch: str
    codolio_handle: str = ""
    leetcode_handle: str = ""
    codeforces_handle: str = ""
    codechef_handle: str = ""
    gfg_handle: str = ""
    github_handle: str = ""
    total_solved: int = 0
    easy_solved: int = 0
    medium_solved: int = 0
    hard_solved: int = 0
    leetcode_rating: int = 0
    codeforces_rating: int = 0
    codechef_rating: int = 0
    contest_rating: int = 0
    active_days: int = 0
    current_streak: int = 0
    leetcode_score: float = 0.0
    codeforces_score: float = 0.0
    codechef_score: float = 0.0
    gfg_score: float = 0.0
    codolio_score: float = 0.0
    best_platform_score: float = 0.0
    average_platform_score: float = 0.0
    rank_score: float = 0.0
    github_public_repos: int = 0
    github_followers: int = 0
    rank: int = 0
    sync_status: str = "Pending"
    errors: str = ""
    last_synced: str = ""


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def int_value(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


class DirectPlatformClient:
    @staticmethod
    def fetch_codeforces(handle: str) -> Dict[str, int]:
        if not handle:
            return {"rating": 0}
        try:
            r = requests.get(
                "https://codeforces.com/api/user.info",
                params={"handles": handle},
                timeout=10,
            )
            if r.ok:
                result = (r.json() or {}).get("result") or []
                if result:
                    return {"rating": int_value(result[0].get("rating"))}
        except requests.RequestException as e:
            logger.warning("Codeforces %s: %s", handle, e)
        return {"rating": 0}

    @staticmethod
    def fetch_leetcode(handle: str) -> Dict[str, int]:
        empty = {"easy": 0, "medium": 0, "hard": 0, "total": 0, "rating": 0}
        if not handle:
            return empty
        query = """
        query getUserProfile($username: String!) {
          matchedUser(username: $username) {
            submitStatsGlobal {
              acSubmissionNum { difficulty count }
            }
          }
          userContestRanking(username: $username) { rating }
        }
        """
        try:
            r = requests.post(
                "https://leetcode.com/graphql",
                json={"query": query, "variables": {"username": handle}},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=12,
            )
            if r.ok:
                body = r.json() or {}
                data = body.get("data") or {}
                user = data.get("matchedUser") or {}
                stats = (user.get("submitStatsGlobal") or {}).get("acSubmissionNum") or []
                counts = {clean(x.get("difficulty")).lower(): int_value(x.get("count")) for x in stats}
                ranking = data.get("userContestRanking") or {}
                return {
                    "easy": counts.get("easy", 0),
                    "medium": counts.get("medium", 0),
                    "hard": counts.get("hard", 0),
                    "total": counts.get("all", 0),
                    "rating": int_value(ranking.get("rating")),
                }
        except requests.RequestException as e:
            logger.warning("LeetCode %s: %s", handle, e)
        return empty


class GitHubClient:
    """Official GitHub REST API adapter for public profile/portfolio metadata."""

    def __init__(self, token: Optional[str] = None):
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "University-Coding-Platform-Analytics/2.0",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def fetch_profile(self, handle: str) -> Dict[str, int]:
        if not handle:
            return {"public_repos": 0, "followers": 0}
        try:
            r = requests.get(
                f"https://api.github.com/users/{handle}",
                headers=self.headers,
                timeout=10,
            )
            if r.ok:
                data = r.json() or {}
                return {
                    "public_repos": int_value(data.get("public_repos")),
                    "followers": int_value(data.get("followers")),
                }
        except requests.RequestException as e:
            logger.warning("GitHub %s: %s", handle, e)
        return {"public_repos": 0, "followers": 0}


class CodolioClient:
    def __init__(self, token: Optional[str] = None):
        self.headers = {
            "User-Agent": "CodingPlatformAnalytics/1.0",
            "Accept": "application/json, text/plain, */*",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def fetch_profile(self, handle: str) -> Optional[Dict[str, Any]]:
        if not handle:
            return None
        try:
            r = requests.get(
                f"https://api.codolio.com/user/public/{handle}",
                headers=self.headers,
                timeout=15,
            )
            if r.ok:
                return (r.json() or {}).get("data") or {}
        except requests.RequestException as e:
            logger.warning("Codolio %s: %s", handle, e)
        return None


class MetricsAggregator:
    def __init__(self):
        self.codolio = CodolioClient(os.getenv("CODOLIO_API_TOKEN"))
        self.github = GitHubClient(os.getenv("GITHUB_TOKEN"))

    @staticmethod
    def _platform_rating(name: str, platform: Dict[str, Any]) -> int:
        return int_value(platform.get("currentRating") or platform.get("rating"))

    def process(self, s: StudentProfile) -> CodingMetrics:
        now = datetime.now(timezone.utc).isoformat()
        errors = []
        easy = medium = hard = 0
        active_days = streak = 0
        lc_rating = cf_rating = cc_rating = 0
        platform_scores = {"leetcode": 0.0, "codeforces": 0.0, "codechef": 0.0, "gfg": 0.0, "codolio": 0.0}
        status = "Pending"

        codolio = self.codolio.fetch_profile(s.codolio_handle)
        if codolio:
            wrapper = codolio.get("platformProfiles") or {}
            profiles = wrapper.get("platformProfiles") or []

            for p in profiles:
                if not isinstance(p, dict):
                    continue
                stats = p.get("totalQuestionStats") or {}
                pe = int_value(stats.get("easyQuestionCounts")) + int_value(stats.get("basicQuestionCounts"))
                pm = int_value(stats.get("mediumQuestionCounts"))
                ph = int_value(stats.get("hardQuestionCounts"))
                pr = self._platform_rating("", p)
                pname = clean(p.get("platform") or p.get("name")).lower()

                ps = pe * 1.0 + pm * 3.0 + ph * 5.0 + pr * 0.5
                if "leetcode" in pname:
                    platform_scores["leetcode"] = max(platform_scores["leetcode"], ps)
                    lc_rating = max(lc_rating, pr)
                elif "codeforces" in pname:
                    platform_scores["codeforces"] = max(platform_scores["codeforces"], ps)
                    cf_rating = max(cf_rating, pr)
                elif "codechef" in pname:
                    platform_scores["codechef"] = max(platform_scores["codechef"], ps)
                    cc_rating = max(cc_rating, pr)
                elif "gfg" in pname or "geeks" in pname:
                    platform_scores["gfg"] = max(platform_scores["gfg"], ps)
                else:
                    platform_scores["codolio"] = max(platform_scores["codolio"], ps)

                easy += pe
                medium += pm
                hard += ph

            active_days = int_value(codolio.get("activeDays"))
            streak = int_value(codolio.get("currentStreak") or codolio.get("streak"))
            status = "Codolio-Synced"
        else:
            lc = DirectPlatformClient.fetch_leetcode(s.leetcode_handle)
            cf = DirectPlatformClient.fetch_codeforces(s.codeforces_handle)
            easy, medium, hard = lc["easy"], lc["medium"], lc["hard"]
            lc_rating, cf_rating = lc["rating"], cf["rating"]
            platform_scores["leetcode"] = lc["easy"] * 1.0 + lc["medium"] * 3.0 + lc["hard"] * 5.0 + lc["rating"] * 0.5
            platform_scores["codeforces"] = cf["rating"] * 0.5
            if easy + medium + hard + lc_rating + cf_rating:
                status = "Direct-Synced"
            else:
                status = "Pending / Missing"
                errors.append("Codolio unavailable and direct fallback returned no metrics")

        # A platform score is kept per platform. Best and average are exposed
        # separately; the institutional leaderboard uses the best platform score
        # plus consistency bonus, avoiding double-counting every platform.
        declared_scores = [v for k, v in platform_scores.items() if k != "codolio" and v > 0]
        if platform_scores["codolio"] > 0:
            declared_scores.append(platform_scores["codolio"])

        best_score = max(declared_scores, default=0.0)
        average_score = sum(declared_scores) / len(declared_scores) if declared_scores else 0.0
        total = easy + medium + hard
        consistency_bonus = min(active_days, 365) * 0.25
        rank_score = best_score + consistency_bonus

        gh = self.github.fetch_profile(s.github_handle)

        return CodingMetrics(
            **{k: getattr(s, k) for k in [
                "email", "username", "roll_number", "year", "section", "branch",
                "codolio_handle", "leetcode_handle", "codeforces_handle",
                "codechef_handle", "gfg_handle", "github_handle"
            ]},
            total_solved=total,
            easy_solved=easy,
            medium_solved=medium,
            hard_solved=hard,
            leetcode_rating=lc_rating,
            codeforces_rating=cf_rating,
            codechef_rating=cc_rating,
            contest_rating=max(lc_rating, cf_rating, cc_rating),
            active_days=active_days,
            current_streak=streak,
            leetcode_score=round(platform_scores["leetcode"], 2),
            codeforces_score=round(platform_scores["codeforces"], 2),
            codechef_score=round(platform_scores["codechef"], 2),
            gfg_score=round(platform_scores["gfg"], 2),
            codolio_score=round(platform_scores["codolio"], 2),
            best_platform_score=round(best_score, 2),
            average_platform_score=round(average_score, 2),
            rank_score=round(rank_score, 2),
            github_public_repos=gh["public_repos"],
            github_followers=gh["followers"],
            sync_status=status,
            errors="; ".join(errors),
            last_synced=now,
        )



class DataPipeline:
    def __init__(self, input_csv="usernames.csv", sheet_url=None):
        self.input_csv = BASE_DIR / input_csv
        self.sheet_url = sheet_url or os.getenv("GOOGLE_SHEET_CSV_URL")
        self.aggregator = MetricsAggregator()
        self.source_status = {}
        self.merge_conflicts = []

    @staticmethod
    def _row_to_student(row: Dict[str, Any]) -> StudentProfile:
        codolio = clean(row.get("codolio_handle") or row.get("codolio_username"))
        return StudentProfile(
            email=clean(row.get("email")),
            username=clean(row.get("username")),
            roll_number=clean(row.get("roll_number")),
            year=clean(row.get("year")),
            section=clean(row.get("section")),
            branch=clean(row.get("branch")),
            codolio_handle=codolio,
            leetcode_handle=clean(row.get("leetcode_handle")),
            codeforces_handle=clean(row.get("codeforces_handle")),
            codechef_handle=clean(row.get("codechef_handle")),
            gfg_handle=clean(row.get("gfg_handle")),
            github_handle=clean(row.get("github_handle")),
        )

    @staticmethod
    def _identity(student: StudentProfile) -> str:
        # Email is strongest; roll number is the fallback institutional key.
        return clean(student.email).lower() or f"roll:{clean(student.roll_number).lower()}"

    def _load_csv_source(self) -> List[StudentProfile]:
        if not self.input_csv.exists():
            self.source_status["usernames.csv"] = "missing"
            return []
        try:
            with self.input_csv.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            missing = validate_student_source_columns([x.strip() for x in (rows[0].keys() if rows else [])])
            if missing:
                raise ValueError("Missing required student columns: " + ", ".join(missing))
            students = [
                self._row_to_student(row)
                for row in rows
                if any(clean(v) for v in row.values())
            ]
            self.source_status["usernames.csv"] = f"loaded:{len(students)}"
            return students
        except Exception as exc:
            self.source_status["usernames.csv"] = f"error:{exc}"
            logger.exception("Failed to load usernames.csv")
            return []

    def _load_sheet_source(self) -> List[StudentProfile]:
        if not self.sheet_url:
            self.source_status["google_sheet"] = "not_configured"
            return []
        try:
            r = requests.get(self.sheet_url, timeout=20)
            r.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(r.text)))
            missing = validate_student_source_columns(list(rows[0].keys()) if rows else [])
            if missing:
                raise ValueError("Missing required student columns: " + ", ".join(missing))
            students = [
                self._row_to_student(row)
                for row in rows
                if any(clean(v) for v in row.values())
            ]
            self.source_status["google_sheet"] = f"loaded:{len(students)}"
            return students
        except requests.RequestException as exc:
            self.source_status["google_sheet"] = f"error:{exc}"
            logger.warning("Google Sheet unavailable: %s", exc)
            return []

    def load_students(self) -> List[StudentProfile]:
        """
        Always evaluates BOTH sources before analytics starts.

        There is intentionally no fixed 'Google Sheet wins' or
        'CSV wins' rule because neither source is guaranteed to be newer.
        Records are merged by institutional identity. Non-conflicting fields
        are combined. Conflicting non-empty fields are recorded and the
        Google Sheet value is used as the deterministic runtime value while
        the conflict is surfaced in analytics.
        """
        csv_students = self._load_csv_source()
        sheet_students = self._load_sheet_source()

        merged: Dict[str, StudentProfile] = {}
        source_map: Dict[str, set] = {}

        def merge_one(student: StudentProfile, source: str):
            key = self._identity(student)
            if not key or key == "roll:":
                # No usable identity: retain as a distinct generated key.
                key = f"{source}:anonymous:{len(merged) + 1}"

            if key not in merged:
                merged[key] = student
                source_map[key] = {source}
                return

            existing = merged[key]
            source_map[key].add(source)
            conflicts = []

            for field_name in FIELDS:
                a = clean(getattr(existing, field_name, ""))
                b = clean(getattr(student, field_name, ""))
                if not b:
                    continue
                if not a:
                    setattr(existing, field_name, b)
                elif a != b:
                    conflicts.append(field_name)

            if conflicts:
                self.merge_conflicts.append({
                    "identity": key,
                    "fields": conflicts,
                    "source_values": source,
                    "resolution": "google_sheet_preferred_for_conflicting_values"
                })

                # Since freshness cannot be established from CSV exports,
                # use the Sheet value deterministically when it conflicts.
                if source == "google_sheet":
                    for field_name in conflicts:
                        setattr(existing, field_name, getattr(student, field_name))

        # Load both sources first, then merge. Order is deliberately explicit.
        for student in csv_students:
            merge_one(student, "usernames.csv")
        for student in sheet_students:
            merge_one(student, "google_sheet")

        self.source_status["merged_students"] = f"{len(merged)}"
        self.source_status["conflicts"] = f"{len(self.merge_conflicts)}"
        return list(merged.values())

    @staticmethod
    def rank(items: List[CodingMetrics]) -> List[CodingMetrics]:
        items.sort(
            key=lambda x: (
                x.rank_score, x.total_solved, x.hard_solved,
                x.medium_solved, x.active_days
            ),
            reverse=True,
        )
        for i, item in enumerate(items, 1):
            item.rank = i
        return items

    def run(self, students: Optional[List[StudentProfile]] = None) -> List[CodingMetrics]:
        students = self.load_students() if students is None else students
        results = self.rank([self.aggregator.process(s) for s in students])
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = {
            "schema_version": 3,
            "last_updated": timestamp,
            "total_students": len(results),
            "source_status": self.source_status,
            "merge_conflicts": self.merge_conflicts,
            "leaderboard": [asdict(x) for x in results],
        }
        LEADERBOARD_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        history = []
        if HISTORY_PATH.exists():
            try:
                history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                history = []
        history.append({
            "timestamp": timestamp,
            "records": [{
                "roll_number": x.roll_number,
                "rank": x.rank,
                "total_solved": x.total_solved,
                "easy_solved": x.easy_solved,
                "medium_solved": x.medium_solved,
                "hard_solved": x.hard_solved,
                "rank_score": x.rank_score,
                "leetcode_rating": x.leetcode_rating,
                "codeforces_rating": x.codeforces_rating,
                "codechef_rating": x.codechef_rating,
                "active_days": x.active_days,
                "current_streak": x.current_streak,
            } for x in results],
        })
        HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
        return results


def snapshot_exists() -> bool:
    return LEADERBOARD_PATH.exists() and LEADERBOARD_PATH.stat().st_size > 0


def initialize_first_run(sheet_url: Optional[str] = None) -> tuple[bool, str]:
    """Bootstrap the dashboard once when no leaderboard snapshot exists."""
    if snapshot_exists():
        return True, "existing"

    try:
        pipeline = DataPipeline(sheet_url=sheet_url)
        students = pipeline.load_students()
        if not students:
            return False, "no_students"

        pipeline.run()
        if snapshot_exists():
            return True, "synced"
        return False, "sync_no_snapshot"
    except Exception as exc:
        logger.exception("Initial synchronization failed")
        return False, f"failed:{exc}"


DASHBOARD_DEFAULTS = {
    "mentor_id": "", "mentor_name": "", "mentor_email": "",
    "mentee_status": "Unassigned",
    "sync_status": "Unknown",
    "best_platform_score": 0.0, "average_platform_score": 0.0,
    "total_solved": 0, "easy_solved": 0, "medium_solved": 0, "hard_solved": 0,
    "contest_rating": 0, "rank_score": 0.0, "rank": 0,
    "leetcode_rating": 0, "codeforces_rating": 0, "codechef_rating": 0,
    "active_days": 0, "current_streak": 0,
    "leetcode_score": 0.0, "codeforces_score": 0.0,
    "codechef_score": 0.0, "gfg_score": 0.0, "codolio_score": 0.0,
    "github_public_repos": 0, "github_followers": 0,
    "codolio_handle": "", "leetcode_handle": "", "codeforces_handle": "",
    "codechef_handle": "", "gfg_handle": "", "github_handle": "",
    "errors": "", "last_synced": "",
}


def normalize_dashboard_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize current and legacy leaderboard snapshots to one stable schema."""
    df = df.copy()

    # Legacy snapshots used `status` for coding synchronization.
    if "sync_status" not in df.columns:
        if "status" in df.columns:
            df["sync_status"] = df["status"]
        else:
            df["sync_status"] = DASHBOARD_DEFAULTS["sync_status"]

    # Never use the ambiguous legacy field inside the dashboard.
    if "status" in df.columns:
        df = df.drop(columns=["status"])

    for column, default in DASHBOARD_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default

    numeric = [
        "rank", "total_solved", "easy_solved", "medium_solved", "hard_solved",
        "contest_rating", "active_days", "current_streak",
        "leetcode_rating", "codeforces_rating", "codechef_rating",
        "github_public_repos", "github_followers",
        "best_platform_score", "average_platform_score", "rank_score",
        "leetcode_score", "codeforces_score", "codechef_score",
        "gfg_score", "codolio_score",
    ]
    for column in numeric:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    text_columns = [
        c for c in DASHBOARD_DEFAULTS
        if c not in numeric
    ]
    for column in text_columns:
        df[column] = df[column].fillna("").astype(str)

    return df


def load_df() -> pd.DataFrame:
    if not LEADERBOARD_PATH.exists():
        return pd.DataFrame()
    try:
        payload = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
        records = payload.get("leaderboard", [])
        return normalize_dashboard_df(pd.DataFrame(records))
    except (OSError, json.JSONDecodeError, TypeError):
        logger.exception("Unable to load leaderboard snapshot")
        return pd.DataFrame()


MENTEE_MAP_PATH = DATA_DIR / "mentor_mentees.csv"


MENTORS_PATH = DATA_DIR / "mentors.csv"
ACCESS_REGISTRY_PATH = DATA_DIR / "access_registry.csv"
EVENTS_PATH = DATA_DIR / "events.csv"
ANNOUNCEMENTS_PATH = DATA_DIR / "announcements.csv"
INTERVENTIONS_PATH = DATA_DIR / "interventions.csv"
STUDENT_UPDATES_PATH = DATA_DIR / "student_updates.csv"

ROLE_LABELS = {
    "admin": "Administrator", "hod": "HOD", "faculty_coordinator": "Faculty Coordinator",
    "mentor": "Mentor", "student_coordinator": "Student Coordinator",
    "placement_officer": "Placement Officer", "student": "Student",
}

FULL_ACCESS_ROLES = {"admin", "hod", "faculty_coordinator"}
OPERATIONS_ROLES = {"admin", "faculty_coordinator", "student_coordinator"}


def load_table(path: Path, columns: List[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        result = pd.read_csv(path, dtype=str).fillna("")
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in result.columns:
            result[column] = ""
    return result[columns]


def append_table_row(path: Path, columns: List[str], row: Dict[str, Any]) -> None:
    table = load_table(path, columns)
    table = pd.concat([table, pd.DataFrame([{key: clean(row.get(key)) for key in columns}])], ignore_index=True)
    table.to_csv(path, index=False)


def load_access_registry() -> pd.DataFrame:
    return load_table(ACCESS_REGISTRY_PATH, ["login_id", "password", "password_hash", "display_name", "role", "email", "roll_number", "department"])


def password_digest(password: str) -> str:
    """PBKDF2 is used for newly registered local accounts; legacy demo rows still work."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b"campuscode-local-v1", 200_000).hex()


def password_matches(account: pd.Series, password: str) -> bool:
    stored_hash = clean(account.get("password_hash"))
    password = clean(password)
    return password_digest(password) == stored_hash if stored_hash else password == clean(account.get("password"))


def authenticate_account(registry: pd.DataFrame, email: str, password: str) -> Optional[Dict[str, str]]:
    """Single source of truth for both email and pre-approved staff sign-in."""
    email = clean(email).lower()
    matched = registry[registry["email"].astype(str).str.strip().str.lower() == email]
    if matched.empty or not password_matches(matched.iloc[0], password):
        return None
    return matched.iloc[0].to_dict()


def register_student_account(email: str, password: str, name: str, roll_number: str, branch: str) -> tuple[bool, str]:
    """Register a single Student account per email. Authority roles cannot self-register."""
    email = email.strip().lower()
    registry = load_access_registry()
    if not email or "@" not in email:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Use a password with at least 8 characters."
    if not clean(name):
        return False, "Enter your name."
    registered_emails = registry["email"].astype(str).str.strip().str.lower()
    login_ids = registry["login_id"].astype(str).str.strip().str.lower()
    if email in set(registered_emails) or email in set(login_ids):
        return False, "This email already has an account. Please sign in instead."
    append_table_row(ACCESS_REGISTRY_PATH,
                     ["login_id", "password", "password_hash", "display_name", "role", "email", "roll_number", "department"],
                     {"login_id": email, "password": "", "password_hash": password_digest(password), "display_name": name.strip(), "role": "student", "email": email, "roll_number": roll_number.strip(), "department": branch.strip()})
    return True, "Account created. You can now sign in with this email."


def risk_details(row: pd.Series) -> Dict[str, Any]:
    """Transparent, explainable early-warning score; it is not a disciplinary decision."""
    score, signals = 0, []
    solved = int_value(row.get("total_solved"))
    active_days = int_value(row.get("active_days"))
    streak = int_value(row.get("current_streak"))
    rating = int_value(row.get("contest_rating"))
    repos = int_value(row.get("github_public_repos"))
    if solved < 10:
        score += 30; signals.append("Very low solved-problem count")
    elif solved < 30:
        score += 15; signals.append("Low solved-problem count")
    if active_days < 5:
        score += 25; signals.append("Limited coding activity")
    elif active_days < 12:
        score += 12; signals.append("Inconsistent coding activity")
    if streak == 0:
        score += 15; signals.append("No current coding streak")
    if rating < 900:
        score += 15; signals.append("Low contest readiness")
    if repos == 0:
        score += 10; signals.append("No visible GitHub portfolio")
    score = min(score, 100)
    status = "At risk" if score >= 60 else "Needs attention" if score >= 30 else "On track"
    return {"risk_score": score, "risk_status": status, "signals": signals or ["Healthy engagement signals"]}


def with_risk(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    details = output.apply(risk_details, axis=1)
    output["risk_score"] = details.apply(lambda x: x["risk_score"])
    output["risk_status"] = details.apply(lambda x: x["risk_status"])
    output["risk_signals"] = details.apply(lambda x: "; ".join(x["signals"]))
    return output


def load_mentors() -> pd.DataFrame:
    if not MENTORS_PATH.exists():
        return pd.DataFrame(columns=["mentor_id", "mentor_name", "mentor_email", "department"])
    return pd.read_csv(MENTORS_PATH, dtype=str).fillna("")


MENTEE_MAP_COLUMNS = [
    "mentor_id", "mentor_name", "mentor_email",
    "student_email", "roll_number", "mentee_status", "updated_at"
]


def load_mentee_map() -> pd.DataFrame:
    if not MENTEE_MAP_PATH.exists():
        return pd.DataFrame(columns=MENTEE_MAP_COLUMNS)

    try:
        mapping = pd.read_csv(MENTEE_MAP_PATH, dtype=str).fillna("")
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=MENTEE_MAP_COLUMNS)

    # Migrate old mentor assignment files that used `status`.
    if "mentee_status" not in mapping.columns and "status" in mapping.columns:
        mapping["mentee_status"] = mapping["status"]

    for column in MENTEE_MAP_COLUMNS:
        if column not in mapping.columns:
            mapping[column] = ""

    return mapping[MENTEE_MAP_COLUMNS].fillna("")


def merge_mentor_mappings(df: pd.DataFrame) -> pd.DataFrame:
    mapping = load_mentee_map()
    out = normalize_dashboard_df(df)

    out["mentor_id"] = ""
    out["mentor_name"] = ""
    out["mentor_email"] = ""
    out["mentee_status"] = "Unassigned"

    if mapping.empty or "email" not in out.columns:
        return out

    mapping["student_email"] = (
        mapping["student_email"].astype(str).str.strip().str.lower()
    )
    out["_identity_email"] = (
        out["email"].astype(str).str.strip().str.lower()
    )

    mapping = mapping[mapping["student_email"].ne("")]
    mapping = mapping.drop_duplicates(subset=["student_email"], keep="last")

    if mapping.empty:
        return out.drop(columns=["_identity_email"], errors="ignore")

    assignment = mapping[
        ["student_email", "mentor_id", "mentor_name", "mentor_email", "mentee_status"]
    ].copy()

    out = out.merge(
        assignment,
        left_on="_identity_email",
        right_on="student_email",
        how="left",
        suffixes=("", "_mapping"),
    )

    for column in ["mentor_id", "mentor_name", "mentor_email", "mentee_status"]:
        mapped = out[f"{column}_mapping"].fillna("").astype(str).str.strip()
        out[column] = mapped.where(mapped.ne(""), out[column])

    return out.drop(
        columns=[
            "_identity_email", "student_email",
            "mentor_id_mapping", "mentor_name_mapping",
            "mentor_email_mapping", "mentee_status_mapping",
        ],
        errors="ignore",
    )


def save_mentee_map(df: pd.DataFrame) -> None:
    MENTEE_MAP_PATH.parent.mkdir(exist_ok=True)
    df = df.copy()

    # Accept legacy `status` input, but persist only `mentee_status`.
    if "mentee_status" not in df.columns and "status" in df.columns:
        df["mentee_status"] = df["status"]
    if "status" in df.columns:
        df = df.drop(columns=["status"])

    for column in MENTEE_MAP_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df[MENTEE_MAP_COLUMNS].to_csv(MENTEE_MAP_PATH, index=False)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")
    search = st.sidebar.text_input("Search email / roll / name", "")
    def options(col):
        vals = sorted([clean(v) for v in df[col].dropna().unique() if clean(v)])
        return ["All"] + vals
    branch = st.sidebar.selectbox("Branch", options("branch"))
    year = st.sidebar.selectbox("Year", options("year"))
    section = st.sidebar.selectbox("Section", options("section"))
    mentor_values = ["All"] + sorted([clean(v) for v in df["mentor_name"].dropna().unique() if clean(v)])
    mentor = st.sidebar.selectbox("Mentor", mentor_values)

    out = df.copy()
    if search:
        mask = False
        for c in ["email", "roll_number", "username"]:
            mask = mask | out[c].astype(str).str.contains(search, case=False, na=False)
        out = out[mask]
    for col, val in [("branch", branch), ("year", year), ("section", section)]:
        if val != "All":
            out = out[out[col] == val]
    if mentor != "All":
        out = out[out["mentor_name"] == mentor]
    return out


def overview(df):
    st.subheader("🏆 Leaderboard")
    if df.empty:
        st.info("No records.")
        return
    top_default = min(10, len(df))
    top_n = st.slider("Top N", 1, len(df), top_default)
    shown = df.head(top_n).copy()
    columns = [
        "rank", "roll_number", "username", "year", "section", "branch", "mentor_name", "mentee_status",
        "best_platform_score", "average_platform_score", "total_solved", "easy_solved", "medium_solved", "hard_solved",
        "contest_rating", "rank_score", "sync_status"
    ]
    columns = [c for c in columns if c in shown.columns]
    st.dataframe(shown[columns], use_container_width=True, hide_index=True)


def analytics(df):
    st.subheader("📊 Analytics")
    if df.empty:
        return
    top_n = st.slider("Analytics Top N", 1, len(df), min(10, len(df)), key="analytics_top")
    top = df.head(top_n).set_index("username")[["easy_solved", "medium_solved", "hard_solved"]]
    st.bar_chart(top)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Average Score by Branch")
        st.bar_chart(df.groupby("branch")["rank_score"].mean().sort_values(ascending=False))
    with c2:
        st.markdown("### Average Solved by Year")
        st.bar_chart(df.groupby("year")["total_solved"].mean().sort_values(ascending=False))

    st.markdown("### Section Summary")
    summary = df.groupby(["branch", "year", "section"]).agg(
        Students=("username", "count"),
        Avg_Solved=("total_solved", "mean"),
        Avg_Score=("rank_score", "mean"),
        Max_Rating=("contest_rating", "max"),
    ).round(2)
    st.dataframe(summary, use_container_width=True)

    st.markdown("### Mentor / Faculty Summary")
    mentor_summary = df.groupby("mentor_name").agg(
        Students=("username", "count"),
        Avg_Score=("rank_score", "mean"),
        Avg_Solved=("total_solved", "mean"),
        Best_Score=("best_platform_score", "max"),
    ).round(2).sort_values("Avg_Score", ascending=False)
    st.dataframe(mentor_summary, use_container_width=True)


def profile(df):
    st.subheader("👤 Student Profile")
    if df.empty:
        return
    selected = st.selectbox("Student", df["username"].tolist())
    row = df[df["username"] == selected].iloc[0]
    st.write(f"**{row['username']}** — `{row['roll_number']}` — {row['branch']} / {row['year']} / {row['section']}")
    st.write(f"**Mentor/Faculty:** {row.get('mentor_name') or 'Unassigned'}")
    cols = st.columns(5)
    for col, name in zip(cols, ["codolio_handle", "leetcode_handle", "codeforces_handle", "codechef_handle", "github_handle"]):
        col.metric(name.replace("_handle", "").title(), row.get(name) or "—")
    st.divider()
    st.dataframe(pd.DataFrame([{
        "Easy": row["easy_solved"], "Medium": row["medium_solved"], "Hard": row["hard_solved"],
        "Total": row["total_solved"], "LeetCode Rating": row["leetcode_rating"],
        "Codeforces Rating": row["codeforces_rating"], "CodeChef Rating": row["codechef_rating"],
        "Active Days": row["active_days"], "Streak": row["current_streak"],
        "LeetCode Score": row["leetcode_score"], "Codeforces Score": row["codeforces_score"],
        "CodeChef Score": row["codechef_score"], "GFG Score": row["gfg_score"],
        "Best Platform Score": row["best_platform_score"], "Average Platform Score": row["average_platform_score"],
        "GitHub Repos": row["github_public_repos"], "GitHub Followers": row["github_followers"],
        "Score": row.get("rank_score", 0), "Rank": row.get("rank", 0), "Sync Status": row.get("sync_status", "Unknown")
    }]), use_container_width=True, hide_index=True)


def mentor_dashboard(df):
    st.subheader("👨‍🏫 Mentor Dashboard")
    if df.empty:
        st.info("No student profiles available.")
        return

    assigned = df[df["mentor_name"].astype(str).str.strip() != ""].copy()
    mentors = sorted([clean(x) for x in assigned["mentor_name"].unique() if clean(x)])
    if not mentors:
        st.info("No mentee assignments have been created yet.")
        return

    mentor = st.selectbox("Mentor / Faculty", mentors, key="mentor_dashboard")
    mentees = assigned[assigned["mentor_name"] == mentor].copy()

    a, b, c = st.columns(3)
    a.metric("Mentees", len(mentees))
    b.metric("Average Score", f"{mentees['rank_score'].mean():.1f}")
    c.metric("Best Score", f"{mentees['rank_score'].max():.1f}")

    st.dataframe(
        mentees[[
            "rank", "username", "roll_number", "branch", "year", "section",
            "best_platform_score", "average_platform_score", "total_solved",
            "contest_rating", "github_public_repos", "sync_status"
        ]].sort_values("rank"),
        use_container_width=True,
        hide_index=True,
    )


def github_dashboard(df):
    st.subheader("💻 GitHub / Portfolio")

    if df.empty:
        st.info("No student profiles available.")
        return

    github_df = df.copy()
    github_df["github_handle"] = github_df["github_handle"].fillna("").astype(str).str.strip()

    available = github_df[github_df["github_handle"].ne("")].copy()
    if available.empty:
        st.info("No GitHub handles are available in the student profile data.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Students with GitHub", len(available))
    c2.metric("Public Repositories", int(available["github_public_repos"].sum()))
    c3.metric("Followers", int(available["github_followers"].sum()))

    display = available[[
        "rank", "username", "roll_number", "branch", "year", "section",
        "mentor_name", "github_handle", "github_public_repos",
        "github_followers", "best_platform_score", "average_platform_score"
    ]].copy()

    display["GitHub Profile"] = display["github_handle"].apply(
        lambda h: f"https://github.com/{h}"
    )

    st.dataframe(
        display.sort_values(
            ["github_public_repos", "github_followers"],
            ascending=[False, False]
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "GitHub Profile": st.column_config.LinkColumn(
                "GitHub Profile",
                display_text="Open GitHub"
            )
        }
    )

    st.caption(
        "GitHub is a development/portfolio signal and is intentionally kept "
        "separate from competitive-programming scores."
    )



def email_lookup(df):
    st.subheader("🔎 Email Lookup")
    st.caption("Email resolves through the institutional registry; it is not used to guess public platform identities.")
    email = st.text_input("Institutional email")
    if email:
        matches = df[df["email"].astype(str).str.lower() == email.strip().lower()]
        if matches.empty:
            st.warning("No registered student found for this email.")
        else:
            profile(df[df.index.isin(matches.index)])


def history_view(df):
    st.subheader("📈 Progress History")
    if not HISTORY_PATH.exists():
        st.info("No historical snapshots yet. Run at least two syncs.")
        return
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    rows = []
    for snapshot in history:
        for record in snapshot.get("records", []):
            rows.append({"timestamp": snapshot["timestamp"], **record})
    if not rows:
        st.info("No history records.")
        return
    h = pd.DataFrame(rows)
    roll = st.selectbox("Student Roll Number", sorted(h["roll_number"].unique()))
    student = h[h["roll_number"] == roll].copy()
    student["timestamp"] = pd.to_datetime(student["timestamp"])
    st.line_chart(student.set_index("timestamp")[["total_solved", "rank_score"]])
    st.dataframe(student.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)


def load_mentors() -> pd.DataFrame:
    path = BASE_DIR / "data" / "mentors.csv"
    if not path.exists():
        return pd.DataFrame(columns=["mentor_id", "mentor_name", "mentor_email", "department"])
    return pd.read_csv(path).fillna("")


def save_mentors(df: pd.DataFrame) -> None:
    path = BASE_DIR / "data" / "mentors.csv"
    df.to_csv(path, index=False)


def dataset_upload_workspace():
    """Let authorised staff replace the local registry with a JRS/Codolio export."""
    st.subheader("Upload AIML coding dataset")
    st.caption("Upload the student registry collected from JRS. The app uses each `codolio_handle` to collect linked LeetCode, CodeChef, Codeforces, HackerRank, GFG and other supported platform activity through Codolio.")
    template_path = BASE_DIR / "templates" / "universal_student_data_template.csv"
    if template_path.exists():
        st.download_button("Download upload template", template_path.read_bytes(), "aiml_coding_dataset_template.csv", "text/csv")
    upload = st.file_uploader("JRS / Codolio student dataset (CSV)", type=["csv"])
    if upload is None:
        return
    try:
        incoming = pd.read_csv(upload, dtype=str).fillna("")
    except (UnicodeDecodeError, pd.errors.ParserError):
        st.error("The uploaded file is not a readable CSV.")
        return
    missing = validate_student_source_columns(incoming.columns.tolist())
    if missing:
        st.error("Missing required columns: " + ", ".join(missing))
        return
    if "codolio_handle" not in incoming.columns and "codolio_username" in incoming.columns:
        incoming["codolio_handle"] = incoming["codolio_username"]
    for column in FIELDS:
        if column not in incoming.columns:
            incoming[column] = ""
    incoming["branch"] = "AIML"
    st.success(f"Dataset is valid: {len(incoming)} AIML student records.")
    st.dataframe(incoming[FIELDS].head(10), hide_index=True, use_container_width=True)
    if st.button("Replace registry and refresh leaderboard", type="primary"):
        incoming[FIELDS].to_csv(BASE_DIR / "usernames.csv", index=False)
        st.session_state["initial_sync_done"] = False
        st.success("AIML registry saved. The leaderboard will rebuild from Codolio/platform data now.")
        st.rerun()


def data_management(df):
    dataset_upload_workspace()
    st.divider()
    st.subheader("⚙️ Data Management")

    sheet = st.text_input("Student Google Sheets CSV URL", value=os.getenv("GOOGLE_SHEET_CSV_URL", ""))

    if st.button("🔄 Refresh Both Student Sources"):
        with st.spinner("Reading usernames.csv + Google Sheet and rebuilding analytics..."):
            try:
                DataPipeline(sheet_url=sheet or None).run()
                st.session_state["initial_sync_done"] = True
                st.success("Both student sources refreshed successfully.")
                st.rerun()
            except Exception as exc:
                logger.exception("Refresh failed")
                st.error(f"Refresh failed: {exc}")

    st.markdown("### Mentor / Mentee Mapping")
    st.caption(
        "Student profile data and mentor assignments are separate. "
        "Mentors can pick/update their mentees without changing student coding-platform data."
    )

    mentors = load_mentors()
    mapping = load_mentee_map()

    if not mentors.empty and not df.empty:
        st.markdown("#### Assign / Update Mentees")
        mentor_options = mentors["mentor_id"].tolist()
        mentor_id = st.selectbox("Mentor", mentor_options, format_func=lambda x: str(
            mentors.loc[mentors["mentor_id"] == x, "mentor_name"].iloc[0]
        ))
        mentor_row = mentors.loc[mentors["mentor_id"] == mentor_id].iloc[0]

        student_options = df["email"].dropna().astype(str).tolist()
        student_email = st.selectbox(
            "Student",
            student_options,
            format_func=lambda x: f"{df.loc[df['email'] == x, 'username'].iloc[0]} — {x}"
        )
        mentee_status = st.selectbox("Mentee Status", ["Active", "Released", "Pending"])

        if st.button("Save Mentee Assignment"):
            existing = mapping.copy()
            existing = existing[existing["student_email"].astype(str).str.lower() != student_email.lower()]
            new_row = pd.DataFrame([{
                "mentor_id": mentor_id,
                "mentor_name": mentor_row["mentor_name"],
                "mentor_email": mentor_row["mentor_email"],
                "student_email": student_email,
                "roll_number": str(df.loc[df["email"] == student_email, "roll_number"].iloc[0]),
                "mentee_status": mentee_status,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }])
            save_mentee_map(pd.concat([existing, new_row], ignore_index=True))
            st.success("Mentee assignment updated.")
            st.rerun()

    if mapping.empty:
        st.info("No mentee mappings exist yet.")
    else:
        st.dataframe(mapping, use_container_width=True, hide_index=True)

    if not df.empty:
        st.markdown("### Current Student Profiles")
        st.dataframe(
            df[[
                "email", "username", "roll_number", "year", "section", "branch",
                "mentor_name", "mentee_status",
                "codolio_handle", "leetcode_handle", "codeforces_handle",
                "codechef_handle", "gfg_handle", "github_handle"
            ]],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Download Student Profiles",
            df.to_csv(index=False).encode(),
            "student_profiles.csv",
            "text/csv",
        )

        if not mapping.empty:
            st.download_button(
                "Download Mentor-Mentee Mapping",
                mapping.to_csv(index=False).encode(),
                "mentor_mentees.csv",
                "text/csv",
            )


def validate_student_source_columns(columns: List[str]) -> List[str]:
    aliases = {"codolio_username"}
    required = {"email", "username", "roll_number", "year", "section", "branch"}
    available = set(columns)
    missing = sorted(required - available)
    if "codolio_handle" not in available and not (available & aliases):
        missing.append("codolio_handle (or legacy codolio_username)")
    return missing


def render_brand():
    st.markdown("""<style>
    .block-container {padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1440px;}
    [data-testid='stMetric'] {background: #ffffff; border: 1px solid #e6eaf0; border-radius: 14px; padding: 12px;}
    .eyebrow {color:#4f46e5; font-weight:700; letter-spacing:.08em; font-size:.78rem; text-transform:uppercase;}
    .hero {padding:1.25rem 0 .4rem;}
    .notice {padding:.8rem 1rem; background:#eef2ff; border-left:4px solid #4f46e5; border-radius:8px;}
    </style>""", unsafe_allow_html=True)


def public_landing():
    """Presentation homepage shown before a user enters the secured portal."""
    preview = load_df()
    students = len(preview)
    top = preview.head(4) if not preview.empty else pd.DataFrame()
    st.markdown("""<style>
    .stApp {background: radial-gradient(circle at 80% -10%, #20285a 0, #0b1020 38%, #070a12 100%); color:#f8fafc;}
    .stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3 {color:#f8fafc;}
    .block-container {max-width: 1280px; padding-top: 1.1rem;}
    .landing-nav {display:flex; justify-content:space-between; align-items:center; padding:8px 0 28px;}
    .landing-brand {font-size:1.35rem; font-weight:800; letter-spacing:-.03em;}
    .landing-brand span {color:#f59e0b;}.landing-links {color:#cbd5e1; font-weight:600; word-spacing:1.5rem;}
    .landing-pill {display:inline-block; border:1px solid #334155; border-radius:999px; padding:8px 16px; color:#bfdbfe; font-weight:700;}
    .landing-title {font-size:4.25rem; line-height:1.02; margin:22px 0 20px; font-weight:850; letter-spacing:-.06em;}
    .landing-copy {font-size:1.16rem; line-height:1.7; color:#b8c5dc; max-width:650px;}
    .platform {display:inline-block; border:1px solid #334155; border-radius:999px; padding:7px 12px; margin:8px 7px 0 0; font-size:.87rem; color:#dbeafe;}
    .preview-card {background:linear-gradient(150deg,#161d31,#101625); border:1px solid #2c3852; border-radius:18px; padding:24px; box-shadow:0 20px 55px #0005; margin-top:22px;}
    .preview-card h3 {margin:0;}.muted {color:#94a3b8!important;}.rank-row {display:grid; grid-template-columns:42px 1fr 75px; gap:8px; align-items:center; padding:12px; margin-top:8px; border:1px solid #283348; border-radius:10px; background:#111827;}.rank-score{color:#fbbf24; font-weight:800; text-align:right;}
    .proof {border-top:1px solid #293349; margin-top:48px; padding-top:28px;}.proof-item {font-size:2.2rem; font-weight:800; color:#f8fafc;}.proof-label{color:#94a3b8;}
    </style>""", unsafe_allow_html=True)
    st.markdown("""<div class='landing-nav'><div class='landing-brand'>Campus<span>Code</span> Intelligence</div><div class='landing-links'>Platform &nbsp; Leaderboard &nbsp; Insights &nbsp; Placement</div></div>""", unsafe_allow_html=True)
    left, right = st.columns([1.05, .95], gap="large")
    with left:
        st.markdown("<div class='landing-pill'>AIML Department · Anurag University</div>", unsafe_allow_html=True)
        st.markdown("<div class='landing-title'>Track every coder.<br>Build every future.</div>", unsafe_allow_html=True)
        st.markdown("<p class='landing-copy'>One institutional workspace for coding-platform performance, mentor action, contests, and placement readiness. Upload your JRS dataset, connect Codolio, and turn student activity into an explainable AIML leaderboard.</p>", unsafe_allow_html=True)
        st.markdown("<span class='platform'>LeetCode</span><span class='platform'>CodeChef</span><span class='platform'>Codeforces</span><span class='platform'>HackerRank</span><span class='platform'>GeeksforGeeks</span><span class='platform'>Codolio</span>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Open department portal →", type="primary", use_container_width=True):
                st.session_state["show_auth"] = True; st.rerun()
        with c2:
            if st.button("View platform story", use_container_width=True):
                st.info("Upload student handles, sync Codolio, analyse progress, identify top coders, and support placement readiness.")
    with right:
        rows = ""
        if top.empty:
            rows = "<div class='rank-row'><b>1</b><div>Upload your AIML dataset<br><span class='muted'>Leaderboard preview</span></div><span class='rank-score'>—</span></div>"
        else:
            for _, row in top.iterrows():
                rows += f"<div class='rank-row'><b>#{int_value(row.get('rank'))}</b><div><b>{clean(row.get('username'))}</b><br><span class='muted'>{clean(row.get('roll_number'))}</span></div><span class='rank-score'>{float(row.get('rank_score', 0)):.0f}</span></div>"
        st.markdown(f"<div class='preview-card'><h3>Department leaderboard</h3><p class='muted'>AIML · platform data, refreshed after sync</p>{rows}<p class='muted' style='margin-top:20px'>Top coders are ranked using verified platform activity and consistency.</p></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='proof'><div class='proof-item'>{students}</div><div class='proof-label'>AIML students ready to track · Codolio-connected platform intelligence · role-based academic portal</div></div>", unsafe_allow_html=True)


def sign_in() -> Optional[Dict[str, str]]:
    registry = load_access_registry()
    if st.button("← Back to CampusCode", key="back_to_landing"):
        st.session_state["show_auth"] = False
        st.rerun()
    st.markdown("<div class='hero'><div class='eyebrow'>CampusCode Intelligence</div><h1>Institutional coding performance, made actionable.</h1><p>Secure access for academic leaders, coordinators, mentors, placement teams, and students.</p></div>", unsafe_allow_html=True)
    if registry.empty:
        st.error("No access registry is configured. Add data/access_registry.csv using the supplied schema.")
        return None
    left, right = st.columns([1, 1.2])
    with left:
        staff_tab, login_tab, register_tab = st.tabs(["Staff direct login", "Student sign in", "Register"])
        with staff_tab:
            staff = registry[registry["role"].ne("student")].copy()
            staff["label"] = staff.apply(lambda row: f"{row['display_name']} — {ROLE_LABELS.get(row['role'], row['role'])}", axis=1)
            with st.form("staff_login_form"):
                selected_label = st.selectbox("Select your pre-approved staff account", staff["label"].tolist())
                staff_password = st.text_input("Password", type="password", key="staff_password")
                staff_submitted = st.form_submit_button("Staff sign in", use_container_width=True, type="primary")
            if staff_submitted:
                selected = staff[staff["label"] == selected_label].iloc[0]
                user = authenticate_account(registry, selected["email"], staff_password)
                if user is None:
                    st.error("Password was not recognised. Use the password assigned to this staff account.")
                else:
                    st.session_state["current_user"] = user
                    st.rerun()
        with login_tab:
            with st.form("login_form"):
                login_id = st.text_input("Registered email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")
            if submitted:
                user = authenticate_account(registry, login_id, password)
                if user is None:
                    st.error("Email or password was not recognised.")
                else:
                    st.session_state["current_user"] = user
                    st.rerun()
        with register_tab:
            st.caption("One email address can create one Student account. Staff roles are assigned by the Main Authority.")
            with st.form("register_form", clear_on_submit=True):
                name = st.text_input("Full name")
                email = st.text_input("Email address")
                roll = st.text_input("Roll number")
                branch = st.selectbox("Branch", ["CSE", "AIML", "IT", "DS", "Other"])
                new_password = st.text_input("Create password (minimum 8 characters)", type="password")
                confirm_password = st.text_input("Confirm password", type="password")
                registered = st.form_submit_button("Create student account", use_container_width=True)
            if registered:
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    success, message = register_student_account(email, new_password, name, roll, branch)
                    (st.success if success else st.error)(message)
    with right:
        st.markdown("### Access that matches responsibility")
        st.markdown("Main authority, HOD, and Faculty Coordinator have institutional views. Mentors see only their mentees; Student Coordinators manage events and announcements; students see their own journey and can submit updates.")
        st.info("Each email address is unique. Registration is limited to Student accounts so nobody can give themselves HOD, coordinator, or admin access.")
    return None


def student_360(row: pd.Series, allow_intervention: bool = False):
    risk = risk_details(row)
    st.markdown(f"### {row['username']} · {row['roll_number']}")
    st.caption(f"{row['branch']} · {row['year']} · Section {row['section']} · Mentor: {row.get('mentor_name') or 'Unassigned'}")
    a, b, c, d, e = st.columns(5)
    a.metric("Coding score", f"{float(row['rank_score']):.1f}")
    b.metric("College rank", f"#{int_value(row['rank']) or '—'}")
    c.metric("Problems solved", int_value(row['total_solved']))
    d.metric("Current streak", int_value(row['current_streak']))
    e.metric("Risk score", f"{risk['risk_score']}/100", risk["risk_status"])
    p1, p2 = st.columns(2)
    with p1:
        st.markdown("#### Platform performance")
        st.dataframe(pd.DataFrame([{
            "LeetCode": int_value(row["leetcode_rating"]), "Codeforces": int_value(row["codeforces_rating"]),
            "CodeChef": int_value(row["codechef_rating"]), "GitHub repos": int_value(row["github_public_repos"])
        }]), hide_index=True, use_container_width=True)
    with p2:
        st.markdown("#### Skill focus")
        skill = pd.DataFrame({"Skill": ["Arrays", "Strings", "Trees", "Graphs", "Dynamic Programming"],
                              "Confidence": [min(92, 40 + int_value(row['easy_solved'])), min(88, 35 + int_value(row['medium_solved']) * 2), min(80, 25 + int_value(row['hard_solved']) * 4), max(25, 70 - risk['risk_score'] // 2), max(20, 65 - risk['risk_score'] // 2)]}).set_index("Skill")
        st.bar_chart(skill)
    st.markdown(f"<div class='notice'><b>Recommended next step:</b> {'Focus on Graphs and Dynamic Programming this week.' if risk['risk_score'] < 30 else 'Schedule a mentor check-in, set a 14-day activity goal, and assign DSA fundamentals.'}</div>", unsafe_allow_html=True)
    if allow_intervention:
        with st.expander("Create intervention"):
            with st.form(f"intervention_{row['roll_number']}"):
                action = st.selectbox("Intervention", ["14-day activity target", "DSA fundamentals plan", "Mentor meeting", "Contest encouragement"])
                note = st.text_area("Mentor note")
                if st.form_submit_button("Save intervention"):
                    append_table_row(INTERVENTIONS_PATH, ["created_at", "roll_number", "student_name", "action", "note", "owner"], {"created_at": datetime.now().isoformat(timespec="minutes"), "roll_number": row["roll_number"], "student_name": row["username"], "action": action, "note": note, "owner": st.session_state["current_user"]["display_name"]})
                    st.success("Intervention recorded.")


def institutional_overview(df: pd.DataFrame, user: Dict[str, str]):
    scoped = with_risk(df)
    if user["role"] == "hod" and user.get("department"):
        scoped = scoped[scoped["branch"].str.upper() == user["department"].upper()]
    st.markdown("<div class='eyebrow'>Department intelligence</div>", unsafe_allow_html=True)
    st.title("Performance overview")
    active = int((scoped["active_days"] >= 5).sum())
    at_risk = int((scoped["risk_status"] == "At risk").sum())
    a,b,c,d = st.columns(4); a.metric("Students", len(scoped)); b.metric("Active coders", active); c.metric("At risk", at_risk); d.metric("Average score", f"{scoped['rank_score'].mean():.1f}" if len(scoped) else "0")
    team = load_access_registry()
    team = team[team["role"].isin(["hod", "faculty_coordinator", "student_coordinator"])]
    if not team.empty:
        st.markdown("#### Academic coordination team")
        team["Role"] = team["role"].map(ROLE_LABELS)
        st.dataframe(team[["Role", "display_name", "department"]].rename(columns={"display_name": "Member", "department": "Department"}), hide_index=True, use_container_width=True)
    st.markdown("#### Drill down")
    drill = scoped.groupby(["branch", "year", "section"], dropna=False).agg(Students=("username", "count"), Active=("active_days", lambda x: int((x >= 5).sum())), At_Risk=("risk_status", lambda x: int((x == "At risk").sum())), Average_Score=("rank_score", "mean")).round(1).reset_index()
    st.dataframe(drill, hide_index=True, use_container_width=True)
    col1,col2 = st.columns(2)
    with col1: st.bar_chart(scoped.groupby("branch")["rank_score"].mean())
    with col2: st.bar_chart(scoped["risk_status"].value_counts())
    st.markdown("#### Students needing attention")
    st.dataframe(scoped.sort_values("risk_score", ascending=False)[["username", "roll_number", "branch", "mentor_name", "risk_score", "risk_status", "risk_signals"]].head(15), hide_index=True, use_container_width=True)


def mentor_workspace(df: pd.DataFrame, user: Dict[str, str]):
    st.title("Mentorship workspace")
    if user["role"] == "mentor":
        mentees = df[df["mentor_email"].str.lower() == user.get("email", "").lower()].copy()
    else:
        names = sorted(x for x in df["mentor_name"].dropna().unique() if clean(x))
        if not names: st.info("Create mentor–mentee assignments in Administration first."); return
        name = st.selectbox("Mentor", names)
        mentees = df[df["mentor_name"] == name].copy()
    mentees = with_risk(mentees)
    a,b,c = st.columns(3); a.metric("Mentees",len(mentees)); b.metric("On track",int((mentees.risk_status == "On track").sum())); c.metric("At risk",int((mentees.risk_status == "At risk").sum()))
    if mentees.empty: st.info("No active mentees are mapped to this account."); return
    st.dataframe(mentees[["username","roll_number","total_solved","active_days","risk_score","risk_status","risk_signals"]].sort_values("risk_score", ascending=False), hide_index=True, use_container_width=True)
    selected = st.selectbox("Open 360° profile", mentees["username"].tolist(), key="mentor_profile")
    student_360(mentees[mentees["username"] == selected].iloc[0], allow_intervention=True)


def coordination_workspace(df: pd.DataFrame, user: Dict[str, str]):
    st.title("Coding coordination")
    events = load_table(EVENTS_PATH, ["event_name", "date", "type", "capacity", "status", "created_by"])
    announcements = load_table(ANNOUNCEMENTS_PATH, ["created_at", "title", "message", "audience", "created_by"])
    a,b,c,d = st.columns(4); a.metric("Students",len(df)); b.metric("Active coders",int((df.active_days >= 5).sum())); c.metric("Events",len(events)); d.metric("Platform sync","Healthy")
    left,right = st.columns(2)
    with left:
        st.markdown("#### Upcoming events")
        st.dataframe(events, hide_index=True, use_container_width=True)
        with st.form("event_form", clear_on_submit=True):
            event = st.text_input("Event name"); date = st.date_input("Date"); event_type = st.selectbox("Type", ["Contest", "Workshop", "Assessment", "Hackathon", "Bootcamp"]); capacity = st.number_input("Capacity", 1, 10000, 100)
            if st.form_submit_button("Create event"):
                append_table_row(EVENTS_PATH, ["event_name","date","type","capacity","status","created_by"], {"event_name":event,"date":date,"type":event_type,"capacity":capacity,"status":"Open","created_by":user["display_name"]}); st.success("Event created."); st.rerun()
    with right:
        st.markdown("#### Announcements")
        st.dataframe(announcements.sort_values("created_at", ascending=False), hide_index=True, use_container_width=True)
        with st.form("announcement_form", clear_on_submit=True):
            title=st.text_input("Title"); message=st.text_area("Message"); audience=st.selectbox("Audience", ["All students", "Student coordinators", "Mentors"])
            if st.form_submit_button("Publish announcement"):
                append_table_row(ANNOUNCEMENTS_PATH, ["created_at","title","message","audience","created_by"], {"created_at":datetime.now().isoformat(timespec="minutes"),"title":title,"message":message,"audience":audience,"created_by":user["display_name"]}); st.success("Announcement published."); st.rerun()


def placement_workspace(df: pd.DataFrame):
    st.title("Placement readiness")
    ready = df.copy(); ready["readiness"] = (ready["rank_score"] * .45 + ready["contest_rating"] * .02 + ready["github_public_repos"] * 2).clip(upper=100).round()
    ready["band"] = pd.cut(ready["readiness"], [-1, 35, 60, 80, 101], labels=["Needs work", "Average", "Good", "Excellent"])
    st.bar_chart(ready["band"].value_counts().sort_index())
    minimum = st.slider("Minimum readiness for talent pool", 0, 100, 60)
    st.dataframe(ready[ready.readiness >= minimum][["username","roll_number","branch","total_solved","contest_rating","github_public_repos","readiness","band"]].sort_values("readiness", ascending=False), hide_index=True, use_container_width=True)


def student_workspace(df: pd.DataFrame, user: Dict[str, str]):
    own = df[(df["email"].str.lower() == user.get("email", "").lower()) | (df["roll_number"].str.lower() == user.get("roll_number", "").lower())]
    st.title(f"Welcome back, {user['display_name']} 👋")
    if own.empty:
        st.warning("Your account is active, but it is not yet linked to a student profile. Ask a coordinator to verify your email or roll number.")
    else:
        student_360(own.iloc[0])
    st.markdown("#### Submit an update")
    st.caption("Updates are routed to coordinators; they do not overwrite verified analytics automatically.")
    with st.form("student_update", clear_on_submit=True):
        update_type = st.selectbox("Update type", ["Platform handle", "Event participation", "Achievement", "Profile correction"]); details = st.text_area("Details")
        if st.form_submit_button("Send for review"):
            append_table_row(STUDENT_UPDATES_PATH, ["created_at","student_email","roll_number","update_type","details","status"], {"created_at":datetime.now().isoformat(timespec="minutes"),"student_email":user.get("email"),"roll_number":user.get("roll_number"),"update_type":update_type,"details":details,"status":"Pending review"}); st.success("Your update was sent to the coordination team.")


def student_registry_editor(df: pd.DataFrame, user: Dict[str, str]):
    """Direct profile editing for staff, limited to the records each role owns."""
    role = user["role"]
    if role not in {"admin", "hod", "faculty_coordinator", "student_coordinator", "mentor"}:
        st.error("Your role has view-only access to student records.")
        return
    source_path = BASE_DIR / "usernames.csv"
    if not source_path.exists():
        st.error("Student registry file usernames.csv was not found.")
        return
    try:
        source = pd.read_csv(source_path, dtype=str).fillna("")
    except (OSError, pd.errors.EmptyDataError):
        st.error("Student registry could not be opened.")
        return
    for column in FIELDS:
        if column not in source.columns:
            source[column] = ""

    editable = source.copy()
    scope_message = "All student records"
    if role == "hod":
        editable = editable[editable["branch"].str.upper() == clean(user.get("department")).upper()]
        scope_message = f"Department records: {user.get('department') or 'assigned department'}"
    elif role == "mentor":
        mentee_emails = set(df.loc[df["mentor_email"].str.lower() == clean(user.get("email")).lower(), "email"].str.lower())
        editable = editable[editable["email"].str.lower().isin(mentee_emails)]
        scope_message = "Only your assigned mentees"

    st.title("Edit student records")
    st.caption(f"Access scope: {scope_message}. Changes are saved to the student registry and then analytics refresh automatically.")
    if editable.empty:
        st.info("No student records are available in your permitted scope.")
        return
    edited = st.data_editor(editable[FIELDS], key=f"registry_editor_{role}", use_container_width=True, hide_index=True, num_rows="fixed")
    if st.button("Save student record changes", type="primary"):
        emails = edited["email"].astype(str).str.strip().str.lower()
        rolls = edited["roll_number"].astype(str).str.strip().str.lower()
        if emails.eq("").any() or rolls.eq("").any():
            st.error("Email and roll number are required for every student record.")
        elif emails.duplicated().any() or rolls.duplicated().any():
            st.error("Each email and roll number must remain unique.")
        else:
            source.loc[edited.index, FIELDS] = edited[FIELDS].astype(str)
            source.to_csv(source_path, index=False)
            st.session_state["initial_sync_done"] = False
            st.success("Student records saved. Refreshing analytics now...")
            st.rerun()


def sidebar_member_directory():
    """Keep the coordination team visible at the top for every signed-in user."""
    members = load_access_registry()
    members = members[members["role"].isin(["hod", "faculty_coordinator", "student_coordinator", "mentor", "placement_officer"])]
    if members.empty:
        return
    with st.expander("Campus members", expanded=True):
        for role in ["hod", "faculty_coordinator", "student_coordinator", "mentor", "placement_officer"]:
            names = members.loc[members["role"] == role, "display_name"].tolist()
            if names:
                st.caption(f"{ROLE_LABELS[role]}: {', '.join(names)}")


def all_members_data_view(df: pd.DataFrame):
    """A shared read-only directory available after every login."""
    st.title("All members & data")
    st.caption("This directory is visible to every signed-in member. Only authorised staff receive editing controls in their own workspace.")
    members = load_access_registry()
    members = members[members["role"].ne("student")].copy()
    members["Role"] = members["role"].map(ROLE_LABELS)
    tabs = st.tabs(["Institution team", "Student performance"])
    with tabs[0]:
        st.dataframe(members[["Role", "display_name", "department"]].rename(columns={"display_name": "Member", "department": "Department"}), hide_index=True, use_container_width=True)
    with tabs[1]:
        st.dataframe(df[["username", "roll_number", "branch", "year", "section", "mentor_name", "total_solved", "contest_rating", "rank_score", "rank"]].sort_values("rank"), hide_index=True, use_container_width=True)


def dashboard_topbar(user: Dict[str, str], nav: List[str]):
    """A compact, presentation-style top navigation for every logged-in page."""
    members = load_access_registry()
    team_bits = []
    for role in ["hod", "faculty_coordinator", "student_coordinator"]:
        names = members.loc[members["role"] == role, "display_name"].tolist()
        if names:
            team_bits.append(f"<b>{ROLE_LABELS[role]}:</b> {', '.join(names)}")
    team_text = " &nbsp; · &nbsp; ".join(team_bits)
    st.markdown(f"""<style>
    .app-topnav {{background:#090e1a; border:1px solid #202a40; border-radius:14px; padding:15px 20px; display:flex; align-items:center; justify-content:space-between; margin:0 0 10px;}}
    .app-topnav .brand {{font-weight:850; font-size:1.15rem; color:#fff;}} .app-topnav .brand span {{color:#f59e0b;}}
    .team-strip {{background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:9px 14px; font-size:.79rem; color:#475569; margin-bottom:18px;}}
    </style><div class='app-topnav'><div class='brand'>Campus<span>Code</span> Intelligence</div></div><div class='team-strip'>{team_text}</div>""", unsafe_allow_html=True)
    top_links = [
        page for page in nav
        if page in {"Home", "Overview", "All members & data", "Analytics", "Competitions", "Coordination", "Leaderboard"}
    ]
    columns = st.columns(len(top_links))
    for column, page in zip(columns, top_links):
        if column.button(page, key=f"topnav_{page}", use_container_width=True):
            st.session_state["workspace_page"] = page
            st.rerun()


def logged_home(df: pd.DataFrame, user: Dict[str, str]):
    st.markdown("<div class='eyebrow'>AIML Department · CampusCode Intelligence</div>", unsafe_allow_html=True)
    st.title("Coding intelligence home")
    st.caption("A single view for leadership, faculty coordination, student activities, and platform-based performance.")
    a, b, c, d = st.columns(4)
    a.metric("Students tracked", len(df))
    b.metric("Top score", f"{df['rank_score'].max():.1f}" if not df.empty else "0")
    c.metric("Problems solved", int(df["total_solved"].sum()))
    d.metric("Platforms", "6+")
    left, right = st.columns([1.25, .75])
    with left:
        st.markdown("#### Top coders")
        st.dataframe(df[["rank", "username", "roll_number", "total_solved", "contest_rating", "rank_score"]].sort_values("rank").head(8), hide_index=True, use_container_width=True)
    with right:
        st.markdown("#### Tomorrow's presentation flow")
        st.markdown("1. Upload JRS dataset\n2. Sync Codolio-linked platforms\n3. Show leaderboard and risk insights\n4. Explain mentor interventions\n5. Demonstrate placement readiness")
        st.info("Use the sidebar to open member data, upload the AIML dataset, or manage events.")


def legacy_app():
    if st is None:
        raise RuntimeError("Streamlit is required for the dashboard. Install requirements.txt.")
    st.set_page_config(page_title="Coding Platform Analytics", page_icon="⚡", layout="wide")
    st.title("⚡ University Coding Platform Analytics")

    # Synchronize both configured student sources once per Streamlit session
    # before showing dashboard data. A manual refresh can force another sync.
    if "initial_sync_done" not in st.session_state:
        st.session_state["initial_sync_done"] = False

    if not st.session_state["initial_sync_done"]:
        sheet_url = os.getenv("GOOGLE_SHEET_CSV_URL", "").strip()
        with st.spinner("Loading usernames.csv + Google Sheet and fetching coding data..."):
            try:
                pipeline = DataPipeline(sheet_url=sheet_url or None)
                students = pipeline.load_students()
                if not students:
                    st.warning(
                        "No student profiles found in usernames.csv or Google Sheet. "
                        "Configure the Google Sheet or add usernames.csv."
                    )
                    return
                pipeline.run(students)
                st.session_state["initial_sync_done"] = True
            except Exception as exc:
                logger.exception("Initial synchronization failed")
                st.error(f"Initial synchronization failed: {exc}")
                st.info("Check usernames.csv and the Google Sheet configuration, then retry.")
                return

    df = load_df()
    if not df.empty:
        df = merge_mentor_mappings(df)

    if df.empty:
        st.info("No student analytics are currently available.")
    else:
        filtered = apply_filters(df)
        a, b, c, d = st.columns(4)
        a.metric("Students", len(filtered))
        b.metric("Problems Solved", int(filtered["total_solved"].sum()) if not filtered.empty else 0)
        c.metric("Top Score", f"{filtered['rank_score'].max():.1f}" if not filtered.empty else "0.0")
        d.metric("Average Rating", f"{filtered['contest_rating'].mean():.0f}" if not filtered.empty else "0")
        e = st.columns(1)[0]
        e.metric("Best Platform Score", f"{filtered['best_platform_score'].max():.1f}" if not filtered.empty else "0.0")

        tabs = st.tabs(["🏆 Leaderboard", "📊 Analytics", "👤 Profile", "👨‍🏫 Mentor", "💻 GitHub", "🔎 Email Lookup", "📈 Progress", "⚙️ Data"])
        with tabs[0]: overview(filtered)
        with tabs[1]: analytics(filtered)
        with tabs[2]: profile(filtered)
        with tabs[3]: mentor_dashboard(filtered)
        with tabs[4]: github_dashboard(filtered)
        with tabs[5]: email_lookup(df)
        with tabs[6]: history_view(filtered)
        with tabs[7]: data_management(df)


def app():
    if st is None:
        raise RuntimeError("Streamlit is required for the dashboard. Install requirements.txt.")
    st.set_page_config(page_title="CampusCode Intelligence", page_icon="🎓", layout="wide")
    render_brand()
    user = st.session_state.get("current_user")
    if not user:
        if st.session_state.get("show_auth", False):
            sign_in()
        else:
            public_landing()
        return
    with st.sidebar:
        st.markdown("### CampusCode")
        st.caption(f"{user['display_name']} · {ROLE_LABELS.get(user['role'], user['role'])}")
        sidebar_member_directory()
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("current_user", None)
            st.rerun()

    if "initial_sync_done" not in st.session_state:
        st.session_state["initial_sync_done"] = False
    if not st.session_state["initial_sync_done"]:
        with st.spinner("Loading student analytics..."):
            try:
                pipeline = DataPipeline(sheet_url=os.getenv("GOOGLE_SHEET_CSV_URL", "").strip() or None)
                students = pipeline.load_students()
                if not students:
                    st.warning("No student profiles found. Add usernames.csv or configure the Google Sheet.")
                    return
                pipeline.run(students)
                st.session_state["initial_sync_done"] = True
            except Exception as exc:
                logger.exception("Initial synchronization failed")
                st.error(f"Initial synchronization failed: {exc}")
                return
    df = load_df()
    if df.empty:
        st.info("No student analytics are currently available.")
        return
    df = merge_mentor_mappings(df)
    role = user["role"]
    if role in FULL_ACCESS_ROLES:
        nav = ["Home", "Overview", "All members & data", "Students & Risk", "Mentorship", "Competitions", "Analytics", "Placement", "Administration"]
    elif role == "mentor": nav = ["Home", "All members & data", "My mentees", "Interventions", "Edit my mentees"]
    elif role == "student_coordinator": nav = ["Home", "All members & data", "Coordination", "Student records", "Dataset upload", "Leaderboard", "Announcements"]
    elif role == "placement_officer": nav = ["Home", "All members & data", "Placement readiness", "Talent pool"]
    else: nav = ["Home", "All members & data", "My journey", "Announcements", "Submit update"]
    if st.session_state.get("workspace_page") not in nav:
        st.session_state["workspace_page"] = nav[0]
    dashboard_topbar(user, nav)
    page = st.sidebar.radio("Workspace", nav, key="workspace_page")
    if page == "Home": logged_home(df, user)
    elif page == "Overview": institutional_overview(df, user)
    elif page == "All members & data": all_members_data_view(df)
    elif page == "Students & Risk":
        scoped = with_risk(apply_filters(df)); st.title("Students & early warning")
        st.dataframe(scoped[["username", "roll_number", "branch", "mentor_name", "rank_score", "total_solved", "risk_score", "risk_status", "risk_signals"]].sort_values("risk_score", ascending=False), hide_index=True, use_container_width=True)
        selected = st.selectbox("Open student 360° profile", scoped["username"].tolist(), key="admin_student_profile")
        student_360(scoped[scoped.username == selected].iloc[0], allow_intervention=True)
    elif page in {"Mentorship", "My mentees", "Interventions"}: mentor_workspace(df, user)
    elif page in {"Student records", "Edit my mentees"}: student_registry_editor(df, user)
    elif page == "Dataset upload": dataset_upload_workspace()
    elif page in {"Competitions", "Coordination"}: coordination_workspace(df, user)
    elif page == "Analytics": analytics(apply_filters(df))
    elif page in {"Placement", "Placement readiness", "Talent pool"}: placement_workspace(df)
    elif page == "Leaderboard": overview(df)
    elif page == "Announcements":
        st.title("Announcements")
        st.dataframe(load_table(ANNOUNCEMENTS_PATH, ["created_at", "title", "message", "audience", "created_by"]).sort_values("created_at", ascending=False), hide_index=True, use_container_width=True)
    elif page in {"My journey", "Submit update"}: student_workspace(df, user)
    elif page == "Administration":
        tabs = st.tabs(["Student records", "Data & mappings", "GitHub portfolio", "Progress history", "Student submissions"])
        with tabs[0]: student_registry_editor(df, user)
        with tabs[1]: data_management(df)
        with tabs[2]: github_dashboard(df)
        with tabs[3]: history_view(df)
        with tabs[4]: st.dataframe(load_table(STUDENT_UPDATES_PATH, ["created_at","student_email","roll_number","update_type","details","status"]), hide_index=True, use_container_width=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true")
    args, _ = parser.parse_known_args()
    if args.sync:
        DataPipeline().run()
    else:
        app()
