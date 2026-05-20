# LLMSecureCode — Security-Nudge / GenAI Coding-Tool Study

A Prolific crowdsourcing experiment investigating whether **security-emphasizing nudges** change how software developers interact with LLM-generated code, whether those behavioral changes improve security outcomes, and how they shift psychological attitudes toward GenAI coding tools.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Application (`app.py`)](#3-application-apppy)
   - [Getting Started](#31-getting-started)
   - [Experimental Design](#32-experimental-design)
   - [Participant Flow](#33-participant-flow)
   - [Database Schema](#34-database-schema)
4. [Data Directory (`data/`)](#4-data-directory-data)
5. [Analysis Pipeline (`Analysis/`)](#5-analysis-pipeline-analysis)
   - [Data Sources](#51-data-sources)
   - [Pipeline Overview](#52-pipeline-overview)
   - [Folder Descriptions](#53-folder-descriptions)
6. [Documentation (`docs/`)](#6-documentation-docs)
7. [Reproducing the Analysis](#7-reproducing-the-analysis)
8. [Dependencies](#8-dependencies)
9. [Known Issues and Caveats](#9-known-issues-and-caveats)

---

## 1. Project Overview

**Study question.** Does exposing developers to security-emphasizing nudges — messages explicitly warning them that LLM-generated code may contain vulnerabilities — increase their likelihood of running a static security scanner (Bandit), making code changes, and ultimately reducing vulnerability counts?

**Design.** Between-subjects experiment with two nudge conditions:

| Condition | Label | `NudgeType` | Description |
|-----------|-------|-------------|-------------|
| **Nudge A** | Control | 0 | Generic feedback prompt (no explicit security framing) |
| **Nudge B** | Treatment | 1 | Security-emphasizing warnings highlighting risks in the generated code |

**Sample.** N = **97** participants (48 Nudge A, 49 Nudge B) after filtering. Recruited via Prolific; follow-up survey via LimeSurvey.

**Primary finding.** Nudge B significantly increased the rate at which participants changed their code after using the security tool (β = +0.22, p = .029) and produced larger reductions in high-severity Bandit findings (mean HighSeverityDiff = −0.35 vs. −0.15 for Nudge A).

---

## 2. Repository Structure

```
LLMSecureCode/
│
├── app.py                          # Main Streamlit experiment (PostgreSQL backend)
├── admin.py                        # Legacy Streamlit dashboard (SQLite — outdated)
├── db_seed_group_slots.py          # CLI utility: seed group_slots 1–200 in PostgreSQL
├── requirements.txt                # Python dependencies for the application
│
├── data/                           # Static content loaded by app.py at runtime
│   ├── task/                       # Task definitions (instructions + starter code)
│   │   ├── task1.json
│   │   ├── task2.json
│   │   └── task3.json
│   ├── LLMCode/                    # LLM-generated code shown to participants
│   │   ├── task1.json
│   │   ├── task2.json
│   │   └── task3.json
│   └── nudges/                     # Nudge message text
│       ├── nudgeA.json
│       └── nudgeB.json
│
├── Analysis/                       # Full quantitative analysis pipeline
│   ├── Tool_CSV/                   # Raw telemetry exports from PostgreSQL (source of truth)
│   ├── Tool_JSON/                  # JSON mirrors of Tool_CSV tables
│   ├── LLMCode/                    # LLM baseline code copies for Bandit comparison
│   ├── data_cleanup/               # Steps 1–2: participant inclusion filtering
│   ├── tool_usage/                 # Step 3: per-participant tool-use summary
│   ├── code_changes_with_tool/     # Step 4: code change detection (tool arm)
│   ├── code_changes_without_tool/  # Step 5: code change detection (nudge-only arm)
│   ├── bandit_comparison_with_tool/     # Step 6: Bandit diffs (tool arm)
│   ├── bandit_comparison_without_tool/  # Step 7: Bandit diffs (nudge-only arm)
│   ├── nudge_to_completion_duration/    # Step 8: timing from nudge to completion
│   ├── Aggregation/                # Steps 9–10: merged wide summary tables
│   ├── SEM_Analysis/               # R structural equation modeling (canonical: SEMFinal.R)
│   ├── psychological_constructs_analysis/  # Construct reliability + paired tests
│   └── rq1_statistical_analysis/          # Between-group hypothesis tests
│
└── docs/                           # Technical documentation
    ├── README.md                   # Analysis master README (pipeline details, key results)
    ├── Platform.md                 # Full app.py / PostgreSQL / participant-flow documentation
    ├── CSV_BUILD_METHODS.md        # Step-by-step lineage for all 10 pipeline scripts
    ├── TABLE_DOCUMENTATION.md      # Column-level schema for every derived CSV
    └── SEM_ANALYSIS.md             # SEM methods, script evolution, reproducibility notes
```

---

## 3. Application (`app.py`)

The experiment runs as a **Streamlit** web application backed by **PostgreSQL**. Participants are recruited via Prolific and directed to the app URL.

### 3.1 Getting Started

**Prerequisites:** Python 3.9+, PostgreSQL instance, `bandit` on `PATH`.

```bash
# 1. Clone and install
git clone <repo-url>
cd LLMSecureCode
pip install -r requirements.txt

# 2. Configure the database (create a .env file at the repo root)
# Option A — connection string
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Option B — individual variables
DB_HOST=localhost
DB_NAME=llmsecurecode
DB_USER=youruser
DB_PASSWORD=yourpassword
DB_PORT=5432

# 3. Seed group assignment slots (run once)
python db_seed_group_slots.py

# 4. Launch the experiment
streamlit run app.py
```

> `app.py` auto-creates all required tables on first connect if they do not already exist.

### 3.2 Experimental Design

Participants are assigned to one of **12 design cells** (6 task permutations × 2 nudge types). The assignment is managed by the `group_slots` table, which maps slot numbers 1–200 to Prolific PIDs atomically.

| group_id | Task order | Nudge |
|----------|-----------|-------|
| 1–6 | All 6 permutations of tasks 1, 2, 3 | Nudge A (control) |
| 7–12 | All 6 permutations of tasks 1, 2, 3 | Nudge B (security) |

**Completion code:** `761528` — participants enter this in the LimeSurvey follow-up questionnaire to confirm they completed the study.

**Event taxonomy** (used throughout app and analysis):

| Event ID | Name | When logged |
|----------|------|-------------|
| 1 | `SUB_NO_NUDGE` | Participant submits code *before* the nudge is shown |
| 2 | `RUN_TOOL` | Participant chooses to run the Bandit security scanner |
| 3 | `SUB_NO_TOOL` | Participant submits code *after* nudge but *without* running the tool |
| 4 | `SUB_TOOL` | Participant submits code *after* using the tool |

### 3.3 Participant Flow

```
Enter Prolific ID → claim group_id from group_slots
         │
         ▼  (repeated for each of 3 tasks)
  View starter code (read-only)
  Edit LLM-generated code in Ace editor
         │
         ▼
  Submit Task ──────────── logs event 1 (SUB_NO_NUDGE)
         │
         ▼
  Nudge displayed (A or B)
         │
    ┌────┴────┐
    │         │
Run Tool    Skip Tool
(event 2)   (event 3 → next task)
    │
    ▼
  Bandit JSON report shown
  Optionally edit code
    │
    ▼
  Submit Final Code ─────── logs event 4 (SUB_TOOL)
         │
         ▼  (after all 3 tasks)
  Display completion code: 761528
```

### 3.4 Database Schema

All tables are auto-created by `app.py` on startup.

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `participants` | `participant_id`, `prolific_pid`, `group_id`, `llm_used_flag` | One row per participant |
| `code_snapshots` | `interaction_id`, `participant_id`, `taskid`, `eventid`, `nudgeid`, `code`, `timestamp` | Every code submission |
| `tool_usage` | `interaction_id`, `participant_id`, `taskid`, `nudgeid`, `eventid`, `tool_used`, `tool_decision_time` | Tool run/skip decisions |
| `nudge_descriptions` | `nudgeid`, `description` | Nudge text (seeded: 1 = generic, 2 = security) |
| `event_types` | `eventid`, `description` | Event label lookup |
| `tasks` | `taskid`, `description`, `code` | Task metadata |
| `group_slots` | `group_id`, `prolific_pid`, `claimed_at` | Slot → participant mapping |

---

## 4. Data Directory (`data/`)

Static JSON files loaded by `app.py` at runtime. None of these files are modified during the experiment.

| Path | Schema | Contents |
|------|--------|----------|
| `data/task/taskN.json` | `{id, title, explanation, description, prompt, code}` | Task instructions and read-only starter code |
| `data/LLMCode/taskN.json` | `{id, title, code}` | LLM-generated code shown in the editable Ace editor; contains intentional security vulnerabilities |
| `data/nudges/nudgeA.json` | `{message}` | Generic nudge text (control condition) |
| `data/nudges/nudgeB.json` | `{message}` | Security-emphasizing nudge text (treatment condition) |

**Task security themes** (Bandit findings expected per task):

| Task | Theme | Key Bandit IDs | CWE |
|------|-------|----------------|-----|
| 1 | Flask/Jinja2 template rendering | B701 | CWE-80 (XSS) |
| 2 | Session token / randomness | B311 | CWE-330 (Insufficient Randomness) |
| 3 | Subprocess / OS command execution | B404, B602, B603, B607, B105 | CWE-78, CWE-426, CWE-259 |

---

## 5. Analysis Pipeline (`Analysis/`)

### 5.1 Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Tool telemetry (CSV) | `Tool_CSV/` | Per-event code snapshots, tool decisions, participant ↔ group mapping |
| Tool telemetry (JSON) | `Tool_JSON/` | JSON mirrors of the CSV tables |
| LLM baselines | `LLMCode/task*.json` | AI-generated starter code used as Bandit baseline |
| Survey responses | `Aggregation/results-survey641369.csv` | LimeSurvey export; pre/post Likert items for five psychological constructs |
| Derived wide table | `Aggregation/participant_profiles_schema.csv` | **Primary SEM input** — one row per participant with all behavioral, security, and survey columns joined |

### 5.2 Pipeline Overview

The analysis has three logical stages:

```
Stage 1 — Python Data Preparation (Steps 1–10)
  Raw telemetry + survey → participant_profiles_schema.csv

Stage 2 — R Structural Equation Modeling
  participant_profiles_schema.csv → SEM path models + group tests + CWE tables

Stage 3 — Python Supplementary Analyses
  participant_profiles_schema.csv → RQ1 between-group tests + construct reliability
```

**Recommended script execution order:**

| Step | Script | Purpose |
|------|--------|---------|
| 1 | `data_cleanup/filter_limesurvey.py` | Filter survey by completion code `761528` |
| 2 | `data_cleanup/find_complete_prolific_ids.py` | Build participant inclusion list |
| 3 | `tool_usage/generate_tool_usage_summary.py` | Summarize per-participant tool use/skip |
| 4 | `code_changes_with_tool/code_changes_after_tool.py` | Detect code changes (events 2 → 4) |
| 5 | `code_changes_without_tool/code_changes_after_nudge.py` | Detect code changes (events 1 → 3) |
| 6 | `bandit_comparison_with_tool/bandit_comparison.py` | Bandit diffs for tool arm |
| 7 | `bandit_comparison_without_tool/bandit_comparison_nudge.py` | Bandit diffs for nudge-only arm |
| 8 | `nudge_to_completion_duration/nudge_to_completion_durations.py` | Timing analysis |
| 9 | `Aggregation/aggregate_nudge_metrics.py` | Wide 2-row nudge summary |
| 10 | `Aggregation/generate_participant_profiles_schema.py` | One-row-per-participant master table |
| 11 *(opt.)* | `rq1_statistical_analysis/rq1_statistical_analysis.py` | Between-group hypothesis tests |
| 12 *(opt.)* | `psychological_constructs_analysis/psychological_constructs_analysis.py` | Construct reliability + paired tests |
| 13 | `SEM_Analysis/SEMFinal.R` | Canonical SEM (open via `SEM_Analysis.Rproj`) |

> **Important:** Steps 4–8 depend on `outputs/prolific_ids_with_counts.txt`, which is created by step 2. The `outputs/` directory must exist before running step 2. Additionally, `find_complete_prolific_ids.py` contains a hardcoded `BASE_DIR` path that must be updated if the repository is moved.

### 5.3 Folder Descriptions

#### `Tool_CSV/` and `Tool_JSON/`

Raw exports from the PostgreSQL database. These are the source of truth for all downstream analysis. JSON files mirror the CSV tables in array-of-objects format.

Key files: `participants.csv`, `code_snapshots.csv`, `tool_usage.csv`, `event_types.csv`, `tasks.csv`, `nudge_descriptions.csv`, `group_slots.csv`, `results-survey641369.csv`.

---

#### `data_cleanup/`

**Steps 1–2.** Builds the participant inclusion list used by all downstream scripts.

- `filter_limesurvey.py` — Filters the LimeSurvey export to rows where the confirmation code equals `761528`. Output: `filter_limesurvey_ids.csv`.
- `find_complete_prolific_ids.py` — Intersects survey candidates with telemetry: requires presence in both `code_snapshots.csv` and `tool_usage.csv`. Detects and flags duplicate Prolific IDs. Output: `prolific_ids_with_counts.csv` / `prolific_ids_with_counts.txt` (backbone used by all downstream scripts).

---

#### `tool_usage/`

**Step 3.** Summarizes per-participant tool-use decisions.

- `generate_tool_usage_summary.py` — For each `(participant_id, task_id)`, selects the latest decision by timestamp. Maps `group_id` 1–6 → Nudge A, 7–12 → Nudge B. Computes per-nudge tool-use rates.
- Outputs: `tool_usage_participant_summary.csv`, `tool_usage_task_interactions.csv`, `tool_usage_global_metrics.csv`, `tool_usage_nudge_counts.csv`, `tool_usage_nudge_comparison.csv`.

---

#### `code_changes_with_tool/`

**Step 4.** Detects whether participants edited their code after running the tool.

- `code_changes_after_tool.py` — Compares event 2 (`RUN_TOOL`) snapshot to event 4 (`SUB_TOOL`) snapshot. Computes `changed` boolean, line count metrics (`start_lines`, `end_lines`, `line_delta`), and timestamps.
- Outputs: per-task CSVs, summary, nudge counts, `.txt` report.
- `plots/` — Histograms and QQ plots of change distributions per task.

---

#### `code_changes_without_tool/`

**Step 5.** Same logic as step 4 for the nudge-only arm: participants who skipped the tool.

- `code_changes_after_nudge.py` — Compares event 1 (`SUB_NO_NUDGE`) to event 3 (`SUB_NO_TOOL`).
- Outputs: per-task CSVs, summary, nudge counts, `.txt` report, distribution plots.

---

#### `bandit_comparison_with_tool/`

**Step 6.** Runs Bandit on LLM baseline code vs. participants' final code (event 4) for any task where the code changed.

- `bandit_comparison.py` — Executes `bandit -f json` via subprocess. Computes issue totals, severity diffs (high / medium / low), and change-type classifications (`new` / `fixed` / `common`) per participant-task pair.
- Outputs: `bandit_comparison_llm_tasks.csv` (baseline), `bandit_comparison_participant_submissions.csv`, `bandit_comparison_type_changes.csv`, per-nudge aggregates, `bandit_comparison.txt`.

---

#### `bandit_comparison_without_tool/`

**Step 7.** Same Bandit comparison flow for the nudge-only arm (event 3 submissions).

- `bandit_comparison_nudge.py` — Uses event 1 → 3 submissions.
- Outputs: matching CSV set with `_nudge_` infix.

> **Known issue:** the output file is named `bandit_comparison_nudge_task_total_diffs.csv` but the aggregator in step 9 reads the legacy name `bandit_comparison_nudge_nudge_task_total_diffs.csv`. Rename the file before running step 9.

---

#### `nudge_to_completion_duration/`

**Step 8.** Measures elapsed time from the moment the nudge is shown to task completion.

- `nudge_to_completion_durations.py` — Earliest event 1 timestamp to earliest event 3 or 4 timestamp per participant-task. Reports seconds and `hh:mm:ss`; averages by task × nudge group.
- Outputs: `nudge_to_completion_durations.csv`, `nudge_to_completion_avg_by_task_nudge.csv`, nudge counts, `.txt` report, `.xlsx` rollup.

---

#### `Aggregation/`

**Steps 9–10.** Merges all upstream outputs into summary tables.

- `aggregate_nudge_metrics.py` — Produces a 2-row wide table (one row per nudge group) aggregating ~21 metrics per task across all upstream CSVs. Output: `nudge_aggregated_summary.csv`.
- `generate_participant_profiles_schema.py` — **Primary analytical input.** Builds a one-row-per-participant table by joining all upstream derived tables with the full LimeSurvey export. Selects with-tool or without-tool metrics based on whether the participant used the tool. Handles duplicate survey headers and keeps the best-matching survey row per Prolific ID. Output: `participant_profiles_schema.csv`.

---

#### `SEM_Analysis/`

Structural equation modeling in R. Three scripts represent the evolution of the model:

| Script | Mediator variable | Status |
|--------|-------------------|--------|
| `sem_analysis.r` | `FollowCount` (tasks with tool used, 0–3) | Historical |
| `SEM_CodeChanges.R` | `CodeChangesWithTool` (tasks with tool used AND code changed, 0–3) | Intermediate |
| **`SEMFinal.R`** | `CodeChangesWithTool` + CWE/Bandit parsing + per-group tests | **Canonical** |

**Conceptual SEM model:**

```
NudgeType (A=0, B=1)
      │
  H1  ▼
CodeChangesWithTool ─── H2a ──▶ PostRiskTolerance ─┐
                    ─── H2b ──▶ PostSelfEfficacy   │  H4a/b/c ──▶ PostBehavioralIntention
                    ─── H2c ──▶ PostTrust          ─┘                     ▲
      │                                                               H5   │
  H3a └──────────────────────────────────────────────▶ PostRiskTolerance  │
  H3b ──────────────────────────────────────────────▶ PostTrust      Motivation
```

**Psychological constructs measured (pre and post):**

| Construct | Items | Scale | Notes |
|-----------|-------|-------|-------|
| Motivation (trait) | 3 | 6-pt agreement | Baseline only |
| Risk Tolerance | 3 | 6-pt agree (PRE), 5-pt frequency (POST) | Normalized to 0–1; items 1 & 2 reverse-scored |
| Self-Efficacy | 4 | 6-pt agreement | Item 2 reverse-scored |
| Trust | 4 | 6-pt agreement | No reverse scoring |
| Behavioral Intention | 3 | 6-pt agreement | No reverse scoring |

**Estimation:** FIML for missing data, bootstrap SE (5000 replications). Three model variants per script: main (post scores), change-score (Δ = post − pre), and main + direct effect.

**Output directories:**

| Directory | Written by | Canonical? |
|-----------|------------|-----------|
| `sem_outputs/` | `sem_analysis.r` | No |
| `sem_outputs_codechanges/` | `SEM_CodeChanges.R` and `SEMFinal.R` | No |
| `sem_outputs_codechanges_nudges/` | Manually copied from above | **Yes** |

---

#### `psychological_constructs_analysis/`

Supplementary Python analysis of the five psychological constructs.

- `psychological_constructs_analysis.py` — Scores Likert composites, computes Cronbach's α, and tests pre→post shifts using paired t-tests (parametric) and Wilcoxon signed-rank (non-parametric). Optionally runs a path-regression SEM via `semopy`.
- Outputs: `construct_composites.csv`, `paired_ttest_results.csv`, `sem_results.csv`, `construct_analysis_report.txt`.

---

#### `rq1_statistical_analysis/`

Supplementary Python analysis for the primary between-group research question.

- `rq1_statistical_analysis.py` — Tests Nudge A vs. Nudge B across tool usage, vulnerability metrics, and code changes. Decision protocol: Shapiro–Wilk normality → Levene variance homogeneity → Welch's t-test or Mann–Whitney U → Hedges' g or rank-biserial r. Bonferroni correction (α / 3) for three primary comparisons.
- Outputs: `rq1_statistical_analysis.txt`, `rq1_statistical_analysis_summary.csv`, `rq1_stats.xlsx`.

---

#### `LLMCode/`

Copies of `data/LLMCode/task*.json` used as Bandit baselines in steps 6 and 7.

---

## 6. Documentation (`docs/`)

All detailed technical documentation lives in the `docs/` folder at the repository root.

| File | Purpose |
|------|---------|
| **`docs/README.md`** | Master analysis README: study design, full `Analysis/` tree, pipeline run order, all Python/R scripts, key SEM results, dependencies, and known issues |
| **`docs/Platform.md`** | Full technical documentation for `app.py`: PostgreSQL schema, participant flow, group assignment logic, Bandit integration, environment configuration (~880 lines) |
| **`docs/CSV_BUILD_METHODS.md`** | Step-by-step lineage for all 10 Python pipeline scripts: inputs, outputs, and internal logic for each step |
| **`docs/TABLE_DOCUMENTATION.md`** | Column-level schema reference for every derived CSV table and for `participant_profiles_schema.csv` (the primary SEM input) |
| **`docs/SEM_ANALYSIS.md`** | Complete SEM methods documentation: construct measurement and scale coding, lavaan model syntax, per-script differences, reproducibility notes, output directory reference, and all known issues |

> `docs/SEM_RESULTS.md` (referenced in `docs/README.md`) is not currently present in the repository.

---

## 7. Reproducing the Analysis

### Python pipeline

```bash
# Prerequisites (analysis dependencies — add to your environment separately)
pip install pandas scipy semopy bandit openpyxl pingouin

# Run from the Analysis/ directory in order
cd Analysis

# Before running: edit BASE_DIR in data_cleanup/find_complete_prolific_ids.py
# to point to the correct absolute path if the repo has moved.

python data_cleanup/filter_limesurvey.py
python data_cleanup/find_complete_prolific_ids.py
python tool_usage/generate_tool_usage_summary.py
python code_changes_with_tool/code_changes_after_tool.py
python code_changes_without_tool/code_changes_after_nudge.py
python bandit_comparison_with_tool/bandit_comparison.py
python bandit_comparison_without_tool/bandit_comparison_nudge.py
python nudge_to_completion_duration/nudge_to_completion_durations.py
python Aggregation/aggregate_nudge_metrics.py
python Aggregation/generate_participant_profiles_schema.py

# Optional supplementary analyses
python rq1_statistical_analysis/rq1_statistical_analysis.py
python psychological_constructs_analysis/psychological_constructs_analysis.py
```

### R SEM (canonical)

```r
# In RStudio:
# 1. Open SEM_Analysis/SEM_Analysis.Rproj
# 2. Edit the base_path constant at the top of SEMFinal.R if the repo has moved
# 3. Install required packages:
install.packages(c("tidyverse", "readr", "psych", "lavaan", "semPlot",
                   "effectsize", "broom", "knitr", "stringr"))

# 4. Source the canonical script:
source("SEMFinal.R")
```

> Bootstrap CIs depend on the RNG state. Add `set.seed(<value>)` before the `sem(...)` calls to reproduce identical results.

---

## 8. Dependencies

### Application (`app.py`)

Listed in `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI framework |
| `streamlit-ace` | In-browser code editor |
| `bandit` | Python static security linter (must also be on `PATH`) |
| `psycopg2-binary` | PostgreSQL driver |
| `python-dotenv` | `.env` configuration loading |
| `pyarrow` | Streamlit data display |

### Analysis (Python)

Not all listed in `requirements.txt`; install separately:

| Package | Purpose |
|---------|---------|
| `pandas` | Data loading, filtering, joining |
| `scipy` | Shapiro–Wilk, Levene, Mann–Whitney U, Wilcoxon, paired t-test |
| `bandit` | Subprocess Bandit runs for security diffs |
| `semopy` | Optional Python-side SEM |
| `openpyxl` / `xlsxwriter` | Excel output |
| `pingouin` | Effect size helpers |

### Analysis (R)

```r
install.packages(c(
  "tidyverse", "readr", "psych", "lavaan", "semPlot",
  "effectsize", "broom", "knitr", "stringr"
))
```

---

## 9. Known Issues and Caveats

1. **Hardcoded absolute paths.** `data_cleanup/find_complete_prolific_ids.py` and `SEM_Analysis/SEMFinal.R` both embed absolute filesystem paths. Update `BASE_DIR` and `base_path` respectively before running on any machine other than the original development machine.

2. **`outputs/` directory.** Steps 4–8 read `outputs/prolific_ids_with_counts.txt`, which is written by step 2. Create the `outputs/` directory under `Analysis/` before running step 2 if it does not already exist.

3. **Bandit filename mismatch.** `bandit_comparison_without_tool/bandit_comparison_nudge.py` writes `bandit_comparison_nudge_task_total_diffs.csv`, but `Aggregation/aggregate_nudge_metrics.py` reads the legacy name `bandit_comparison_nudge_nudge_task_total_diffs.csv`. Rename the file before running step 9.

4. **Column suffix brittleness.** Python's deduplication emits `__2`/`__3` suffixes on repeated survey columns; R's `make.unique()` emits `__dup_1`/`__dup_2`. When both stack, column names can look like `]__2__dup_1`. Re-check column name suffixes after any upstream survey re-export.

5. **Non-breaking spaces in survey headers.** LimeSurvey column names contain Unicode non-breaking spaces (`\u00a0`) and trailing whitespace. All R scripts normalize these with `stringr::str_replace_all`. Re-check if the survey platform or export format changes.

6. **Bootstrap non-determinism.** No `set.seed()` is called before `lavaan::sem()`. Bootstrap confidence intervals will differ slightly between runs.

7. **`SEMFinal.R` output directory mismatch.** The script writes to `sem_outputs_codechanges/` but the canonical archived results are in `sem_outputs_codechanges_nudges/`. After a fresh run, manually copy the outputs to the `_nudges/` folder to preserve the canonical layout.

8. **CWE map is hardcoded.** The Bandit-ID → CWE lookup in `SEMFinal.R` covers only the seven expected findings for the three study tasks. Any unexpected Bandit finding will appear with `NA` for CWE and severity.

9. **Pre-Risk vs. Post-Risk scale mismatch.** PRE Risk uses a 6-pt agreement scale; POST Risk uses a 5-pt frequency scale. Both are min-max normalized to [0, 1] before compositing. Deltas and correlations for Risk Tolerance are therefore bounded to [−1, 1], not raw scale intervals.

10. **`admin.py` is outdated.** The admin dashboard reads from a legacy SQLite database (`interactions.db`). The current application uses PostgreSQL and `admin.py` is no longer functional without significant changes.

11. **Analysis Python dependencies.** Not all analysis packages are listed in the root `requirements.txt`, which covers only the application. Install analysis packages separately (see §8).
