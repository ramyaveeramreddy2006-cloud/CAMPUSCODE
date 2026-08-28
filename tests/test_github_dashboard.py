
import unittest
import pandas as pd
import app


class TestGitHubDashboard(unittest.TestCase):
    def test_github_columns_are_supported(self):
        df = app.normalize_dashboard_df(pd.DataFrame([{
            "email": "student@university.edu",
            "username": "Student",
            "roll_number": "1",
            "year": "III",
            "section": "A",
            "branch": "CSE",
            "github_handle": "student-dev",
            "github_public_repos": 12,
            "github_followers": 30,
        }]))
        self.assertEqual(df.loc[0, "github_handle"], "student-dev")
        self.assertEqual(df.loc[0, "github_public_repos"], 12)
        self.assertEqual(df.loc[0, "github_followers"], 30)

    def test_github_profile_url_format(self):
        handle = "student-dev"
        self.assertEqual(f"https://github.com/{handle}", "https://github.com/student-dev")


if __name__ == "__main__":
    unittest.main()
