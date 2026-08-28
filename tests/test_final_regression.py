
import csv
import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
import app


class TestFinalRegression(unittest.TestCase):
    def base_record(self):
        return {
            "email": "student@university.edu",
            "username": "Student",
            "roll_number": "23CSE001",
            "year": "III",
            "section": "A",
            "branch": "CSE",
            "rank": 1,
            "rank_score": 100,
            "best_platform_score": 100,
            "average_platform_score": 80,
            "total_solved": 20,
            "easy_solved": 10,
            "medium_solved": 7,
            "hard_solved": 3,
            "contest_rating": 1500,
            "leetcode_rating": 1500,
            "codeforces_rating": 0,
            "codechef_rating": 0,
            "leetcode_score": 100,
            "codeforces_score": 0,
            "codechef_score": 0,
            "gfg_score": 0,
            "codolio_score": 0,
            "active_days": 10,
            "current_streak": 2,
            "github_public_repos": 5,
            "github_followers": 8,
            "codolio_handle": "student",
            "leetcode_handle": "student",
            "codeforces_handle": "",
            "codechef_handle": "",
            "gfg_handle": "",
            "github_handle": "student",
        }

    def test_legacy_snapshot_without_status_is_safe(self):
        df = pd.DataFrame([self.base_record()])
        normalized = app.normalize_dashboard_df(df)
        self.assertIn("sync_status", normalized.columns)
        self.assertEqual(normalized.loc[0, "sync_status"], "Unknown")
        self.assertNotIn("status", normalized.columns)

    def test_legacy_status_is_migrated(self):
        r = self.base_record()
        r["status"] = "Codolio-Synced"
        df = app.normalize_dashboard_df(pd.DataFrame([r]))
        self.assertEqual(df.loc[0, "sync_status"], "Codolio-Synced")
        self.assertNotIn("status", df.columns)

    def test_all_dashboard_column_groups_exist(self):
        df = app.normalize_dashboard_df(pd.DataFrame([self.base_record()]))
        groups = [
            ["rank","roll_number","username","year","section","branch","mentor_name","mentee_status",
             "best_platform_score","average_platform_score","total_solved","easy_solved","medium_solved",
             "hard_solved","contest_rating","rank_score","sync_status"],
            ["easy_solved","medium_solved","hard_solved"],
            ["email","username","roll_number","year","section","branch","mentor_name","mentee_status",
             "codolio_handle","leetcode_handle","codeforces_handle","codechef_handle","gfg_handle","github_handle"],
            ["rank","username","roll_number","branch","year","section","best_platform_score",
             "average_platform_score","total_solved","contest_rating","github_public_repos","sync_status"],
        ]
        for group in groups:
            self.assertEqual([c for c in group if c not in df.columns], [])

    def test_old_mentor_mapping_status_is_migrated(self):
        with tempfile.TemporaryDirectory() as d:
            old = app.MENTEE_MAP_PATH
            try:
                app.MENTEE_MAP_PATH = Path(d) / "mentor_mentees.csv"
                pd.DataFrame([{
                    "mentor_id": "M001",
                    "mentor_name": "Faculty",
                    "mentor_email": "faculty@university.edu",
                    "student_email": "student@university.edu",
                    "roll_number": "23CSE001",
                    "status": "Active",
                }]).to_csv(app.MENTEE_MAP_PATH, index=False)
                mapping = app.load_mentee_map()
                self.assertIn("mentee_status", mapping.columns)
                self.assertEqual(mapping.loc[0, "mentee_status"], "Active")
            finally:
                app.MENTEE_MAP_PATH = old

    def test_missing_mentor_status_is_safe(self):
        with tempfile.TemporaryDirectory() as d:
            old = app.MENTEE_MAP_PATH
            try:
                app.MENTEE_MAP_PATH = Path(d) / "mentor_mentees.csv"
                pd.DataFrame([{
                    "mentor_id": "M001",
                    "mentor_name": "Faculty",
                    "mentor_email": "faculty@university.edu",
                    "student_email": "student@university.edu",
                    "roll_number": "23CSE001",
                }]).to_csv(app.MENTEE_MAP_PATH, index=False)
                df = pd.DataFrame([self.base_record()])
                merged = app.merge_mentor_mappings(df)
                self.assertEqual(merged.loc[0, "mentee_status"], "Unassigned")
            finally:
                app.MENTEE_MAP_PATH = old

    def test_student_source_schema(self):
        missing = app.validate_student_source_columns([
            "email","username","roll_number","year","section","branch","codolio_handle"
        ])
        self.assertEqual(missing, [])

    def test_student_source_missing_required_column_is_reported(self):
        missing = app.validate_student_source_columns([
            "email","username","roll_number","year","section","codolio_handle"
        ])
        self.assertIn("branch", missing)

    def test_sample_files_have_expected_headers(self):
        root = Path(__file__).parents[1]
        expected = [
            "email","username","roll_number","year","section","branch",
            "codolio_handle","leetcode_handle","codeforces_handle",
            "codechef_handle","gfg_handle","github_handle"
        ]
        with (root / "usernames.csv").open(encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), expected)

        with (root / "data" / "student_profiles_google_sheet_sample.csv").open(encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), expected)

        with (root / "data" / "mentors.csv").open(encoding="utf-8") as f:
            self.assertEqual(
                next(csv.reader(f)),
                ["mentor_id","mentor_name","mentor_email","department"]
            )

        with (root / "data" / "mentor_mentees.csv").open(encoding="utf-8") as f:
            self.assertEqual(
                next(csv.reader(f)),
                ["mentor_id","mentor_name","mentor_email","student_email","roll_number","mentee_status","updated_at"]
            )

    def test_first_run_uses_both_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_path = root / "usernames.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "email","username","roll_number","year","section","branch","codolio_handle"
                ])
                w.writeheader()
                w.writerow({
                    "email":"student@university.edu","username":"Student","roll_number":"1",
                    "year":"III","section":"A","branch":"CSE","codolio_handle":"student"
                })

            old_lb, old_hist = app.LEADERBOARD_PATH, app.HISTORY_PATH
            try:
                app.LEADERBOARD_PATH = root / "leaderboard.json"
                app.HISTORY_PATH = root / "history.json"

                class FakePipeline(app.DataPipeline):
                    def __init__(self, *args, **kwargs):
                        super().__init__(input_csv=str(csv_path), sheet_url="fake")
                        self.aggregator = type("A", (), {
                            "process": lambda self, s: app.CodingMetrics(
                                email=s.email, username=s.username, roll_number=s.roll_number,
                                year=s.year, section=s.section, branch=s.branch,
                                sync_status="Test-Synced", rank_score=10
                            )
                        })()

                    def _load_sheet_source(self):
                        self.source_status["google_sheet"] = "loaded:1"
                        return [app.StudentProfile(
                            email="student@university.edu", username="Student",
                            roll_number="1", year="III", section="A", branch="CSE",
                            codolio_handle="student"
                        )]

                p = FakePipeline()
                students = p.load_students()
                self.assertEqual(len(students), 1)
                self.assertIn("usernames.csv", p.source_status)
                self.assertIn("google_sheet", p.source_status)
                p.run()
                payload = json.loads(app.LEADERBOARD_PATH.read_text())
                self.assertEqual(payload["total_students"], 1)
            finally:
                app.LEADERBOARD_PATH = old_lb
                app.HISTORY_PATH = old_hist

if __name__ == "__main__":
    unittest.main()
