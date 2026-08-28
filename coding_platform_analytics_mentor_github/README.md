# University Coding Platform Analytics — v2

A university coding-performance system for the Coding Platform Incharge, faculty mentors and students.

The system is designed around a simple principle:

**collect once → fetch reliably → normalize → compare → mentor → select → recommend**

## Complete step-by-step guide

This section is the practical guide for running and using the project. The
remaining sections explain the design and data model in more detail.

### 1. Project structure

```text
coding_platform_analytics_mentor_github/
├── app.py                         # Streamlit application and data pipeline
├── requirements.txt               # Python dependencies
├── usernames.csv                  # Local student profile source
├── README.md                      # Project documentation
├── data/
│   ├── access_registry.csv        # Local sign-in accounts and roles
│   ├── leaderboard.json           # Latest generated analytics snapshot
│   ├── history.json               # Previous synchronization snapshots
│   ├── mentors.csv                # Mentor directory
│   ├── mentor_mentees.csv         # Mentor-to-student assignments
│   ├── student_profiles_google_sheet_sample.csv
│   ├── events.csv                 # Created when event data is first saved
│   ├── announcements.csv          # Created when an announcement is first saved
│   ├── interventions.csv          # Created when an intervention is first saved
│   └── student_updates.csv        # Created when a student submits an update
├── templates/
│   ├── universal_student_data_template.csv
│   ├── student_profiles_template.csv
│   ├── mentor_mentees_template.csv
│   └── universal_student_data_field_spec.csv
└── tests/
              ├── test_final_regression.py   # Data, ranking, sync and schema tests
              └── test_github_dashboard.py   # GitHub field and URL tests
```

`app.py` is the only application entry point. It contains the Streamlit UI,
local authentication, source loading, platform connectors, score calculation,
role-based views, file-backed forms, and export logic.

### 2. Install and start the application

Open a terminal in the folder that contains `app.py`, then run:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Windows Command Prompt:

```cmd
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Linux or macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints a local URL, normally `http://localhost:8501`. Open that URL
in a browser. Keep the terminal running while using the dashboard. Stop the
server with `Ctrl+C`.

### 3. Configure data before the first run

At minimum, `usernames.csv` must contain these columns:

```csv
email,username,roll_number,year,section,branch,codolio_handle,leetcode_handle,codeforces_handle,codechef_handle,gfg_handle,github_handle
```

Use `templates/universal_student_data_template.csv` when preparing a new file.
Every row represents one student. Use the institutional email as the stable
identity, and enter public usernames only in the platform handle columns.

You can use either or both of these sources:

1. Keep student records in the local `usernames.csv` file.
2. Put the same schema into Google Sheets and publish/export the sheet as CSV.
3. Set `GOOGLE_SHEET_CSV_URL` to the published CSV URL.
4. Start the application or use **Refresh Both Student Sources** in Data Management.

Example PowerShell configuration for the current terminal session:

```powershell
$env:GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/<id>/export?format=csv"
$env:GITHUB_TOKEN = "<optional-token>"
$env:CODOLIO_API_TOKEN = "<optional-token>"
streamlit run app.py
```

Do not commit real tokens, passwords, or private student information.

### 4. Sign in

The public landing page has **Open department portal**. The sign-in page has:

- **Staff direct login** for pre-approved staff accounts.
- **Student sign in** for registered student accounts.
- **Register** for creating a student account.

Local development accounts are stored in `data/access_registry.csv`. The
current sample accounts include:

| Account | Login | Password |
|---|---|---|
| Administrator | `admin@campuscode.edu` | `admin123` |
| HOD | `mallikarjunareddyaiml@anurag.edu.in` | `hod123` |
| Faculty coordinator | `shashankreddyaiml@anurag.edu.in` | `coord123` |
| Mentor | `anilkumar.aiml@anurag.edu.in` | `mentor123` |
| Student coordinator | `ramyaaiml@anurag.edu.in` | `studentcoord123` |
| Placement officer | `placement@campuscode.edu` | `placement123` |
| Student | `student@university.edu` | `student123` |

These are demo credentials only. Replace them before deployment. New student
registrations require a valid email, a password of at least eight characters,
name, roll number, and branch. New passwords are stored as PBKDF2 digests.

### 5. Understand the first dashboard load

After a successful sign-in, the app performs the following sequence:

1. Read the local student registry.
2. Read the Google Sheet when `GOOGLE_SHEET_CSV_URL` is configured.
3. Merge matching records by email, or by roll number when email is absent.
4. Record conflicts and use the Google Sheet value for a conflicting field.
5. Fetch Codolio data and use direct LeetCode and Codeforces fallbacks when needed.
6. Fetch public GitHub profile metadata when a GitHub handle is available.
7. Calculate platform scores, consistency, overall rank, and sync status.
8. Write the latest result to `data/leaderboard.json`.
9. Append a historical snapshot to `data/history.json`.
10. Display the role-specific workspace.

The first synchronization may take time because it uses external services. If
the sync fails, the app reports the error and keeps the last valid snapshot.
Use **Refresh Both Student Sources** to retry after correcting the source data.

### 6. Use the navigation

The top navigation and the sidebar open the same role-specific pages. Selecting
a page updates the workspace immediately. Available pages depend on the role:

| Role | Pages and purpose |
|---|---|
| Administrator, HOD, Faculty Coordinator | Home, Overview, All members & data, Students & Risk, Mentorship, Competitions, Analytics, Placement, Administration |
| Mentor | Home, All members & data, My mentees, Interventions, Edit my mentees |
| Student Coordinator | Home, All members & data, Coordination, Student records, Dataset upload, Leaderboard, Announcements |
| Placement Officer | Home, All members & data, Placement readiness, Talent pool |
| Student | Home, All members & data, My journey, Announcements, Submit update |

Main page responsibilities:

- **Home:** headline student counts, top scores, solved problems, and the top coders.
- **Overview / Leaderboard:** ranking table, filters, Top-N comparison, platform scores, and coding metrics.
- **All members & data:** read-only institution team and student performance directory.
- **Students & Risk:** risk score, explainable risk signals, and student 360-degree profiles.
- **Mentorship / My mentees / Interventions:** mentor assignments, progress, and intervention records.
- **Competitions / Coordination:** competition and coordination workflows.
- **Analytics:** difficulty, branch, year, section, and mentor summaries.
- **Placement / Placement readiness / Talent pool:** evidence-based placement views and candidate filtering.
- **Administration:** student records, data mappings, GitHub portfolio, history, and submissions.
- **Dataset upload:** validate and replace the local student registry with a CSV upload.
- **Announcements:** view announcements saved by authorized users.
- **My journey / Submit update:** student-specific progress and update submission.

### 7. Maintain mentor assignments

Mentor assignment is intentionally separate from student profile data:

1. Add mentors to `data/mentors.csv` using `mentor_id`, `mentor_name`,
        `mentor_email`, and `department`.
2. Assign students in `data/mentor_mentees.csv`.
3. Keep the student email and roll number aligned with the student registry.
4. Use the Data Management or role-specific editing view to update assignments.
5. The app joins assignments with analytics at runtime.

Changing a mentor does not require changing the student's coding handles. The
assignment state is `mentee_status`; the platform synchronization state is
`sync_status`. They are separate and should not be replaced with a generic
`status` field.

### 8. Upload a new student dataset

Authorized users can open **Dataset upload** or the Administration data view:

1. Download the upload template.
2. Fill one row per student.
3. Keep all required columns present.
4. Upload the CSV.
5. Review the validation message and preview table.
6. Select **Replace registry and refresh leaderboard**.
7. Allow the next synchronization to rebuild the analytics files.

The upload workflow forces `branch` to `AIML` for this project. It does not
silently accept missing required identity or handle columns.

### 9. Run tests and a manual sync

From the project root:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The tests are network-independent and verify normalization, legacy-file
compatibility, score calculation, ranking, mentor mapping, GitHub fields, and
snapshot creation.

To run synchronization without opening the dashboard:

```bash
python app.py --sync
```

This command uses the configured environment variables and writes the JSON
snapshots. Use it from a controlled environment with valid public handles.

### 10. Troubleshoot common problems

- **The app exits immediately:** run the command from the directory containing
       `app.py` and confirm `streamlit` is installed in the active environment.
- **No student analytics are available:** check `usernames.csv`, its headers,
       and the Google Sheet CSV URL.
- **A platform shows zero values:** verify the public handle and inspect the
       `sync_status` and `errors` fields in `data/leaderboard.json`.
- **A mentor sees no mentees:** check matching email values in
       `data/mentor_mentees.csv` and the signed-in account.
- **A source conflict appears:** compare the local CSV and Google Sheet before
       using the record for a high-stakes placement or competition decision.
- **Tests cannot import `app`:** run them from the project root, or set the
       project root as `PYTHONPATH` before running test discovery.

## What is implemented in v2

### Student registry
- Google Sheet / CSV ingestion
- Standardized student schema
- Institutional email identity
- Roll number, year, section and branch
- Assigned mentor/faculty
- Codolio, LeetCode, Codeforces, CodeChef, GFG and GitHub handles

### Data fetching
- Codolio: primary multi-platform aggregation
- LeetCode: direct GraphQL fallback
- Codeforces: direct REST fallback
- GitHub: official REST API for public profile/portfolio metadata
- CodeChef/GFG: handled through Codolio when available; no undocumented direct connector is required for the core release

### Ranking
The system exposes **individual platform scores**, **best platform score** and **average platform score**.

```text
Platform Score =
    Easy × 1
  + Medium × 3
  + Hard × 5
  + Platform Rating × 0.5
```

Available:
- LeetCode Score
- Codeforces Score
- CodeChef Score
- GFG Score
- Codolio-derived score where a platform cannot be identified

The leaderboard uses:

```text
Overall Rank Score =
    Best Platform Score
  + Consistency Bonus
```

This is deliberately different from the average score.

Use:
- **Best** to identify the strongest competition-ready skill.
- **Average** to identify broad multi-platform consistency.
- **Individual scores** to identify platform-specific strengths.
- **Overall rank** for the institutional leaderboard.

The raw platform ratings remain separate and are not treated as interchangeable.

## Why Best + Average + Individual?

A single total score hides important differences.

Example:

```text
Student A:
LeetCode       920
Codeforces     400
CodeChef       350
Average        557
Best           920

Student B:
LeetCode       620
Codeforces     650
CodeChef       610
Average        627
Best           650
```

Student A may be the better choice for a LeetCode-focused event.

Student B demonstrates stronger cross-platform consistency.

The dashboard therefore exposes all three views.

## Mentor / Faculty mapping

Mentoring is a core requirement, not a future feature.

Use two related sheets:

### Student Registry

```text
email
username
roll_number
year
section
branch
mentor_id
mentor_name
mentor_email
codolio_handle
leetcode_handle
codeforces_handle
codechef_handle
gfg_handle
github_handle
```

### Mentor Registry

```csv
mentor_id,mentor_name,mentor_email,department
```

Use `data/mentors.csv` as the mentor registry template. Keep its four columns:
`mentor_id`, `mentor_name`, `mentor_email`, and `department`.

The student sheet should preferably store `mentor_id`; `mentor_name` and `mentor_email` can be maintained as derived/lookup values.

Recommended flow:

```text
Mentor Registry
       |
       v
Student Registry
       |
       v
Coding Metrics
       |
       +--> Incharge Dashboard
       |
       +--> Mentor Dashboard
```

This allows the Coding Platform Incharge to inspect everyone while each mentor can be given a filtered view of assigned students later.

## Coding Platform Incharge use cases

The dashboard is intended to support:

### 1. Competition selection

Filter:

```text
Branch
Year
Mentor
Platform
```

Then compare:

```text
Best Platform Score
Individual Platform Score
Contest Rating
Recent Progress
Active Days
Streak
```

### 2. Placement recommendations

Use a broader profile:

```text
Coding score
Platform breadth
GitHub portfolio
Problem-solving consistency
Rating
Historical improvement
```

The system should support evidence-based recommendation rather than selecting students only by total solved.

### 3. Mentor intervention

Identify:

```text
High score + declining activity
Low score + high improvement
No recent activity
Strong platform-specific ability
Unbalanced skill profile
```

Historical data is retained for this purpose.

## GitHub

GitHub is included because it provides useful portfolio evidence in addition to competitive-programming statistics.

The current connector uses the official GitHub REST API for public user information such as public repository count and followers. GitHub documents public user lookup through `GET /users/{username}` and its REST API is officially supported. urlGitHub REST API user documentationhttps://docs.github.com/en/rest/users

GitHub metrics are intentionally **not automatically mixed into the competitive-programming score**. GitHub is a portfolio/development signal.

## Reliability / complexity decision

Not every possible connector should be added.

### Current architecture

```text
                  Student Sheet
                       |
              +--------+--------+
              |                 |
           Handles           Mentor
              |
              v
          Codolio
              |
       +------+------+
       |             |
       v             v
   LeetCode      Codeforces
   fallback        fallback

          GitHub
             |
             v
      Portfolio signal
```

This keeps the core system relatively small.

### Why not force direct CodeChef/GFG connectors now?

A direct connector should be added only when there is a stable, documented and maintainable API/interface.

If a platform requires brittle page scraping, adding it to the core synchronization path increases:
- failure rate
- maintenance cost
- rate-limit risk
- synchronization time
- deployment complexity

Codolio already provides the aggregation layer for those platforms in the current design.

Therefore **Direct CodeChef and Direct GFG are optional adapters, not mandatory dependencies.**

## Historical analytics

Each synchronization creates a snapshot in:

```text
data/history.json
```

This supports:
- rank movement
- solved growth
- score growth
- rating changes
- active-day trends
- mentor progress
- most-improved identification later



## Dual-source synchronization policy

The application evaluates **both `usernames.csv` and the configured Google Sheet before the dashboard is displayed**.

This is intentional because there is no reliable guarantee that either source is the newest.

### Startup sequence

```text
usernames.csv ─────┐
                   ├──> load both ──> merge ──> detect conflicts
Google Sheet ──────┘                         │
                                             v
                                      fetch platform data
                                             │
                                             v
                                       save snapshot
                                             │
                                             v
                                        dashboard
```

### Merge policy

Records are matched by:

1. institutional email
2. roll number when email is unavailable

For duplicate students:

- non-empty fields from either source are retained;
- if the same field has conflicting non-empty values, the conflict is recorded;
- because exported CSV/Google Sheet data does not reliably expose a comparable last-modified timestamp, the **Google Sheet value is used as the deterministic runtime value for that conflicting field**;
- the conflict is not hidden: it is stored in `data/leaderboard.json` and shown in the Data Management view.

This means the system does **not silently assume that one source is always newer**.

For high-stakes competition or placement decisions, review any reported source conflicts before final selection.

## First-run behavior

The dashboard does **not** require a pre-existing `data/leaderboard.json`.

When the application starts:

1. If a valid leaderboard snapshot exists, it loads it.
2. If no snapshot exists, it automatically attempts the first synchronization.
3. It uses `GOOGLE_SHEET_CSV_URL` when configured.
4. Otherwise it falls back to the local `usernames.csv`.
5. A successful sync creates both `data/leaderboard.json` and `data/history.json`.
6. If no student records are available, the dashboard shows a setup message instead of pretending that the dataset is empty.
7. If synchronization fails, the UI reports the failure and does not delete any previously valid snapshot.

The Data tab can always be used to manually retry synchronization.

## Dashboard

### Leaderboard
- Dynamic Top-N, default 10
- Search
- Branch
- Year
- Section
- Mentor
- Rank
- Best platform score
- Average platform score
- Individual scores
- Coding metrics

### Analytics
- Difficulty breakdown
- Branch performance
- Year performance
- Section performance
- Mentor/faculty summary

### Student Profile
- Academic identity
- Mentor
- All platform handles
- Individual platform scores
- Best score
- Average score
- Ratings
- GitHub portfolio metrics
- Rank
- Sync status

### Email Lookup
Email resolves only against the registered institutional student registry. It does not guess public accounts from an email address.

### Progress
Historical synchronization snapshots.

### Data Management
- Student sync
- Mentor registry visibility
- Current analytics export

## Current schema

```csv
email,username,roll_number,year,section,branch,mentor_id,mentor_name,mentor_email,codolio_handle,leetcode_handle,codeforces_handle,codechef_handle,gfg_handle,github_handle
```

## Google Form

Use controlled choices:

- Year: I, II, III, IV
- Section: A, B, C, D, E
- Branch: institution-defined list
- Mentor: mentor ID/name from the mentor registry

Students should enter their own public coding handles.

## APIs / connectors

| Source | Current method | Core status |
|---|---|---|
| Codolio | Existing public-profile connector | Primary |
| LeetCode | GraphQL web endpoint | Fallback |
| Codeforces | Official REST API | Fallback |
| GitHub | Official REST API | Portfolio |
| CodeChef | Codolio aggregation | Current |
| GFG | Codolio aggregation | Current |

The system is deliberately adapter-based so a direct connector can be added later without changing the dashboard or ranking model.

## What remains optional

These are **not required for the current release**:

- Direct CodeChef connector
- Direct GFG connector
- Advanced rating normalization
- Cross-platform problem deduplication
- PostgreSQL/Supabase migration
- Advanced growth models
- Notifications
- Public GitHub Pages frontend
- Automatic account discovery from email

They are roadmap items, not dependencies.

## Installation

```bash
python -m venv .venv
```

Windows:

```cmd
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
streamlit run app.py
```

Headless:

```bash
python app.py --sync
```

## Environment variables

```text
GOOGLE_SHEET_CSV_URL
CODOLIO_API_TOKEN
GITHUB_TOKEN
```

`GITHUB_TOKEN` is optional. Public GitHub profile requests can work without authentication, while authentication provides higher API limits and access to authenticated endpoints where appropriate.

## GitHub Actions

The supplied workflow runs daily and can be manually triggered.

Required:

```text
GOOGLE_SHEET_CSV_URL
```

Optional:

```text
CODOLIO_API_TOKEN
GITHUB_TOKEN
```

## Privacy

Do not publish the raw student registry or institutional email addresses in a public repository.

Keep:
- email
- mentor email
- internal mentor identifiers

in the private source data where possible.


## Verification status

The bundled test suite is deliberately network-independent. It uses mocked platform responses to verify:

- canonical schema
- legacy `codolio_username` compatibility
- individual platform score calculation
- best platform score
- average platform score
- GitHub metric ingestion
- mentor fields
- ranking tie-breakers
- leaderboard JSON export
- historical snapshot export

The tests do **not** claim live validation of Codolio, LeetCode, Codeforces or GitHub endpoints. Those external services can change and require network access and valid public handles/tokens.

Run:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

For live validation, run:

```bash
python app.py --sync
```

against a controlled test sheet containing known public handles, then inspect `data/leaderboard.json` and `data/history.json`.

## Production recommendation

For the first real deployment:

1. Google Sheet for student registry
2. Separate mentor registry sheet
3. Codolio primary source
4. LeetCode + Codeforces fallback
5. GitHub portfolio metrics
6. JSON history
7. Streamlit dashboard
8. GitHub Actions daily sync

Only move to PostgreSQL/Supabase when data volume, concurrent users or audit requirements justify the additional infrastructure.

## Student Profiles vs Mentor Assignments

These are intentionally **two separate datasets**.

### Student Profiles

The normalized student-profile dataset is created in memory from:

```text
usernames.csv + Google Sheet
```

It contains academic identity and coding-platform handles. The latest persisted
analytics are stored in `data/leaderboard.json`; the app does not write a
separate `student_profiles.csv` file.

It does **not** contain mentor ownership.

### Mentors

`mentors.csv` is a separate assignment dataset in data folder.

```csv
mentor_id,mentor_name,mentor_email,department
```


### Mentor-Mentee Mapping

`mentor_mentees.csv` is a separate assignment dataset in data folder.

```csv
mentor_id,mentor_name,mentor_email,student_email,roll_number,status,updated_at
```

A mentor/faculty member can update this mapping to:
- pick a student as a mentee
- change a mentee
- release a mentee
- reassign a student

The student profile does not need to be edited when mentor ownership changes.

The dashboard joins the two datasets at runtime.

### Why this separation matters

```text
Student Sources
  usernames.csv
       +
  Google Sheet
       |
       v
 Student Profiles
       |
       +--------------------+
                            |
Mentor Assignment File -----+--> Dashboard
                            |
                            +--> Mentor view
                            |
                            +--> Incharge view
```

This prevents mentor assignment changes from contaminating the authoritative student/platform registry.

### Mentor workflow

The Coding Platform Incharge can maintain the mapping centrally.

In a future authenticated deployment, each mentor can be restricted to editing only their own mentees. The current release keeps the assignment data separate and editable without requiring authentication.

## Important data-model correction (v5.1)

`mentor_id` is **not part of the student profile source**, even if an older `usernames.csv` contains that column.

The student loader deliberately ignores mentor columns. Mentor ownership is maintained separately in:

```text
data/mentor_mentees.csv
```

The mentor registry is:

```text
data/mentors.csv
```

Therefore:

```text
usernames.csv / Google Sheet
        |
        v
Student Profiles
        |
        +---- separate runtime join ----+
                                       |
mentors.csv + mentor_mentees.csv ------+
                                       |
                                       v
                               Mentor Dashboard
```

This prevents a stale `mentor_id` in a student CSV from becoming an unintended student-to-mentor connection.

The Data Management screen also provides a basic **Assign / Update Mentees** control.

## Mentor mapping file compatibility

`data/mentor_mentees.csv` is independent from the student-profile dataset.

Older or manually edited mapping files may omit columns such as `status` or
`updated_at`. The application now creates missing assignment columns in memory
and uses `Unassigned` when `status` is absent, instead of crashing the dashboard.

## Final schema policy

The system uses two independent status concepts:

- `sync_status`: coding-platform synchronization state generated by the application.
- `mentee_status`: mentor/student assignment state stored in `data/mentor_mentees.csv`.

The ambiguous field `status` is no longer used by dashboard views.

Legacy leaderboard snapshots containing `status` are migrated automatically to
`sync_status` in memory. Legacy mentor assignment files containing `status` are
migrated automatically to `mentee_status`.

## Runtime data layout

```text
project/
├── app.py
├── usernames.csv
├── data/
│   ├── student_profiles_google_sheet_sample.csv
│   ├── mentors.csv
│   └── mentor_mentees.csv
└── templates/
```

`usernames.csv` and the Google Sheet use the same student-profile schema.

The application reads both sources before the dashboard is first displayed in
a Streamlit session. A manual "Refresh Both Student Sources" action is also
available in Data Management.

The sample Google Sheet file is a CSV representation of the exact header/data
format to upload or reproduce in Google Sheets. It is not itself a live Google
Sheet URL.

The sample platform handles are illustrative and must be replaced with actual
public handles for live platform synchronization.

## GitHub / Portfolio dashboard

GitHub is available as a dedicated `💻 GitHub` dashboard tab.

### Where GitHub data is entered

GitHub is part of the student-profile source files:

```text
usernames.csv
Google Sheet
        ↓
github_handle
        ↓
GitHub API
        ↓
github_public_repos
github_followers
```

The same `github_handle` field is present in:

```text
usernames.csv
data/student_profiles_google_sheet_sample.csv
templates/student_profiles_template.csv
```

### Where GitHub is displayed

The dashboard now contains:

```text
🏆 Leaderboard
📊 Analytics
👤 Profile
👨‍🏫 Mentor
💻 GitHub
🔎 Email Lookup
📈 Progress
⚙️ Data
```

The GitHub view shows:

- GitHub username
- Public repositories
- Followers
- Student identity
- Mentor
- Best platform score
- Average platform score
- Direct GitHub profile link

GitHub remains a portfolio/development signal and is not mixed into the competitive-programming score.

## CampusCode Intelligence role-based release

The Streamlit dashboard now opens with a role-based sign-in experience and shows only the workspace appropriate to the signed-in member.

| Role | Access |
|---|---|
| Main Authority / HOD / Faculty Coordinator | Institutional overview, student risk, analytics, mentorship, events, placement and administration |
| Mentor | Assigned mentees, 360° profiles and interventions only |
| Student Coordinator | Events, leaderboard and announcements; no confidential student/faculty administration |
| Placement Officer | Placement readiness and filtered talent pool |
| Student | Personal 360° journey, announcements and update submissions |

Added operational data is stored locally in `data/`: `events.csv`, `announcements.csv`, `interventions.csv`, and `student_updates.csv`. These files are created when the related form is first used.

### Demo sign-in

`data/access_registry.csv` contains development-only demo accounts for every role. For example, sign in as `mallikarjunareddyaiml@anurag.edu.in` with `hod123`, or as `student@university.edu` with `student123`.

Passwords in this CSV are intentionally only for local demonstration. Before any real deployment, move authentication to an identity provider or store salted password hashes outside the repository, remove demo credentials, and use HTTPS.

### One-email-per-member registration

The sign-in screen has a **Register** tab. A member can register once using an email address; attempting to reuse that email shows an error and directs them to sign in. Self-registration creates a **Student** account only. The Main Authority must create or assign every staff role in `data/access_registry.csv`.

Newly registered passwords are stored as PBKDF2 password digests. This local app checks uniqueness but does not send a verification email; configure an email/identity provider before relying on it for real institutional authentication.
