# Security-Nudge / GenAI Coding-Tool Study — Analysis Repository

This repository contains the full quantitative analysis pipeline for a between-subjects experiment investigating whether **security-emphasizing nudges** change how software developers interact with a GenAI coding tool, and whether that behavioral change translates into improved security outcomes and shifted psychological attitudes.

---

## Table of Contents

1. [Study Design](#1-study-design)
2. [Repository Structure](#2-repository-structure)
3. [Data Sources](#3-data-sources)
4. [Analysis Pipeline Overview](#4-analysis-pipeline-overview)
5. [Python Pipeline — Methods and Scripts](#5-python-pipeline--methods-and-scripts)
6. [R SEM Analysis — Methods and Scripts](#6-r-sem-analysis--methods-and-scripts)
7. [Psychological Constructs Analysis](#7-psychological-constructs-analysis)
8. [RQ1 Statistical Analysis](#8-rq1-statistical-analysis)
9. [Key Results at a Glance](#9-key-results-at-a-glance)
10. [Reproducing the Analysis](#10-reproducing-the-analysis)
11. [Dependencies](#11-dependencies)
12. [Known Issues and Caveats](#12-known-issues-and-caveats)
13. [Further Documentation](#13-further-documentation)

---

## 1. Study Design

**Design type.** Between-subjects experiment, two nudge conditions:

| Condition | Label | Description |
|-----------|-------|-------------|
| **Nudge A** | Control | Generic / non-security feedback from the tool. `NudgeType = 0`. |
| **Nudge B** | Security-emphasizing | Warnings explicitly highlighting security risks in the generated code. `NudgeType = 1`. |

**Tasks.** Each participant completed three Python coding tasks within a custom tool interface. After each task the code was scanned by [Bandit](https://github.com/PyCQA/bandit) (a Python security linter), and per-task booleans recorded whether the participant *used the tool* and whether the *code subsequently changed*.

**Survey.** A LimeSurvey questionnaire collected pre-treatment and post-treatment Likert responses for four psychological constructs — **Risk Tolerance**, **Self-Efficacy**, **Trust**, and **Behavioral Intention** toward GenAI coding tools — plus a one-time trait **Motivation** scale.

**Sample (after filtering).** N = **97** participants (48 Nudge A, 49 Nudge B). Inclusion criteria: non-missing `Nudge` assignment, non-missing tool-use count, post-debriefing consent = `"YES"` where present.

**Recruitment platform.** Prolific.

---

## 2. Repository Structure

```
Analysis/
│
├── README.md                          ← this file
│
├── Tool_CSV/                          ← raw telemetry exports (source of truth)
│   ├── participants.csv               ← participant ↔ nudge-group mapping
│   ├── code_snapshots.csv             ← per-event code snapshots with timestamps
│   ├── tool_usage.csv                 ← tool use / skip decisions per task
│   ├── event_types.csv, tasks.csv, nudge_descriptions.csv, group_slots.csv
│   └── results-survey641369.csv       ← LimeSurvey export mirror
│
├── Tool_JSON/                         ← JSON mirrors of all Tool_CSV tables
│
├── LLMCode/                           ← LLM-generated baseline code for tasks 1–3
│   └── task1.json, task2.json, task3.json
│
├── data_cleanup/                      ← Step 1–2: participant inclusion list
│   ├── filter_limesurvey.py
│   ├── find_complete_prolific_ids.py
│   ├── filter_limesurvey_ids.csv
│   └── prolific_ids_with_counts.csv
│
├── tool_usage/                        ← Step 3: per-participant tool-use summary
│   ├── generate_tool_usage_summary.py
│   └── tool_usage_*.csv / .txt
│
├── code_changes_with_tool/            ← Step 4: code change detection (with-tool arm)
│   ├── code_changes_after_tool.py
│   └── code_changes_after_tool_*.csv / .txt
│
├── code_changes_without_tool/         ← Step 5: code change detection (without-tool arm)
│   ├── code_changes_after_nudge.py
│   └── code_changes_after_nudge_*.csv / .txt / plots/
│
├── bandit_comparison_with_tool/       ← Step 6: Bandit security scan diffs (with-tool)
│   ├── bandit_comparison.py
│   └── bandit_comparison_*.csv / .txt
│
├── bandit_comparison_without_tool/    ← Step 7: Bandit security scan diffs (without-tool)
│   ├── bandit_comparison_nudge.py
│   └── bandit_comparison_nudge_*.csv / .txt
│
├── nudge_to_completion_duration/      ← Step 8: timing from nudge to task completion
│   ├── nudge_to_completion_durations.py
│   └── *.csv / .txt / .xlsx
│
├── Aggregation/                       ← Steps 9–10: merged summary tables
│   ├── aggregate_nudge_metrics.py
│   ├── generate_participant_profiles_schema.py
│   ├── nudge_aggregated_summary.csv
│   ├── participant_profiles_schema.csv  ← PRIMARY ANALYSIS INPUT (one row per participant)
│   └── results-survey641369.csv
│
├── SEM_Analysis/                      ← R structural equation modeling
│   ├── SEMFinal.R                     ← CANONICAL script
│   ├── SEM_CodeChanges.R              ← intermediate variant
│   ├── sem_analysis.r                 ← original / historical script
│   ├── participant_profiles_schema.csv ← local copy of aggregation output
│   ├── SEM_Analysis.Rproj
│   ├── sem_outputs/                   ← sem_analysis.r outputs
│   ├── sem_outputs_codechanges/       ← SEM_CodeChanges.R outputs
│   └── sem_outputs_codechanges_nudges/ ← SEMFinal.R outputs (CANONICAL)
│
├── psychological_constructs_analysis/
│   ├── psychological_constructs_analysis.py
│   └── *.csv / .txt
│
├── rq1_statistical_analysis/
│   ├── rq1_statistical_analysis.py
│   └── *.csv / .txt / .xlsx
│
└── docs/
    ├── CSV_BUILD_METHODS.md           ← step-by-step pipeline lineage
    ├── TABLE_DOCUMENTATION.md         ← column-level schema reference
    ├── SEM_ANALYSIS.md                ← SEM methods and script documentation
    └── SEM_RESULTS.md                 ← SEM results interpretation
```

The **event semantics** used throughout the pipeline:

| Event ID | Name | Meaning |
|----------|------|---------|
| 1 | `SUB_NO_NUDGE` | Participant submits code *before* nudge is shown |
| 2 | `RUN_TOOL` | Participant chooses to run the GenAI security tool |
| 3 | `SUB_NO_TOOL` | Participant submits code *after* nudge but *without* tool |
| 4 | `SUB_TOOL` | Participant submits code *after* using the tool |

---

## 3. Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Tool telemetry (CSV) | `Tool_CSV/` | Per-event code snapshots, tool-use decisions, participant ↔ group mapping, task metadata |
| Tool telemetry (JSON) | `Tool_JSON/` | JSON mirrors of the above |
| Survey responses | `Aggregation/results-survey641369.csv` | LimeSurvey export; pre/post Likert items for five constructs |
| LLM baselines | `LLMCode/task*.json` | AI-generated starter code used as Bandit comparison baseline for each task |
| Derived wide table | `Aggregation/participant_profiles_schema.csv` | One row per participant; all behavioral, security, and survey columns joined (primary SEM input) |

---

## 4. Analysis Pipeline Overview

The pipeline has three logical stages:

```
Stage 1 — Python Data Preparation (steps 1–10)
  Raw telemetry + survey → participant_profiles_schema.csv

Stage 2 — R Structural Equation Modeling
  participant_profiles_schema.csv → path models, per/between-group tests, Bandit/CWE tables

Stage 3 — Python Supplementary Analyses
  participant_profiles_schema.csv → RQ1 group comparisons, construct reliability/paired tests
```

**Recommended run order (scripts must be run in this sequence):**

1. `data_cleanup/filter_limesurvey.py`
2. `data_cleanup/find_complete_prolific_ids.py`
3. `tool_usage/generate_tool_usage_summary.py`
4. `code_changes_with_tool/code_changes_after_tool.py`
5. `code_changes_without_tool/code_changes_after_nudge.py`
6. `bandit_comparison_with_tool/bandit_comparison.py`
7. `bandit_comparison_without_tool/bandit_comparison_nudge.py`
8. `nudge_to_completion_duration/nudge_to_completion_durations.py`
9. `Aggregation/aggregate_nudge_metrics.py`
10. `Aggregation/generate_participant_profiles_schema.py`
11. *(Optional)* `rq1_statistical_analysis/rq1_statistical_analysis.py`
12. *(Optional)* `psychological_constructs_analysis/psychological_constructs_analysis.py`
13. Open `SEM_Analysis/SEM_Analysis.Rproj` → source `SEMFinal.R`

> **Important:** Steps 4–8 require `outputs/prolific_ids_with_counts.txt` which is created by step 2. The `outputs/` directory at the project root must exist. `data_cleanup/find_complete_prolific_ids.py` contains a hardcoded `BASE_DIR` path that must be updated if the repository is moved.

---

## 5. Python Pipeline — Methods and Scripts

### 5.1 `data_cleanup/filter_limesurvey.py`
Filters the raw LimeSurvey export (`Tool_CSV/results-survey641369.csv`) to rows where the confirmation code equals `761528`. Extracts Prolific IDs into `outputs/filter_limesurvey_ids.csv`.

**Method:** pandas row filtering.

---

### 5.2 `data_cleanup/find_complete_prolific_ids.py`
Builds the participant inclusion list by requiring presence in both `code_snapshots.csv` and `tool_usage.csv`.

**Method:** set intersection across three telemetry tables; detects duplicate Prolific IDs.

**Key output:** `outputs/prolific_ids_with_counts.csv` — the participant filter backbone used by all downstream scripts.

---

### 5.3 `tool_usage/generate_tool_usage_summary.py`
Summarizes per-participant tool use/skip decisions. For each `(participant_id, task_id)`, keeps the latest decision by timestamp. Maps `group_id` 1–6 → Nudge A, 7–12 → Nudge B.

**Method:** aggregation and de-duplication; computes per-nudge tool-use rates.

---

### 5.4 `code_changes_with_tool/code_changes_after_tool.py`
Detects code changes between event 2 (tool run start) and event 4 (tool submission) for each participant-task pair.

**Method:** string comparison of snapshot code; computes `changed` boolean and line-delta metrics.

---

### 5.5 `code_changes_without_tool/code_changes_after_nudge.py`
Same logic as 5.4, but for the nudge-only arm: event 1 (pre-nudge) → event 3 (post-nudge, no-tool submission).

---

### 5.6 `bandit_comparison_with_tool/bandit_comparison.py`
Runs [Bandit](https://github.com/PyCQA/bandit) (`bandit -f json`) on (a) LLM-generated baseline code and (b) participant code at event 4, for any task where the code changed. Computes issue totals, severity diffs (high / medium / low), and change-type classifications (new / fixed / common) per participant-task pair.

**Method:** subprocess execution of Bandit; JSON parsing; diff-based security-issue accounting.

---

### 5.7 `bandit_comparison_without_tool/bandit_comparison_nudge.py`
Same flow as 5.6 using event 3 (nudge-only) submissions.

---

### 5.8 `nudge_to_completion_duration/nudge_to_completion_durations.py`
Computes elapsed time from first nudge display (event 1) to task completion (event 3 or 4) for each participant-task pair.

**Method:** timestamp arithmetic; produces duration in seconds and `hh:mm:ss`; averages by task × nudge.

---

### 5.9 `Aggregation/aggregate_nudge_metrics.py`
Merges upstream per-nudge-per-task CSV metrics into a single wide summary with two rows (Nudge A / B).

---

### 5.10 `Aggregation/generate_participant_profiles_schema.py`
Builds the primary analytical input — one row per participant — by joining all upstream derived tables with the full survey export. For each task, selects the with-tool or without-tool metrics based on whether the participant used the tool. Resolves duplicate survey headers via unique renaming. Keeps the best-matching survey row when a Prolific ID appears multiple times (row with most non-empty fields).

**Key output:** `Aggregation/participant_profiles_schema.csv`

---

### 5.11 `rq1_statistical_analysis/rq1_statistical_analysis.py`
Tests the primary between-group hypotheses (Nudge A vs. B) on tool use, vulnerability metrics, and code changes.

**Statistical methods:**
- **Shapiro–Wilk** test for normality per group
- **Levene's test** for homogeneity of variance
- If both groups are normal → **Welch's t-test**; otherwise → **Mann–Whitney U**
- Effect sizes: **Hedges' g** (parametric) or **rank-biserial r** (non-parametric)
- Multiple-comparison correction: **Bonferroni** (α/3 for three primary comparisons)

**Outputs:** `rq1_statistical_analysis.txt`, `rq1_statistical_analysis_summary.csv`, `rq1_stats.xlsx`

---

### 5.12 `psychological_constructs_analysis/psychological_constructs_analysis.py`
Scores Likert composites, assesses reliability, and tests pre→post change within each construct.

**Statistical methods:**
- Manual **Cronbach's α**
- **Shapiro–Wilk** normality test on paired differences
- **Paired t-test** (`scipy.stats.ttest_rel`) where assumptions hold
- **Wilcoxon signed-rank test** (`scipy.stats.wilcoxon`) as non-parametric alternative
- Optional path-regression SEM via **semopy**

**Outputs:** `construct_composites.csv`, `paired_ttest_results.csv`, `sem_results.csv`, `construct_analysis_report.txt`

---

## 6. R SEM Analysis — Methods and Scripts

All three R scripts share the same package set:

```r
tidyverse, readr, psych, lavaan, semPlot, effectsize, broom, knitr, stringr
```

They all read `SEM_Analysis/participant_profiles_schema.csv` and independently re-derive all composites and constructs.

---

### 6.1 Conceptual Model

The study tests a mediated causal chain:

```
NudgeType (A=0 / B=1)
      │
  H1  ▼
Tool Engagement  ─── H2a ──▶  PostRiskTolerance  ─┐
(CodeChangesWithTool           H2b ──▶  PostSelfEfficacy  │  H4a/b/c
 or FollowCount)   ─── H2c ──▶  PostTrust         ─┼──────▶ PostBehavioralIntention
      │                                              │         ▲
  H3a └──────────────────────────────────────────▶  │    H5   │
  H3b ──────────────────────────────────────────▶  │◄── Motivation
```

**Hypotheses tested:**

| Path label | Path | Meaning |
|------------|------|---------|
| H1 | `ToolEngagement ~ NudgeType` | Nudge B increases tool engagement |
| H2a–c | `Post{Risk,SE,Trust} ~ ToolEngagement` | Engagement shifts post-treatment attitudes |
| H3a–b | `Post{Risk,Trust} ~ NudgeType` | Direct nudge effect on Risk Tolerance and Trust |
| H4a–c | `PostBI ~ PostRisk + PostSE + PostTrust` | Post attitudes predict Behavioral Intention |
| H5 | `PostBI ~ Motivation` | Trait motivation predicts BI |
| c1–c4 | `PostX ~ PreX` | Autoregressive baseline controls |

**Indirect (mediated) effects defined in lavaan:**
```
ind_risk  := h1 * h2a * h4a
ind_se    := h1 * h2b * h4b
ind_trust := h1 * h2c * h4c
ind_total := ind_risk + ind_se + ind_trust
```

---

### 6.2 Latent Construct Measurement

All constructs are measured pre- and post-treatment. Risk Tolerance uses different scales across waves and is normalized to 0–1 before compositing.

| Construct | Items | Pre scale | Post scale | Reverse-scored |
|-----------|-------|-----------|------------|----------------|
| Motivation (trait) | 3 | 6-pt agreement | — | none |
| Risk Tolerance | 3 | 6-pt agreement | 5-pt frequency | Items 1 and 2 |
| Self-Efficacy | 4 | 6-pt agreement | 6-pt agreement | Item 2 |
| Trust | 4 | 6-pt agreement | 6-pt agreement | none |
| Behavioral Intention | 3 | 6-pt agreement | 6-pt agreement | none |

**Scale coding:**
- 6-pt agreement: `COMPLETELY DISAGREE=1 … COMPLETELY AGREE=6`
- 5-pt frequency: `NEVER=1 … ALWAYS=5`

---

### 6.3 Script Evolution

| Script | Tool-engagement mediator | Additional features |
|--------|--------------------------|---------------------|
| `sem_analysis.r` | `FollowCount` (tasks tool used, 0–3) | Original model |
| `SEM_CodeChanges.R` | `CodeChangesWithTool` (tool used AND code changed, 0–3) | + Wilcoxon tests; Bandit severity sums |
| **`SEMFinal.R`** *(canonical)* | `CodeChangesWithTool` | + CWE/Bandit issue parsing; per-group paired tests; between-group tests; safer correlation helpers |

---

### 6.4 SEM Estimation Settings

All models are estimated identically:

```r
sem(model, data = df,
    missing   = "fiml",      # Full-Information Maximum Likelihood for missing data
    se        = "bootstrap",
    bootstrap = 5000,        # Bootstrap replications
    fixed.x   = FALSE)
```

Three model variants are estimated per script:

1. **Main model** — post-treatment scores as outcomes.
2. **Change-score model** — `Δ = post − pre` as outcomes (robustness check).
3. **Main + direct effect** — adds direct `NudgeType → PostBI` path to decompose total vs. mediated effects.

Output includes standardized solutions (`std.all`), bootstrap-percentile confidence intervals, fit measures, and R².

---

### 6.5 Reliability (Cronbach's α)

`safe_alpha()` filters out all-NA and zero-variance items before calling `psych::alpha()`. Reported for all nine composites (Motivation, Pre/Post Risk, Pre/Post SE, Pre/Post Trust, Pre/Post BI).

---

### 6.6 Paired Tests (Pre vs. Post)

| Script | Test | Effect size |
|--------|------|-------------|
| `sem_analysis.r` | Paired t-test (whole sample) | Cohen's d paired |
| `SEM_CodeChanges.R` | Paired t-test + Wilcoxon signed-rank (whole sample) | Cohen's d paired |
| `SEMFinal.R` | Paired t-test + Wilcoxon signed-rank, **per nudge group (A and B separately)** | Cohen's d paired |

---

### 6.7 Between-Group Tests (`SEMFinal.R` only)

`run_between_tests()` applies the following for each outcome variable:
- **Welch's two-sample t-test**
- **Mann–Whitney U / Wilcoxon rank-sum test**
- **Cohen's d** (independent samples)

Variables tested: `FollowCount`, `CodeChangesWithTool`, `TotalNewVulns`, `Motivation`, high/medium/low severity diffs, fixed/new issue counts.

---

### 6.8 CWE / Bandit Issue Analysis (`SEMFinal.R` only)

Parses the comma-joined `Task X issue type ID` and `Task X issue change kind` columns into a long-format ledger. Joins to a hardcoded Bandit-ID → CWE / severity / task lookup:

| Bandit ID | Name | CWE | Severity | Task |
|-----------|------|-----|----------|------|
| B701 | `jinja2_autoescape_false` | CWE-80 (XSS) | HIGH | 1 |
| B311 | `blacklist (random)` | CWE-330 (Insufficient Randomness) | LOW | 2 |
| B404 | `blacklist (subprocess import)` | CWE-78 (OS Command Injection — import) | LOW | 3 |
| B602 | `subprocess_popen_with_shell_equals_true` | CWE-78 (OS Command Injection) | HIGH | 3 |
| B603 | `subprocess_without_shell_equals_true` | CWE-78 (OS Command Injection — no shell) | LOW | 3 |
| B607 | `start_process_with_partial_path` | CWE-426 (Untrusted Search Path) | LOW | 3 |
| B105 | `hardcoded_password_string` | CWE-259 (Hard-coded Password) | LOW | 3 |

Produces: Bandit-ID frequency tables (overall and by nudge), change-kind breakdowns, per-participant issue counts (`n_issues_fixed`, `n_issues_common`, `n_issues_new`), and Pearson correlations with `CodeChangesWithTool`.

---

### 6.9 Output Directories

| Directory | Written by | Contents |
|-----------|------------|---------|
| `sem_outputs/` | `sem_analysis.r` | Cleaned data, parameter estimates (main + delta), paired t-test summary, group descriptives, path diagram PNG |
| `sem_outputs_codechanges/` | `SEM_CodeChanges.R` | Same as above + Wilcoxon summary, Bandit-by-nudge, severity correlations |
| `sem_outputs_codechanges_nudges/` | `SEMFinal.R` *(canonical)* | All of the above + CWE tables, per-group paired tests, between-group tests |

---

## 7. Psychological Constructs Analysis

**Script:** `psychological_constructs_analysis/psychological_constructs_analysis.py`

Independently scores the five psychological composites from the survey, assesses internal consistency (Cronbach's α), and tests pre→post shifts within the full sample using paired tests. Optionally runs a path-regression SEM with **semopy** to model construct relationships.

**Outputs:** `construct_composites.csv`, `paired_ttest_results.csv`, `sem_results.csv`, `construct_analysis_report.txt`

---

## 8. RQ1 Statistical Analysis

**Script:** `rq1_statistical_analysis/rq1_statistical_analysis.py`

Tests the primary between-group hypotheses (Nudge A vs. Nudge B) across three domains:

1. **Tool Usage** — total uses per participant; per-task binary tool use.
2. **Vulnerability Metrics** — Bandit issue severity diffs; new/fixed/common issue counts.
3. **Code Changes** — proportion of tasks where code changed.

**Statistical protocol per comparison:**

```
1. Shapiro–Wilk normality test (per group)
2. Levene's test for equal variances
3. Decision: Welch's t-test (if normal) OR Mann–Whitney U (if not)
4. Effect size: Hedges' g (parametric) OR rank-biserial r (non-parametric)
5. Bonferroni correction: α_adjusted = 0.05 / 3 = 0.0167
```

**Outputs:** `rq1_statistical_analysis.txt`, `rq1_statistical_analysis_summary.csv`, `rq1_stats.xlsx`

---

## 9. Key Results at a Glance

Full interpretation is in `docs/SEM_RESULTS.md`. Summary of main findings (N = 97, SEMFinal.R):

### Between-group effects (Nudge A vs. B)

| Metric | Nudge A | Nudge B | Effect | p |
|--------|---------|---------|--------|---|
| CodeChangesWithTool (M) | 0.65 | **1.06** | d = −0.44 | .034 |
| AnyCodeChangeWithTool rate | 41.7% | **63.3%** | — | — |
| HighSeverityDiff (M) | −0.15 | **−0.35** | d = +0.45 | .029 |
| ToolUseCount (M) | 2.54 | 2.82 | d = −0.36 | .081 (n.s.) |

### Supported SEM hypotheses (canonical `SEMFinal.R` main model)

| Hypothesis | Path | Standardized β | p | Verdict |
|------------|------|---------------|---|---------|
| H1 | NudgeType → CodeChangesWithTool | +0.22 | .029 | **Supported** |
| H3a | NudgeType → PostRiskTolerance | −0.18 | .041 | **Supported** |
| H3b | NudgeType → PostTrust | +0.12 | .022 | **Supported** |
| H4a | PostRiskTolerance → PostBI | +0.17 | .015 | **Supported** |
| H4b | PostSelfEfficacy → PostBI | +0.13 | .014 | **Supported** |
| H4c | PostTrust → PostBI | +0.16 | .014 | **Supported** |
| H2a–c | CodeChangesWithTool → Post attitudes | ~0.06–0.15 | >.05 | **Not supported** |
| H5 | Motivation → PostBI | −0.06 | .300 | **Not supported** |
| Indirect effects | Full mediated chain | — | >.05 | **Not significant** |

### Within-group pre→post shifts (paired tests, by nudge)

| Group | Construct | Cohen's d | p |
|-------|-----------|-----------|---|
| A | Behavioral Intention | −0.31 | .038 |
| B | Trust | +0.36 | .016 |
| B | Risk Tolerance | −0.27 | .063 (marginal) |

---

## 10. Reproducing the Analysis

### Python pipeline

```bash
# Prerequisites
pip install pandas scipy semopy bandit

# Run in order (from repo root)
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
```

> **Before running:** edit the `BASE_DIR` constant in `data_cleanup/find_complete_prolific_ids.py` if the repository has moved from its original location.

### R SEM (canonical)

```r
# In RStudio: open SEM_Analysis/SEM_Analysis.Rproj, then:
source("SEMFinal.R")
```

> The script uses an absolute `base_path` pointing to `~/Desktop/work/Fard Lab/Analysis/SEM_Analysis`. Edit this constant at the top of `SEMFinal.R` before running on a different machine.

> Bootstrap CIs depend on the RNG state. To reproduce identical results, add `set.seed(<value>)` before the `sem(...)` calls.

### Supplementary analyses

```bash
python rq1_statistical_analysis/rq1_statistical_analysis.py
python psychological_constructs_analysis/psychological_constructs_analysis.py
```

---

## 11. Dependencies

### Python

| Package | Use |
|---------|-----|
| `pandas` | Data loading, filtering, joining |
| `scipy` | Shapiro–Wilk, Levene, Mann–Whitney U, Wilcoxon, paired t-test |
| `bandit` | Static security analysis of Python code (must be on `PATH`) |
| `semopy` | Optional Python-side SEM in construct analysis |
| `openpyxl` / `xlsxwriter` | Excel output |

### R

```r
install.packages(c(
  "tidyverse", "readr", "psych", "lavaan", "semPlot",
  "effectsize", "broom", "knitr", "stringr"
))
```

---

## 12. Known Issues and Caveats

1. **Hardcoded paths.** `data_cleanup/find_complete_prolific_ids.py` and `SEM_Analysis/SEMFinal.R` both contain absolute paths that must be updated when the repository is moved.

2. **`outputs/` directory.** Steps 4–8 expect `outputs/prolific_ids_with_counts.txt` which is created by step 2. If `outputs/` is missing, downstream scripts will fail.

3. **Column-name suffix brittleness.** Python's deduplication emits `__2`/`__3` suffixes; R's `make.unique()` emits `__dup_1`/`__dup_2`. When both stack, column names can look like `]__2__dup_1`. Re-check suffixes after any upstream survey re-export.

4. **Non-breaking spaces in survey headers.** Likert column names contain Unicode non-breaking spaces and trailing whitespace. All R scripts normalize these with `stringr::str_replace_all`.

5. **Bootstrap non-determinism.** No `set.seed()` is set before `lavaan::sem()` calls. Bootstrap CIs will differ slightly between runs.

6. **`output_dir` vs. canonical folder mismatch in `SEMFinal.R`.** The script writes to `sem_outputs_codechanges/` but the canonical result folder is `sem_outputs_codechanges_nudges/`. After a fresh run, manually copy outputs if you need the `_nudges/` folder to remain authoritative.

7. **CWE map is hardcoded.** The Bandit-ID → CWE lookup in `SEMFinal.R` covers only the seven expected findings for the three study tasks. Any new Bandit finding will appear with `NA` for CWE and severity.

8. **Pre-Risk vs. Post-Risk scale mismatch.** PRE Risk uses a 6-pt agreement scale; POST Risk uses a 5-pt frequency scale. Both are min-max normalized to [0, 1] before compositing, so delta and correlation values for Risk Tolerance are bounded to [−1, 1], not the raw scale intervals.

9. **Filename inconsistency in Bandit scripts.** `bandit_comparison_nudge.py` writes `bandit_comparison_nudge_task_total_diffs.csv` but `aggregate_nudge_metrics.py` reads the legacy filename `bandit_comparison_nudge_nudge_task_total_diffs.csv`. After re-running the Bandit script, rename the output file to match what the aggregator expects.

10. **`sem_analysis.r` output directory.** This script writes to the R working directory with no sub-folder; the artifacts in `sem_outputs/` were placed there manually after the run.

---

## 13. Further Documentation

| File | Contents |
|------|---------|
| `docs/CSV_BUILD_METHODS.md` | Step-by-step lineage for all 10 Python pipeline steps, with inputs, outputs, and logic for each script |
| `docs/TABLE_DOCUMENTATION.md` | Column-level schema for all derived tables and `participant_profiles_schema.csv` |
| `docs/SEM_ANALYSIS.md` | Full SEM methods documentation: construct measurement, scale coding, lavaan model syntax, per-script differences, reproducibility notes, and known issues |
| `docs/SEM_RESULTS.md` | Interpretation of all SEM results: descriptives by nudge group, hypothesis-by-hypothesis findings, change-score robustness, paired tests, between-group tests, CWE/Bandit analysis, and synthesis |
