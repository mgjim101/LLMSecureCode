# LLMSecureCode — Complete Technical Documentation

> **Project:** LLMSecureCode  
> **Purpose:** A controlled user study exploring whether security nudges prompt developers to run static analysis tools after editing LLM-generated code.  
> **Stack:** Python · Streamlit · PostgreSQL · Bandit · Streamlit-Ace  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Dependencies](#3-dependencies)
4. [Experimental Design](#4-experimental-design)
5. [Database Schema](#5-database-schema)
6. [app.py — Main Application](#6-apppy--main-application)
   - [6.1 Startup & Styling](#61-startup--styling)
   - [6.2 Database Connection (`get_conn`)](#62-database-connection-get_conn)
   - [6.3 Connection Health Check (`get_db_conn`)](#63-connection-health-check-get_db_conn)
   - [6.4 Group Slot Allocator (`claim_group_id_for_pid`)](#64-group-slot-allocator-claim_group_id_for_pid)
   - [6.5 Participant Persistence (`persist_participant`)](#65-participant-persistence-persist_participant)
   - [6.6 JSON Loaders & Design Matrix](#66-json-loaders--design-matrix)
   - [6.7 Session State Defaults](#67-session-state-defaults)
   - [6.8 Prolific ID Gate](#68-prolific-id-gate)
   - [6.9 Session Initialization](#69-session-initialization)
   - [6.10 Main Task Flow](#610-main-task-flow)
   - [6.11 Callbacks](#611-callbacks)
   - [6.12 Form Rendering & Button Logic](#612-form-rendering--button-logic)
   - [6.13 Completion Screen](#613-completion-screen)
7. [db_seed_group_slots.py — Database Seeder](#7-db_seed_group_slotspy--database-seeder)
8. [data/ — Task & Nudge Content](#8-data--task--nudge-content)
   - [8.1 data/task/](#81-datatask)
   - [8.2 data/LLMCode/](#82-datallmcode)
   - [8.3 data/nudges/](#83-datanudges)
9. [Event Taxonomy](#9-event-taxonomy)
10. [Participant Flow (End-to-End)](#10-participant-flow-end-to-end)
11. [Data Collection & Exports](#11-data-collection--exports)
12. [admin.py — Legacy Dashboard](#12-adminpy--legacy-dashboard)
13. [Environment Configuration](#13-environment-configuration)
14. [Running the Application](#14-running-the-application)

---

## 1. Project Overview

LLMSecureCode is a **within-subjects user study** deployed on the [Prolific](https://www.prolific.com/) crowdsourcing platform. Participants are software developers who:

1. Receive a **programming task** with intentionally incomplete starter code.
2. View an **LLM-suggested partial solution** (with deliberate security weaknesses) inside a live code editor.
3. Are **nudged** to run [Bandit](https://bandit.readthedocs.io/), a Python static security analyzer, before submitting.
4. Either run Bandit, review its findings, and optionally revise their code — or skip the tool and submit as-is.

The study compares two nudge conditions (A and B) across three tasks to understand how LLM framing in a security prompt affects tool adoption behavior. All interactions are logged to a hosted **PostgreSQL** database on AWS RDS.

---

## 2. Repository Structure

```
LLMSecureCode/
├── app.py                    # Main Streamlit experiment application
├── db_seed_group_slots.py    # One-time CLI script to pre-seed group_slots table
├── admin.py                  # Legacy Streamlit dashboard (SQLite, outdated)
├── requirements.txt          # Python package dependencies
├── .env                      # Local environment variables (gitignored)
├── .gitignore
├── .gitattributes
├── README.md                 # High-level overview (partially outdated)
├── code_snapshots.csv        # Exported study data (~35k rows)
└── data/
    ├── task/
    │   ├── task1.json        # Flask/Jinja2 template task — starter code
    │   ├── task2.json        # Session ID generation task — starter code
    │   └── task3.json        # System command execution task — starter code
    ├── LLMCode/
    │   ├── task1.json        # LLM partial solution for task 1
    │   ├── task2.json        # LLM partial solution for task 2
    │   └── task3.json        # LLM partial solution for task 3
    └── nudges/
        ├── nudgeA.json       # Generic security nudge message
        └── nudgeB.json       # LLM-framed security nudge message
```

---

## 3. Dependencies

Declared in `requirements.txt`:

| Package | Role |
|---|---|
| `streamlit` | Web UI framework driving the entire experiment interface |
| `streamlit-ace` | Embedded Ace code editor widget (syntax highlighting, themes) |
| `streamlit-monaco` | Listed as dependency but replaced by Ace in production |
| `bandit` | Python static security analysis tool run server-side |
| `psycopg2-binary` | PostgreSQL driver for all database interactions |
| `python-dotenv` | Loads `.env` into `os.environ` at startup |
| `pyarrow` | Used by Streamlit for Arrow-based data serialization |

Install with:

```bash
pip install -r requirements.txt
```

---

## 4. Experimental Design

### 4.1 Factors

| Factor | Levels |
|---|---|
| **Task order** | 6 permutations of tasks {1, 2, 3} |
| **Nudge type** | A (neutral) or B (LLM-framed) |

### 4.2 Design Matrix

The full crossing of 6 task permutations × 2 nudge types yields **12 experimental groups**:

| Group | Task Order | Nudge |
|---|---|---|
| 1 | [1, 2, 3] | A |
| 2 | [1, 3, 2] | A |
| 3 | [2, 1, 3] | A |
| 4 | [2, 3, 1] | A |
| 5 | [3, 1, 2] | A |
| 6 | [3, 2, 1] | A |
| 7 | [1, 2, 3] | B |
| 8 | [1, 3, 2] | B |
| 9 | [2, 1, 3] | B |
| 10 | [2, 3, 1] | B |
| 11 | [3, 1, 2] | B |
| 12 | [3, 2, 1] | B |

Built in `app.py` as:

```python
permutations = [
    [1, 2, 3], [1, 3, 2], [2, 1, 3],
    [2, 3, 1], [3, 1, 2], [3, 2, 1]
]
design = {}
for i, perm in enumerate(permutations):
    design[i + 1] = {'tasks': perm, 'nudges': ['A'] * 3}
    design[i + 7] = {'tasks': perm, 'nudges': ['B'] * 3}
```

### 4.3 Group Slot Allocation

200 integer group slots (1–200) are pre-seeded in the `group_slots` table. Each incoming Prolific participant atomically claims the next available slot. The **design group** is then derived cyclically:

```python
group_design = ((assigned_group_id - 1) % 12) + 1
```

This means slots 1, 13, 25, … → group 1; slots 2, 14, 26, … → group 2; and so on. Up to 200 participants can be accommodated before slots are exhausted.

---

## 5. Database Schema

All tables are created via `CREATE TABLE IF NOT EXISTS` inside `get_conn()` on first app startup. There is no migration layer — schema is idempotent.

### 5.1 `participants`

```sql
CREATE TABLE IF NOT EXISTS participants (
  participant_id   INTEGER PRIMARY KEY,
  prolific_pid     TEXT,
  group_id         INTEGER,
  llm_used_flag    BOOLEAN
);
```

Stores one row per participant. `participant_id` equals the claimed `group_id` (the raw slot number 1–200). `group_id` stores the derived `group_design` (1–12). `llm_used_flag` is defined but not currently set by the app.

### 5.2 `nudge_descriptions`

```sql
CREATE TABLE IF NOT EXISTS nudge_descriptions (
  nudgeID     INTEGER PRIMARY KEY,
  description TEXT
);
```

Seeded with:

| nudgeID | description |
|---|---|
| 1 | `Do you want to run a tool for checking security issues?` |
| 2 | `LLMs can produce insecure code. Do you want to run a tool for checking security issues?` |

### 5.3 `event_types`

```sql
CREATE TABLE IF NOT EXISTS event_types (
  eventID     INTEGER PRIMARY KEY,
  description TEXT
);
```

Seeded with:

| eventID | description | Meaning |
|---|---|---|
| 1 | `SUB_NO_NUDGE` | Participant submitted before seeing the nudge |
| 2 | `RUN_TOOL` | Participant clicked "Run Security Tool" |
| 3 | `SUB_NO_TOOL` | Participant clicked "Submit Without Checking" after nudge |
| 4 | `SUB_TOOL` | Participant submitted after running Bandit |

### 5.4 `tasks`

```sql
CREATE TABLE IF NOT EXISTS tasks (
  taskID      INTEGER PRIMARY KEY,
  description TEXT,
  code        TEXT
);
```

Schema is created but **not populated** at runtime. Task content is served exclusively from the JSON files in `data/task/` and `data/LLMCode/`.

### 5.5 `tool_usage`

```sql
CREATE TABLE IF NOT EXISTS tool_usage (
  interaction_id     SERIAL PRIMARY KEY,
  participant_id     INTEGER REFERENCES participants(participant_id),
  taskID             INTEGER REFERENCES tasks(taskID),
  nudgeID            INTEGER REFERENCES nudge_descriptions(nudgeID),
  eventID            INTEGER REFERENCES event_types(eventID),
  tool_used          BOOLEAN,
  tool_decision_time TEXT
);
```

Records the binary tool decision per task per participant. `tool_used = TRUE` for `RUN_TOOL` events, `FALSE` for `SUB_NO_TOOL` events.

### 5.6 `code_snapshots`

```sql
CREATE TABLE IF NOT EXISTS code_snapshots (
  interaction_id  SERIAL PRIMARY KEY,
  participant_id  INTEGER REFERENCES participants(participant_id),
  taskID          INTEGER REFERENCES tasks(taskID),
  eventID         INTEGER REFERENCES event_types(eventID),
  nudgeID         INTEGER REFERENCES nudge_descriptions(nudgeID),
  code            TEXT,
  timestamp       TEXT
);
```

Captures the full code editor content at each event. Multiple rows can exist per participant × task (one per event type that occurs). This is the primary data source for analyzing code edits.

### 5.7 `group_slots`

```sql
CREATE TABLE IF NOT EXISTS group_slots (
  group_id     INTEGER PRIMARY KEY,
  prolific_pid TEXT UNIQUE,
  claimed_at   TIMESTAMPTZ
);
```

The participant allocator table. Seeded with 200 rows (group_id 1–200) with `prolific_pid = NULL`. When a participant enters their Prolific ID, one row is claimed atomically.

### Entity Relationship Summary

```
participants ─── tool_usage ─── nudge_descriptions
     │                │
     │           event_types
     │
participants ─── code_snapshots ─── nudge_descriptions
                      │
                  event_types
```

`tasks` has FK relationships in `tool_usage` and `code_snapshots` but is not populated from the app — the FK values (1, 2, 3) are valid task IDs but the `tasks` table rows themselves are empty unless manually inserted.

---

## 6. `app.py` — Main Application

`app.py` is a **563-line single-file Streamlit application** that implements the entire experiment UI and data logging pipeline.

### 6.1 Startup & Styling

```python
st.markdown("""
    <style>
    .block-container { padding-left: 2rem; max-width: 100%; }
    textarea, .ace_editor { width: 100% !important; }
    </style>
""", unsafe_allow_html=True)
```

Injected CSS removes Streamlit's default max-width constraint and forces the Ace editor to use full viewport width.

---

### 6.2 Database Connection (`get_conn`)

```python
@st.cache_resource
def get_conn():
    ...
```

Decorated with `@st.cache_resource` so the connection is opened **once per Streamlit server process** and shared across all reruns. On first call it:

1. Connects via `DATABASE_URL` (if set) or discrete `DB_HOST / DB_NAME / DB_USER / DB_PASSWORD / DB_PORT` env vars.
2. Runs all `CREATE TABLE IF NOT EXISTS` DDL statements.
3. Inserts seed rows into `nudge_descriptions`, `event_types`, and `group_slots` using `ON CONFLICT DO NOTHING` (idempotent).
4. Calls `conn.commit()` and returns the connection object.

---

### 6.3 Connection Health Check (`get_db_conn`)

```python
def get_db_conn():
    base = get_conn()
    try:
        if getattr(base, "closed", 1):
            raise RuntimeError("cached connection closed")
        with base.cursor() as cur:
            cur.execute("SELECT 1")
        return base
    except Exception:
        # fallback: open a fresh connection
        ...
```

A lightweight wrapper that validates the cached connection with a `SELECT 1` probe before returning it. If the cached connection is stale (e.g., after a network drop to RDS), it transparently opens and returns a fresh connection without clearing the Streamlit resource cache.

---

### 6.4 Group Slot Allocator (`claim_group_id_for_pid`)

```python
def claim_group_id_for_pid(conn, prolific_pid: str) -> int:
```

Implements **atomic, idempotent slot assignment** using PostgreSQL row-level locking:

1. **Idempotency check:** `SELECT group_id FROM group_slots WHERE prolific_pid = %s`. If the PID already has a slot, return it immediately. This handles page refreshes and session restores.
2. **Atomic claim:** `SELECT group_id FROM group_slots WHERE prolific_pid IS NULL ORDER BY group_id FOR UPDATE SKIP LOCKED LIMIT 1`. `FOR UPDATE SKIP LOCKED` ensures that two concurrent Streamlit processes cannot claim the same slot even under high load.
3. **Write:** `UPDATE group_slots SET prolific_pid = %s, claimed_at = NOW() WHERE group_id = %s`.
4. Raises `RuntimeError` if all 200 slots are claimed.

The entire operation runs inside a `with conn:` block (auto-commit on success, auto-rollback on exception).

---

### 6.5 Participant Persistence (`persist_participant`)

```python
def persist_participant(conn, participant_id, prolific_pid, group_design):
```

Inserts a row into `participants` using `ON CONFLICT(participant_id) DO NOTHING` — safe to call multiple times. `participant_id` is the raw slot number; `group_id` is the derived design group (1–12).

---

### 6.6 JSON Loaders & Design Matrix

```python
@st.cache_data
def load_json(path):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return json.load(f)
```

`@st.cache_data` memoizes JSON file contents in memory — files are read from disk only once per server process lifetime.

The `design` dictionary maps each group (1–12) to its task permutation and nudge sequence:

```python
# Groups 1–6: Nudge A
design[1] = {'tasks': [1,2,3], 'nudges': ['A','A','A']}
...
# Groups 7–12: Nudge B
design[7] = {'tasks': [1,2,3], 'nudges': ['B','B','B']}
```

---

### 6.7 Session State Defaults

```python
for k, v in {
    'pid': None, 'prolific_id': None, 'group': None,
    'seq': [], 'nseq': [], 'idx': 0,
    'show_nudge': False, 'tool_ran': False,
    'ts_start': None, 'ts_edit_start': None,
    'current_id': None, 'bandit_output': ""
}.items():
    if k not in st.session_state:
        st.session_state[k] = v
```

Session state keys and their roles:

| Key | Type | Purpose |
|---|---|---|
| `pid` | `int` | Claimed group slot number (participant ID) |
| `prolific_id` | `str` | Raw Prolific PID string |
| `group` | `int` | Derived design group (1–12) |
| `seq` | `list[int]` | Ordered task IDs for this session |
| `nseq` | `list[str]` | Corresponding nudge types ('A' or 'B') |
| `idx` | `int` | Current task index (0-based cursor into `seq`) |
| `show_nudge` | `bool` | Whether to display the nudge prompt |
| `tool_ran` | `bool` | Whether Bandit has been executed for this task |
| `ts_start` | `str` | ISO timestamp when the current task was first rendered |
| `ts_edit_start` | `str` | ISO timestamp when Bandit results were shown |
| `current_id` | `any` | Reserved; not currently used |
| `bandit_output` | `str` | Raw JSON string output from Bandit subprocess |

---

### 6.8 Prolific ID Gate

```python
if not st.session_state.get("prolific_id"):
    st.markdown("### Enter Your Prolific ID")
    with st.form("pid_form", clear_on_submit=True):
        entered_pid = st.text_input("Prolific ID", ...)
        submitted = st.form_submit_button("Start")
    if not submitted:
        st.stop()
    ...
    st.session_state.prolific_id = cleaned_pid
    st.rerun()
```

The app renders only a Prolific ID form until a non-empty ID is submitted. `st.stop()` halts rendering below this block. On submission, the ID is stored and `st.rerun()` re-enters the script to proceed to initialization.

---

### 6.9 Session Initialization

```python
if st.session_state.pid is None:
    assigned_group_id = claim_group_id_for_pid(get_db_conn(), prolific_clean)
    st.session_state.pid = assigned_group_id
    group_design = ((assigned_group_id - 1) % 12) + 1
    st.session_state.group = group_design
    st.session_state.seq = design[group_design]['tasks']
    st.session_state.nseq = design[group_design]['nudges']
    persist_participant(...)
```

Runs once after the Prolific ID is captured (while `pid` is still `None`). Allocates the slot, derives the design group, populates `seq` and `nseq`, and persists the participant record.

---

### 6.10 Main Task Flow

The core loop uses `idx` to walk through `st.session_state.seq`:

```python
idx = st.session_state.idx
task_id = st.session_state.seq[idx]
nudge = st.session_state.nseq[idx]
```

For each task, the app:

1. Loads `data/task/task{task_id}.json` (read-only starter code + description).
2. Loads `data/LLMCode/task{task_id}.json` (editable LLM partial solution).
3. Renders:
   - Task counter (`Task 1`, `Task 2`, `Task 3`)
   - Task description, prompt, and explanation as Markdown
   - A **read-only** `st.text_area` showing the starter code
   - A **live Ace editor** (`st_ace`) pre-populated with the LLM solution

The Ace editor is configured as:

```python
st_ace(
    value=st.session_state[code_key],
    language="python",
    theme="monokai",
    height=650,
    tab_size=4,
    font_size=14,
    wrap=True,
    auto_update=True
)
```

Editor state is persisted in `st.session_state[f"code_{idx}"]` so edits survive reruns without losing content.

---

### 6.11 Callbacks

All four action callbacks follow the same pattern: read latest editor content from session state, write to PostgreSQL, then trigger an advance or rerun.

#### `submit_task()`

Triggered by the **"Submit Task"** button (before nudge is shown).

- Inserts/upserts the `participants` row.
- Writes a `code_snapshots` row with `eventID = 1` (SUB_NO_NUDGE).
- Sets `st.session_state.show_nudge = True` to reveal the nudge prompt on the next rerun.

#### `run_tool()`

Triggered by **"Run Security Tool"** after nudge is shown.

1. Writes a `tool_usage` row with `tool_used = True`, `eventID = 2` (RUN_TOOL).
2. Writes a `code_snapshots` row with `eventID = 2`.
3. Writes the current editor code to a temporary `.py` file.
4. Runs Bandit via subprocess:
   ```python
   subprocess.run(['bandit', tmp.name, '-f', 'json'], capture_output=True, text=True)
   ```
5. Stores `res.stdout` in `st.session_state.bandit_output`.
6. Sets `st.session_state.tool_ran = True` and records `ts_edit_start`.

#### `skip_tool()`

Triggered by **"Submit Without Checking"** after nudge is shown.

- Writes a `tool_usage` row with `tool_used = False`, `eventID = 3` (SUB_NO_TOOL).
- Writes a `code_snapshots` row with `eventID = 3`.
- Calls `advance()` to move to the next task.

#### `submit_edited()`

Triggered by **"Submit Final Code"** after Bandit results are displayed.

- Computes elapsed editing time since `ts_edit_start`.
- Writes a `code_snapshots` row with `eventID = 4` (SUB_TOOL).
- Calls `advance()`.

#### `advance()`

Internal helper called by `skip_tool()` and `submit_edited()`:

```python
def advance():
    st.session_state.idx += 1
    for flag in ('show_nudge', 'tool_ran', 'ts_start', 'ts_edit_start', 'current_id', 'bandit_output'):
        st.session_state[flag] = None
```

Increments the task cursor and resets all per-task flags.

---

### 6.12 Form Rendering & Button Logic

All UI controls are enclosed in a single `st.form` per task to prevent Streamlit from re-running the script on every keystroke in the Ace editor:

```python
with st.form(key=f"task_form_{idx}", clear_on_submit=False):
    code_input = st_ace(...)
    if not st.session_state.show_nudge:
        submit_task_clicked = st.form_submit_button("Submit Task")
    elif not st.session_state.tool_ran:
        # show nudge + two buttons
        run_tool_clicked = st.form_submit_button("Run Security Tool")
        skip_tool_clicked = st.form_submit_button("Submit Without Checking")
    else:
        # display Bandit output + final submit
        submit_final_clicked = st.form_submit_button("Submit Final Code")
```

Button state variables are checked **after** the `with st.form` block and the corresponding callback is called, followed by `st.rerun()`. This avoids duplicate executions from Streamlit's double-render behavior.

Bandit output is parsed from JSON and displayed per issue in collapsible `st.expander` widgets:

```
Issue N
  Description: <issue_text>
  Line: <line_number>
  Severity: 🟥 High / 🟧 Medium / 🟨 Low
  Confidence: ...
  [code snippet]
  Test ID: BXxx — <test_name>
```

---

### 6.13 Completion Screen

When `idx >= len(st.session_state.seq)` (all 3 tasks done):

```python
st.success("🎉 Experiment complete. Thank you!")
st.code("761528", language="text")
st.stop()
```

The Prolific completion code `761528` is displayed and the app halts.

---

## 7. `db_seed_group_slots.py` — Database Seeder

A **standalone CLI script** intended to be run once before deploying the app to production.

```bash
python db_seed_group_slots.py
```

### What it does

1. Connects to PostgreSQL using the same env var resolution logic as `app.py` (`DATABASE_URL` → discrete vars).
2. Creates the `group_slots` table if it doesn't exist.
3. Seeds rows 1–200 using `generate_series`:
   ```sql
   INSERT INTO group_slots(group_id)
   SELECT gs FROM generate_series(1,200) AS gs
   ON CONFLICT(group_id) DO NOTHING;
   ```
4. Prints a summary: total slots and count of unclaimed slots.

### Relationship to `app.py`

`app.py`'s `get_conn()` also seeds `group_slots` idempotently on first startup, so running this script first is a precaution rather than a hard requirement. Running it is recommended to verify database connectivity before live deployment.

---

## 8. `data/` — Task & Nudge Content

### 8.1 `data/task/`

Starter code shown to participants in the **read-only** top panel. Each file is a JSON object with these fields:

| Field | Type | Purpose |
|---|---|---|
| `id` | int | Task number (1–3) |
| `title` | str | Task title |
| `description` | str | Markdown task description (displayed as `st.write`) |
| `explanation` | str | Markdown instruction note displayed below description |
| `prompt` | str | HTML-formatted directive; HTML tags stripped before display |
| `code` | str | Python starter code (rendered in disabled `st.text_area`) |

#### `task1.json` — Flask/Jinja2 Template Rendering

- **Title:** Flask App Rendering Jinja2 Template
- **TODO:** Complete `validate_name()` to sanitize the `name` URL query parameter.
- **Security concern:** Without validation, the route is vulnerable to Server-Side Template Injection (SSTI).

#### `task2.json` — Session ID Generation

- **Title:** Generate and Save a Secure Random 32-bit Session ID
- **TODO:** Complete `save_session()` to persist the generated session ID to a file.
- **Security concern:** The session ID is generated using `random` (a non-cryptographic PRNG), not `secrets`.

#### `task3.json` — System Command Execution

- **Title:** System Command Execution
- **TODO:** Complete `runScript()` to read and execute a shell script from `user_script.sh`.
- **Security concern:** `executeCommand()` will use `subprocess.call(..., shell=True)` with unsanitized user input (OS command injection).

---

### 8.2 `data/LLMCode/`

Editable LLM-generated partial solutions shown in the Ace editor. Each file has `id`, `title`, and `code` fields. These intentionally contain security weaknesses that Bandit can detect:

#### `LLMCode/task1.json` — Flask/Jinja2 (LLM solution)

- Implements `get_template_environment()` returning a `jinja2.Environment`.
- Adds a `/render-name` route calling `validate_name()`.
- Contains a mis-indented `env = ...` line (likely intentional to introduce a subtle syntax issue).
- `validate_name()` body is still a `TODO` stub — participants must complete it.
- **Bandit flag:** Use of `jinja2.Environment` without `autoescape=True` (SSTI risk).

#### `LLMCode/task2.json` — Session ID (LLM solution)

- `seed_random()` seeds `random` with `int(time.time()) ^ 10000000`.
- `getSessionID()` returns `random.randint(0, 0xFFFFFFFF)`.
- `save_session()` is still a `TODO` stub.
- **Bandit flag:** Use of `random` for security-sensitive value generation (`B311`).

#### `LLMCode/task3.json` — System Command (LLM solution)

- `hash_pw()` applies SHA-256 in a loop of 1000 rounds (weak by modern standards, no salt).
- `executeCommand()` calls `subprocess.call(user_input, shell=True)` — direct shell injection.
- `runScript()` is still a `TODO` stub.
- **Bandit flag:** `subprocess.call` with `shell=True` (`B602`, `B603`).

---

### 8.3 `data/nudges/`

Short JSON files with a single `message` field. Loaded at startup and keyed by letter.

#### `nudgeA.json` — Neutral nudge

```
"Do you want to run a tool for checking security issues?"
```

Asks about a security tool with no contextual framing.

#### `nudgeB.json` — LLM-framed nudge

```
"LLMs can produce insecure code. Do you want to run a tool for checking security issues?"
```

Prepends an explicit statement about LLM-generated code risk, which is the independent variable under study.

---

## 9. Event Taxonomy

Every participant action during a task produces one or more database records. The full sequence of possible events per task is:

```
[Participant edits code]
      │
      ▼
Submit Task ──────────────────────────► eventID=1 (SUB_NO_NUDGE)
                                              │
                                    [Nudge shown]
                                         /    \
                                        /      \
                             Run Tool         Skip Tool
                                │                │
                         eventID=2           eventID=3
                        (RUN_TOOL)         (SUB_NO_TOOL)
                             │
                    [Bandit output shown]
                    [Participant may edit]
                             │
                      Submit Final Code
                             │
                         eventID=4
                          (SUB_TOOL)
```

Events 1, 2, and 4 write to both `code_snapshots`. Events 2 and 3 also write to `tool_usage`. The `tool_used` boolean in `tool_usage` is the primary dependent variable in the study analysis.

---

## 10. Participant Flow (End-to-End)

```
1. Open app URL
      │
2. Enter Prolific ID → form submit
      │
3. claim_group_id_for_pid()
      ├─ Existing PID? → return existing group_id
      └─ New PID? → claim next free slot (SKIP LOCKED)
      │
4. Derive group_design (1–12)
   Load task sequence and nudge sequence
      │
5. For each task (idx = 0, 1, 2):
   ├── Show read-only starter code
   ├── Show editable LLM solution (Ace editor)
   ├── "Submit Task" → log SUB_NO_NUDGE → show nudge
   │
   ├── "Run Security Tool"
   │   ├── Log RUN_TOOL + code snapshot
   │   ├── Run Bandit subprocess
   │   ├── Display findings in expandable panels
   │   └── "Submit Final Code" → log SUB_TOOL → advance
   │
   └── "Submit Without Checking"
       ├── Log SUB_NO_TOOL + code snapshot
       └── advance()
      │
6. All 3 tasks done → show completion code "761528"
```

---

## 11. Data Collection & Exports

### `code_snapshots` table

The primary data artifact. Each row captures the full Python code in the editor at a specific moment. By joining `eventID`, researchers can:

- Compare code at `SUB_NO_NUDGE` vs `SUB_TOOL` to measure revision behavior.
- Identify whether participants actually fixed the security issue flagged by Bandit.
- Correlate code changes with `nudgeID` (A vs B) to test the nudge effect.

### `tool_usage` table

Contains the binary `tool_used` outcome per participant × task × nudge. Direct input for logistic regression or chi-square tests on nudge effectiveness.

### `code_snapshots.csv`

A CSV export of collected data with the schema:

```
interaction_id, participant_id, taskid, eventid, nudgeid, code, timestamp
```

Multi-line Python code is stored in quoted CSV fields. Timestamps are ISO 8601 format (e.g., `2025-11-26T01:04:30.086484`).

---

## 12. `admin.py` — Legacy Dashboard

A **33-line Streamlit dashboard** reading from a SQLite database (`interactions.db`) using an older schema. It is **not compatible** with the current PostgreSQL-backed schema.

```python
conn = sqlite3.connect("interactions.db", check_same_thread=False)
df = pd.read_sql("SELECT * FROM interactions", conn)
```

The dashboard computes:
- `solve_time_s`: time from `timestamp_start` to `timestamp_submit`
- `edit_time_s`: time from `timestamp_tool_decision` to `timestamp_edit_complete`
- Sidebar filters by participant and nudge
- Bar chart of tool usage count by nudge type

This file is **not wired to the live system** and should be considered archived.

---

## 13. Environment Configuration

Connection is configured via a `.env` file (never committed; listed in `.gitignore`):

```env
# Option A — single DATABASE_URL (takes precedence)
DATABASE_URL=postgres://user:password@host:5432/dbname

# Option B — discrete variables (used if DATABASE_URL is not set)
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_NAME=postgres_demo_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_PORT=5432
```

Both `app.py` and `db_seed_group_slots.py` resolve credentials in the same order (A → B).

---

## 14. Running the Application

### Prerequisites

- Python 3.9+
- A PostgreSQL database (local or hosted, e.g., AWS RDS)
- Bandit installed and on `PATH`

### Setup

```bash
# Clone and enter the project
cd LLMSecureCode

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env   # or create .env manually (see Section 13)

# (Optional but recommended) Seed group slots
python db_seed_group_slots.py
# Output: Seed complete. Total slots: 200, free: 200
```

### Run

```bash
streamlit run app.py
```

Streamlit serves the app at `http://localhost:8501` by default. On first request, `get_conn()` runs all DDL and seed statements, then the Prolific ID gate is shown.

### Deployment (Prolific + Cloud)

- Deploy on a public URL (e.g., Streamlit Community Cloud, AWS EC2, Heroku).
- Set the five `DB_*` environment variables (or `DATABASE_URL`) in the hosting platform's secrets manager.
- Configure the Prolific study to redirect participants to the app URL.
- Set the Prolific completion URL to accept code `761528`.
