# SEM_Analysis — Documentation

This document covers the structural-equation / path-analysis stage of the project, located in `SEM_Analysis/`. The SEM stage starts from the wide participant-profile table produced upstream (`Aggregation/participant_profiles_schema.csv`, also kept as a local copy `SEM_Analysis/participant_profiles_schema.csv`) and tests a behavioral model linking the experimental nudge condition to changes in **Risk Tolerance**, **Self-Efficacy**, **Trust**, and **Behavioral Intention** toward GenAI coding tools, with optional security-outcome (Bandit/CWE) summaries.

---

## 1. Folder Layout

```
SEM_Analysis/
├── sem_analysis.r                         # Original model (FollowCount as mediator)
├── SEM_CodeChanges.R                      # Variant: replaces FollowCount with CodeChangesWithTool, adds Wilcoxon
├── SEMFinal.R                             # Current canonical script (CWE/Bandit analysis, per-group paired tests, between-group tests)
├── participant_profiles_schema.csv        # Local copy of the wide input table (148 KB)
├── SEM_Analysis.Rproj                     # RStudio project file
├── .RData / .Rhistory / .Rproj.user/      # RStudio session/state (not analysis artifacts)
├── sem_outputs/                           # Output dir written by sem_analysis.r
├── sem_outputs_codechanges/               # Output dir written by SEM_CodeChanges.R
└── sem_outputs_codechanges_nudges/        # Output dir written by SEMFinal.R
```

There are three scripts because the model evolved across iterations. **`SEMFinal.R` is the current canonical analysis** and supersedes the others. The earlier two are kept for reproducibility / historical comparison.

---

## 2. Input Data

All three scripts read **one** input file:

- `participant_profiles_schema.csv`
  - This is the same schema produced by `Aggregation/generate_participant_profiles_schema.py` (see `docs/TABLE_DOCUMENTATION.md` for column-level documentation).
  - One row per participant. Modeled columns (`Prolific ID`, `Nudge`, `Number of tasks tool used`, `Task X tool use BOOL`, `Task X changed BOOL`, severity counts/diffs, `Task X issue type ID`, `Task X issue change kind [fixed, common, new]`, etc.) are followed by all raw survey columns appended verbatim.
  - The local `SEM_Analysis/participant_profiles_schema.csv` is a copy from `Aggregation/`. Re-export it whenever upstream data changes.

### Column-name cleaning

Survey headers contain non-breaking spaces, runs of whitespace, and duplicate items (because pre/post versions of identical Likert items are emitted twice). Every script applies the same normalization:

```r
clean_names <- names(df_raw) |>
  stringr::str_replace_all("\u00a0", " ") |>
  stringr::str_replace_all("\\s+", " ") |>
  stringr::str_trim()

names(df_raw) <- make.unique(clean_names, sep = "__dup_")
```

After this step, duplicated post-treatment Likert items appear with a `__dup_1` (in `SEMFinal.R`) or `__2` (in `sem_analysis.r` / `SEM_CodeChanges.R`) suffix. The scripts assume **survey export order is "pre items first, then post items"**.

> **Suffix gotcha:** `Aggregation/generate_participant_profiles_schema.py` emits duplicate-rename suffix `__2`. R's `make.unique(..., sep = "__dup_")` produces `__dup_1`. Therefore the participant-profiles CSV already contains some columns named `...]__2` (from Python), and `make.unique()` will then add `__dup_1` to any *further* duplicates it finds. `sem_analysis.r` and `SEM_CodeChanges.R` reference Trust/SE/BI post columns directly by `__2` suffix; `SEMFinal.R` references some Risk post columns by `__dup_1`. This is brittle — re-check suffixes any time the upstream script changes.

### Participant filtering

All three scripts apply the same inclusion filter, in this order:

1. `Nudge` is non-missing.
2. `Number of tasks tool used` is non-missing.
3. (If present in the survey columns) the post-debriefing consent question equals `"YES"` (or is missing). The full debriefing question text is hardcoded as the column key.

---

## 3. Conceptual Model

The studies test the following hypothesized causal chain:

```
                       NudgeType (A=0, B=1)
                              │
                              ▼  H1
       ┌────────  Tool Engagement (FollowCount or CodeChangesWithTool)  ────────┐
       │                                                                       │
   H2a │                            H2b │                               H2c    │
       ▼                                ▼                                       ▼
  PostRiskTolerance          PostSelfEfficacy                            PostTrust
       │  H3a (direct from NudgeType)                                    │  H3b (direct from NudgeType)
       │                                                                  │
       └──────────────────────────────  H4a/b/c  ─────────────────────────┘
                                          │
                                  + Motivation (H5)
                                  + PreBehavioralIntention (control c4)
                                          │
                                          ▼
                                PostBehavioralIntention
```

### Hypotheses

| Path | Specification | Meaning |
|------|---------------|---------|
| **H1** | `TE ~ NudgeType` | Nudge B (security-emphasizing) shifts how often participants engage with the tool. |
| **H2a/b/c** | `Post{Risk,SE,Trust} ~ TE` | Tool engagement shifts post-treatment levels of Risk Tolerance, Self-Efficacy, and Trust. |
| **H3a/b** | `Post{Risk,Trust} ~ NudgeType` | Direct effect of nudge type on Post Risk Tolerance and Post Trust (controlling for TE). |
| **H4a/b/c** | `PostBI ~ PostRisk + PostSE + PostTrust` | Post-treatment cognitive-affective constructs predict post Behavioral Intention. |
| **H5** | `PostBI ~ Motivation` | Trait motivation predicts post Behavioral Intention. |
| (controls) | `c1..c4` | Each `Post*` is regressed on its own `Pre*` baseline. |

### Indirect effects (defined parameters in `lavaan`)

```
ind_risk  := h1 * h2a * h4a
ind_se    := h1 * h2b * h4b
ind_trust := h1 * h2c * h4c
ind_total := ind_risk + ind_se + ind_trust
```

The optional "main + direct" model adds `direct * NudgeType -> PostBI` and a `total_effect := direct + ind_total`.

### What changes across scripts

| Script | Tool-engagement variable (H1 mediator) | Notes |
|--------|----------------------------------------|-------|
| `sem_analysis.r` | `FollowCount` (= `Number of tasks tool used`, integer 0–3) | Original model |
| `SEM_CodeChanges.R` | `CodeChangesWithTool` (count of tasks where tool **was used** AND code **changed**, 0–3) | Adds Wilcoxon signed-rank tests; Bandit severity-diff sums |
| `SEMFinal.R` | `CodeChangesWithTool` | Adds CWE/Bandit issue parsing; per-group (A/B) paired tests; between-group (A vs B) tests; safer correlation/recoding helpers |

---

## 4. Latent Constructs and Measurement Items

All four primary constructs are measured PRE and POST (immediately before and after the coding-task block in the survey). All Likert items use the same agree-disagree scale **PRE**, but the Risk items switch to a frequency scale **POST**.

### Scale labels and numeric coding

| Function | Scale | 1 → 6 / 1 → 5 mapping |
|----------|-------|------------------------|
| `recode_agree6()` | 6-point agreement | `COMPLETELY DISAGREE=1, DISAGREE=2, SOMEHOW DISAGREE=3, SOMEHOW AGREE=4, AGREE=5, COMPLETELY AGREE=6` |
| `recode_freq5()` | 5-point frequency | `NEVER=1, RARELY=2, SOMETIMES=3, OFTEN=4, ALWAYS=5` |
| `recode_likelihood6()` | 6-point likelihood | `VERY UNLIKELY=1 ... VERY LIKELY=6` (defined in `sem_analysis.r`, not used in models) |
| `reverse6()` | Reverse 6-pt | `7 - x` |
| `reverse5()` | Reverse 5-pt | `6 - x` |
| `norm01(x, min, max)` | Min-max normalize | `(x - min) / (max - min)` to bring different-length scales onto a common 0–1 axis |

### Construct items

| Construct | # items | PRE scale | POST scale | Reverse-scored items | Composite |
|-----------|---------|-----------|------------|----------------------|-----------|
| **Motivation** (trait, baseline only) | 3 | agree-6 | — | none | `mot1, mot2, mot3` row mean |
| **Risk Tolerance** | 3 | agree-6 | freq-5 | `risk_*_1` and `risk_*_2` reversed (so high = more risk-tolerant) | Both pre and post normalized to 0–1 then row-mean |
| **Self-Efficacy** | 4 | agree-6 | agree-6 | `se_*_2` reversed | Row mean of 4 items (1–6 scale, no normalization) |
| **Trust** | 4 | agree-6 | agree-6 | none | Row mean of 4 items (1–6 scale) |
| **Behavioral Intention (BI)** | 3 | agree-6 | agree-6 | none | Row mean of 3 items (1–6 scale) |

### Item identification logic

- **Motivation items** are matched by literal column-name strings (e.g., `"...[I explore GenAI technology even if it's not critical to my job.]"`). `SEMFinal.R` adds a regex fallback if those literal lookups fail.
- **BI items** are detected by regex: column name contains `intend to use GenAI tools in the future|plan to continue using GenAI tools|always try to use GenAI tools in my work`. The script asserts exactly **6** matches (3 PRE + 3 POST) and assumes survey export order = pre, then post.
- **Risk items** are detected by regex on three statement fragments. The script then partitions the matches by detecting which scale each column actually contains: PRE candidates use `recode_agree6` (6-pt agreement), POST candidates use `recode_freq5` (5-pt frequency). `SEMFinal.R` instead uses **direct literal column names with `__dup_1` suffixes** for POST and verifies they exist (it does not auto-detect the scale).
- **Self-Efficacy** and **Trust** items use literal column-name strings throughout; POST versions are referenced via the `__2` suffix.

### Composite construction

```r
PreRiskTolerance        = rowMeans of normalized PRE risk items
PostRiskTolerance       = rowMeans of normalized POST risk items
PreSelfEfficacy         = rowMeans of recoded PRE SE items
PostSelfEfficacy        = rowMeans of recoded POST SE items
PreTrust                = rowMeans of recoded PRE trust items
PostTrust               = rowMeans of recoded POST trust items
PreBehavioralIntention  = rowMeans of recoded PRE BI items
PostBehavioralIntention = rowMeans of recoded POST BI items

dRiskTolerance        = PostRiskTolerance - PreRiskTolerance
dSelfEfficacy         = PostSelfEfficacy  - PreSelfEfficacy
dTrust                = PostTrust         - PreTrust
dBehavioralIntention  = PostBehavioralIntention - PreBehavioralIntention
```

Risk Tolerance is normalized because PRE uses 6-pt and POST uses 5-pt; without normalization, their delta would be uninterpretable. The other three constructs share one 6-pt scale across waves, so raw means are used.

---

## 5. Methods

The same methodological pipeline is run by each script. Differences between scripts are flagged inline.

### 5.1 Reliability (Cronbach's α)

`safe_alpha()` filters out items that are all-NA or have zero variance, then calls `psych::alpha()` on the remaining items. Reported as `round(...$total$raw_alpha, 3)` for:
- Motivation, PRE/POST Risk (normalized), PRE/POST Self-Efficacy, PRE/POST Trust, PRE/POST Behavioral Intention.

### 5.2 Descriptives

- Overall `summary()` on the construct columns and key observed variables.
- `group_desc`: per-`NudgeType` means/SDs of FollowCount (or `CodeChangesWithTool`), Motivation, the four delta scores, and (in `SEMFinal.R`) the three Bandit severity-diff sums.

### 5.3 Pre vs Post tests

Three different test setups, depending on script:

| Script | Test | Effect size |
|--------|------|-------------|
| `sem_analysis.r` | Paired-sample t-test (whole sample), per construct | `effectsize::cohens_d()` paired |
| `SEM_CodeChanges.R` | Paired t-test **and** Wilcoxon signed-rank (whole sample), per construct | Cohen's d paired |
| `SEMFinal.R` | Paired t-test **and** Wilcoxon signed-rank, **per Nudge group (A and B separately)**, per construct | Cohen's d paired |

`SEMFinal.R`'s `run_paired_tests()` helper drops cases with NA on either side and skips the construct if `n < 5`.

### 5.4 Between-group tests (`SEMFinal.R` only)

`run_between_tests()` runs:
- Welch's two-sample t-test (`t.test(var ~ NudgeType_f)`),
- Mann-Whitney U / Wilcoxon rank-sum (`wilcox.test(var ~ NudgeType_f)`),
- `effectsize::cohens_d(var ~ NudgeType_f)`.

Variables tested between A vs B:
- `FollowCount` (labeled `AvgToolUseCount`)
- `CodeChangesWithTool`
- `TotalNewVulns`
- `Motivation`
- `TotalHighSeverityDiff`, `TotalMedSeverityDiff`, `TotalLowSeverityDiff`
- `n_issues_fixed`, `n_issues_new`

### 5.5 Correlation matrix

Pearson correlations across NudgeType, the tool-engagement variable, Motivation, all PRE/POST/Δ construct scores, and (in CodeChanges variants) the three severity-diff totals. `use = "pairwise.complete.obs"`. `SEMFinal.R` first drops zero-variance columns to avoid `cor()` warnings.

### 5.6 Path models (`lavaan::sem`)

Three model specifications are estimated in each script:

1. **Main model** — uses `Post*` constructs as outcomes (model_main).
2. **Change-score model** — uses `dRisk`, `dSelfEfficacy`, `dTrust`, `dBehavioralIntention` as outcomes (model_delta). Robustness check.
3. **Main + direct effect** — adds a direct `NudgeType -> PostBehavioralIntention` path (model_main_plus_direct), so the total effect can be partitioned into direct vs mediated.

All three are fit with the same options:

```r
sem(model, data = df,
    missing  = "fiml",        # full-information ML for missing data
    se       = "bootstrap",
    bootstrap = 5000,         # 5000 bootstrap replications
    fixed.x  = FALSE)
```

Output: `summary(fit, standardized = TRUE, fit.measures = TRUE, ci = TRUE, rsquare = TRUE)`. Standardized solutions and `parameterEstimates()` with percentile bootstrap CIs are saved to CSV.

### 5.7 Path diagram

`semPaths(fit_main, what = "std", whatLabels = "std", layout = "tree", ...)` is plotted and saved as PNG (`sem_main_path_diagram.png` or `..._codechanges.png`) at 1800×1200 / 200 DPI.

### 5.8 CWE / Bandit issue analysis (`SEMFinal.R` only)

A new section parses Bandit findings from the wide profile and joins them to a hardcoded **Bandit-ID → CWE / severity / task** lookup table (Section 5b in the script):

| Bandit ID | Bandit name | CWE | Severity | Task |
|-----------|-------------|-----|----------|------|
| `B701` | `jinja2_autoescape_false` | CWE-80 (XSS via template injection) | HIGH | 1 |
| `B311` | `blacklist (random)` | CWE-330 (Insufficient Randomness) | LOW | 2 |
| `B404` | `blacklist (subprocess import)` | CWE-78 (OS Command Injection - import) | LOW | 3 |
| `B602` | `subprocess_popen_with_shell_equals_true` | CWE-78 (OS Command Injection) | HIGH | 3 |
| `B603` | `subprocess_without_shell_equals_true` | CWE-78 (OS Command Injection - no shell) | LOW | 3 |
| `B607` | `start_process_with_partial_path` | CWE-426 (Untrusted Search Path) | LOW | 3 |
| `B105` | `hardcoded_password_string` | CWE-259 (Use of Hard-coded Password) | LOW | 3 |

The `parse_bandit_issues()` helper converts the comma-joined `Task X issue type ID` and `Task X issue change kind [fixed, common, new]` strings into a long-format tibble with one row per (participant, task, bandit_id, change_kind), then joins to the CWE map and produces:

- Overall Bandit-ID frequencies.
- Bandit-ID frequencies pivoted by Nudge group.
- `change_kind` totals by Nudge group.
- Bandit-ID × `change_kind` cross-tabs (overall and by nudge).
- Per-participant counts: `n_issues_fixed`, `n_issues_common`, `n_issues_new` (= `TotalNewVulns`, parsed via `str_count(..., "new")` etc.).
- Correlations of `CodeChangesWithTool` with each issue-outcome metric.
- Per-Nudge descriptives of fixed/common/new counts.

### 5.9 Other helpers

| Helper | Purpose |
|--------|---------|
| `row_mean_safe(...)` | `rowMeans(cbind(...), na.rm = TRUE)` — survives any-NA rows |
| `is_freq5_col(x)` / `is_agree6_col(x)` | Detect scale type from observed response strings |
| `safe_logical_to_num(x)` (CodeChanges variants) | Coerce mixed `TRUE/"True"/1` → numeric 0/1 for the task-level BOOL columns |
| `safe_cor(x, y)` (`SEMFinal.R`) | Returns NA instead of warning when either variable has zero variance |

---

## 6. Script-by-Script Documentation

### 6.1 `sem_analysis.r` — Original model (FollowCount mediator)

**Working directory assumption:** the script reads `participant_profiles_schema.csv` from the **R working directory**. Set the working directory to `SEM_Analysis/` (e.g., open the `.Rproj`) before sourcing.

**Output directory:** writes outputs to the **current working directory** (no dedicated `output_dir` is created). The on-disk artifacts in `SEM_Analysis/sem_outputs/` were placed there manually after the run.

**Pipeline (numbered sections in code):**

1. Load packages.
2. Load and clean column names (no `__dup_` collisions expected).
3. Optional participant filtering (Nudge / FollowCount / debrief consent).
4. Core variables: `NudgeType`, `FollowCount`.
5. Recode baseline Motivation.
6. Auto-detect 6 BI columns (3 pre + 3 post).
7. Auto-detect 3+3 Risk columns by scale type.
8. Recode all PRE/POST construct items (with reverse scoring on SE item 2 and Risk items 1–2).
9. Build composites and deltas.
10. Descriptives + per-Nudge group descriptives.
11. Reliability (α) for all 9 composites.
12. Paired t-tests + Cohen's d for each construct (whole sample).
13. Correlation matrix.
14. **Main model** (mediator = `FollowCount`).
15. **Change-score model**.
16. **Main + direct effect** model.
17. `semPaths` rendering and PNG export.
18. Export cleaned data and result CSVs.

**Outputs (current working directory; copies in `sem_outputs/`):**
- `cleaned_sem_data.csv` — full participant frame plus all derived items, composites, deltas.
- `sem_main_parameter_estimates.csv` — `lavaan::parameterEstimates(fit_main, standardized = TRUE, ci = TRUE)` columns: `lhs, op, rhs, label, est, se, z, pvalue, ci.lower, ci.upper, std.lv, std.all`.
- `sem_delta_parameter_estimates.csv` — same columns, for `fit_delta`.
- `paired_t_tests_summary.csv` — `construct, t, df, p, mean_pre, mean_post`.
- `group_descriptives_by_nudge.csv` — `NudgeType, n, FollowCount_M, FollowCount_SD, Motivation_M, dRisk_M, dSE_M, dTrust_M, dBI_M`.
- `sem_main_path_diagram.png`.

---

### 6.2 `SEM_CodeChanges.R` — CodeChangesWithTool variant + Wilcoxon

**Working directory assumption:** reads `participant_profiles_schema.csv` from the working directory.

**Output directory:** writes everything to a freshly-created `sem_outputs_codechanges/` (created on demand via `dir.create()` if missing).

**Differences from `sem_analysis.r`:**

1. **Tool-engagement mediator changed.** Adds derived columns:
   - `task{1,2,3}_tool` = `safe_logical_to_num(\`Task X tool use BOOL\`)`
   - `task{1,2,3}_changed` = `safe_logical_to_num(\`Task X changed BOOL\`)`
   - `Task{1,2,3}_CodeChangesWithTool` = `1 iff (tool == 1 & changed == 1) else 0`
   - `CodeChangesWithTool` = `rowSums(...) ∈ {0,1,2,3}` — count of tasks where the tool was used **and** the code changed afterwards.
   - `AnyCodeChangeWithTool` = `1 if CodeChangesWithTool > 0 else 0`.
2. **Bandit severity-diff sums** (per participant, summed across the 3 tasks):
   - `TotalIssueDiff`, `TotalHighSeverityDiff`, `TotalMedSeverityDiff`, `TotalLowSeverityDiff`.
3. **Bandit-by-Nudge descriptives** (`bandit_by_nudge`) and a small **CodeChanges ↔ Bandit-severity correlation** table (`codechange_bandit_assoc`).
4. **Wilcoxon signed-rank test** added alongside the paired t-test for each construct (`wil_risk`, `wil_se`, `wil_trust`, `wil_bi`).
5. The path models replace `FollowCount` with `CodeChangesWithTool` everywhere (`h1`, `h2a/b/c`, mediation defs).
6. `corr_data` adds the three `Total*SeverityDiff` columns.

**Pipeline (numbered sections in code):**

1. Load packages (`tidyverse`, `readr`, `psych`, `lavaan`, `semPlot`, `effectsize`, `broom`, `knitr`, `stringr`).
2. Load data; clean column names via `make.unique(..., sep = "__dup_")`; create `sem_outputs_codechanges/` via `dir.create()` if missing.
3. Participant filtering (Nudge / `Number of tasks tool used` / debrief consent).
4. Core observed variables. Build `NudgeType` and `FollowCount`, then derive `task{1,2,3}_tool`, `task{1,2,3}_changed`, `Task{1,2,3}_CodeChangesWithTool`, `CodeChangesWithTool` (0–3), and `AnyCodeChangeWithTool` (0/1).
5. Bandit security-outcome row-sums across the 3 tasks: `TotalIssueDiff`, `TotalHighSeverityDiff`, `TotalMedSeverityDiff`, `TotalLowSeverityDiff`. Build `bandit_by_nudge` group summary and `codechange_bandit_assoc` (Pearson correlations between `CodeChangesWithTool` and each severity-diff total — no `safe_cor` protection in this script).
6. Recode baseline Motivation (`mot1/2/3` → `Motivation` row-mean) via literal column-name lookup.
7. Auto-detect 6 BI columns by regex; assert exactly 6 matches; assume survey order = 3 pre, then 3 post.
8. Auto-detect 3 + 3 Risk columns by scale type (PRE = `is_agree6_col`, POST = `is_freq5_col`); pick each by statement-fragment regex.
9. Recode all PRE/POST construct items. Risk items 1 and 2 reverse-scored (`reverse6` PRE, `reverse5` POST); SE item 2 reverse-scored.
10. Construct composite scores via `row_mean_safe`. Risk uses `norm01`-normalized items; the other three constructs use raw recoded items. Build `dRiskTolerance`, `dSelfEfficacy`, `dTrust`, `dBehavioralIntention` deltas.
11. Descriptives — `summary()` over the construct columns and per-`NudgeType` `group_desc` (CodeChangesWithTool / Motivation / 4 deltas / 3 severity-diff means).
12. Reliability — Cronbach's α for Motivation and the 8 PRE/POST construct scales via `safe_alpha`.
13. Paired t-tests + Wilcoxon signed-rank + Cohen's d (whole sample, per construct).
14. Correlation matrix over NudgeType, `CodeChangesWithTool`, Motivation, all Pre/Post/Δ construct scores, and the three severity-diff totals.
15. Main path model — `lavaan::sem(model_main, missing = "fiml", se = "bootstrap", bootstrap = 5000, fixed.x = FALSE)` with `CodeChangesWithTool` as the H1 mediator. Prints `summary(..., standardized = TRUE, fit.measures = TRUE, ci = TRUE, rsquare = TRUE)`, `standardizedSolution()`, and `parameterEstimates(..., boot.ci.type = "perc")`.
16. Change-score model (`fit_delta`) — delta outcomes, same `sem()` options.
17. Main + direct effect model (`fit_main_plus_direct`) — adds `direct * NudgeType -> PostBehavioralIntention` and defines `total_effect`.
18. `semPaths(fit_main, ...)` → `sem_main_path_diagram_codechanges.png` (1800×1200 @ 200 DPI) written into `output_dir`.
19. Build `tt_summary` and `wilcox_summary` tibbles, then export `cleaned_sem_data_codechanges.csv`, `sem_main_parameter_estimates_codechanges.csv`, `sem_delta_parameter_estimates_codechanges.csv`, `paired_t_tests_summary_codechanges.csv`, `wilcoxon_summary_codechanges.csv`, `group_descriptives_by_nudge_codechanges.csv`, `bandit_by_nudge_codechanges.csv`, `codechange_bandit_associations.csv` to `sem_outputs_codechanges/`.

**Outputs (in `sem_outputs_codechanges/`):**
- `cleaned_sem_data_codechanges.csv`
- `sem_main_parameter_estimates_codechanges.csv`
- `sem_delta_parameter_estimates_codechanges.csv`
- `paired_t_tests_summary_codechanges.csv` — `construct, t, df_stat, p, mean_pre, mean_post`
- `wilcoxon_summary_codechanges.csv` — `construct, V, p`
- `group_descriptives_by_nudge_codechanges.csv` — adds severity-diff columns
- `bandit_by_nudge_codechanges.csv` — `NudgeType, n, CodeChangesWithTool_M, CodeChangesWithTool_SD, AnyCodeChangeWithTool_Rate, HighSeverityDiff_M, MedSeverityDiff_M, LowSeverityDiff_M`
- `codechange_bandit_associations.csv` — `metric, cor_with_CodeChangesWithTool` (Pearson)
- `sem_main_path_diagram_codechanges.png`

---

### 6.3 `SEMFinal.R` — Canonical analysis (CWE / Bandit + per-group / between-group tests)

**Working directory assumption:** uses an **absolute** `base_path = "~/Desktop/work/Fard Lab/Analysis/SEM_Analysis"` to load the input. **Edit this constant before running on a different machine.**

**Output directory:** the script defines `output_dir = "sem_outputs_codechanges"` (created on demand). The actual on-disk artifacts in `SEM_Analysis/sem_outputs_codechanges_nudges/` were placed there manually; treat that folder as the **canonical results folder for this script**, even though the script itself writes into `sem_outputs_codechanges/`.

**Differences from `SEM_CodeChanges.R`:**

1. **`safe_cor(x, y)`** helper — returns `NA` if either input has zero variance, eliminating `cor()` warnings during the per-task / severity correlations.
2. **`TotalNewVulns`** — derived per-participant from the comma-joined `Task X issue change kind [fixed, common, new]` strings using `str_count(tolower(...), "new")` summed across tasks.
3. **CWE / Bandit issue analysis section (5b)** — full pipeline described in §5.8:
   - hardcoded `bandit_cwe_map` tribble (CWE / severity / task).
   - `parse_bandit_issues()` → long tibble of `(nudge, task, bandit_id, change_kind)`.
   - 6 frequency / cross-tab summaries (overall, by nudge, change_kind by nudge, etc.).
   - `n_issues_fixed`, `n_issues_common`, `n_issues_new` per participant.
   - `cwe_cor_table` of `CodeChangesWithTool` correlations with each metric.
4. **Per-group paired tests** (Section 13) — `run_paired_tests()` runs t-test + Wilcoxon + Cohen's d for each construct, **separately for Nudge A and Nudge B**, with `n < 5` skip rule. Combined into one `paired_results` tibble with a `Group` column.
5. **Between-group tests** (Section 14) — `run_between_tests()` runs Welch t-test + Wilcoxon rank-sum + Cohen's d for each of: `FollowCount` (renamed `AvgToolUseCount`), `CodeChangesWithTool`, `TotalNewVulns`, `Motivation`, the three severity diffs, `n_issues_fixed`, `n_issues_new`. Output: `between_results` tibble.
6. **Risk-item lookups changed.** Whereas earlier scripts auto-detect Risk PRE/POST by scale type, this script hardcodes both PRE (no suffix) and POST (`__dup_1` suffix) literal names, then verifies they exist (`stop()` if any are missing).
7. **Correlation matrix** drops zero-variance columns before `cor()`.

**Pipeline (numbered sections in code):**

1. Load packages (same set as `SEM_CodeChanges.R`).
2. Load data using the **absolute `base_path`** constant; clean column names; create `sem_outputs_codechanges/` via `dir.create()` if missing.
3. Participant filtering (Nudge / `Number of tasks tool used` / debrief consent).
4. Core observed variables. Build `NudgeType`, `FollowCount`, and the `task{1,2,3}_tool/_changed` → `CodeChangesWithTool` / `AnyCodeChangeWithTool` chain identically to `SEM_CodeChanges.R`.
5. Bandit security-outcome row-sums (`TotalIssueDiff`, `TotalHighSeverityDiff`, `TotalMedSeverityDiff`, `TotalLowSeverityDiff`). Build `TotalNewVulns` by `str_count(tolower(...), "new")` summed across the three `Task X issue change kind [fixed, common, new]` columns. Build `bandit_by_nudge`; `codechange_bandit_assoc` now uses `safe_cor()`.
5b. **CWE / Bandit issue analysis.** Hardcoded `bandit_cwe_map` tribble (B701, B311, B404, B602, B603, B607, B105 → CWE / severity / task). `parse_bandit_issues(df)` builds a long tibble of `(nudge, task, bandit_id, change_kind)` by splitting the comma-joined `Task X issue type ID` and `Task X issue change kind` strings; the result is left-joined to the CWE map. Five summary tibbles are produced and printed: `bandit_freq_overall`, `bandit_freq_by_nudge`, `change_by_nudge`, `bandit_change_cross`, `bandit_change_nudge`. Per-participant counts `n_issues_fixed`, `n_issues_common`, `n_issues_new` are written back onto `df` (the latter equals `TotalNewVulns`). `cwe_cor_table` reports `safe_cor()` of `CodeChangesWithTool` against five issue-outcome metrics. `issue_desc_by_nudge` reports per-Nudge means/SDs of fixed/common/new counts.
6. Baseline Motivation — literal column lookup with regex fallback (`mot_candidates`) if any of the three column names is missing after name cleaning.
7. Auto-detect 6 BI columns by regex (assert exactly 6 matches).
8. Identify Risk columns via **literal names**: PRE without suffix, POST with `__dup_1` suffix; `stop()` if any of the 6 columns is missing (no scale-based auto-detection in this script).
9. Recode all PRE/POST construct items (same reverse-scoring scheme as `SEM_CodeChanges.R`).
10. Construct composite scores and deltas (`norm01` on Risk only).
11. Descriptives — `summary()` plus per-`NudgeType` `group_desc` (CodeChangesWithTool / Motivation / 4 deltas / 3 severity-diff means).
12. Reliability — Cronbach's α for all 9 composites via `safe_alpha`.
13. **Per-group paired tests.** `run_paired_tests(data, pre, post, label)` drops rows with NA on either side, returns `NULL` if `n < 5`, and reports n, mean_pre, mean_post, t, df, p_t, wilcox_V, p_wilcox, and Cohen's d. Run separately for `df_A` (`NudgeType == 0`) and `df_B` (`NudgeType == 1`) over each of the four constructs; combined into a single `paired_results` tibble with a `Group` column.
14. **Between-group tests (A vs B).** `run_between_tests(var, label)` runs Welch's two-sample t-test, Wilcoxon rank-sum, and `effectsize::cohens_d()` using the `var ~ NudgeType_f` formula interface. Tested variables: `FollowCount` (relabeled `AvgToolUseCount`), `CodeChangesWithTool`, `TotalNewVulns`, `Motivation`, `TotalHighSeverityDiff`, `TotalMedSeverityDiff`, `TotalLowSeverityDiff`, `n_issues_fixed`, `n_issues_new` — combined into `between_results`.
15. Correlation matrix — drops zero-variance columns via `select(where(~ sd(., na.rm = TRUE) > 0))` before `cor()`; includes the three severity-diff totals. **Note:** in the script source this section is mislabeled `# 14.` (a duplicate of the between-group-tests heading) — an inconsequential numbering bug.
16. Main path model — `lavaan::sem(model_main, missing = "fiml", se = "bootstrap", bootstrap = 5000, fixed.x = FALSE)` with `CodeChangesWithTool` as the H1 mediator. Prints `summary(..., standardized = TRUE, fit.measures = TRUE, ci = TRUE, rsquare = TRUE)`, `standardizedSolution()`, and `parameterEstimates(..., boot.ci.type = "perc")`.
17. Change-score model (`fit_delta`) — delta outcomes, same `sem()` options.
18. Main + direct effect model (`fit_main_plus_direct`) — adds `direct * NudgeType -> PostBehavioralIntention` and defines `total_effect := direct + ind_total`.
19. `semPaths(fit_main, ...)` → `sem_main_path_diagram_codechanges.png` (1800×1200 @ 200 DPI) written into `output_dir`.
20. Export 16 CSVs to `sem_outputs_codechanges/`: `cleaned_sem_data_codechanges.csv`, the two parameter-estimate files, `paired_tests_by_nudge.csv`, `between_group_tests.csv`, `group_descriptives_by_nudge_codechanges.csv`, `bandit_by_nudge_codechanges.csv`, `codechange_bandit_associations.csv`, plus the seven `cwe_*` tables (`cwe_bandit_freq_overall`, `cwe_bandit_freq_by_nudge`, `cwe_change_kind_by_nudge`, `cwe_bandit_change_crosstab`, `cwe_bandit_change_by_nudge`, `cwe_correlations_with_codechanges`, `cwe_issue_descriptives_by_nudge`). The canonical on-disk copy lives in `sem_outputs_codechanges_nudges/`.

**Outputs (script writes to `sem_outputs_codechanges/`; canonical copy in `sem_outputs_codechanges_nudges/`):**

| File | Schema |
|------|--------|
| `cleaned_sem_data_codechanges.csv` | Full cleaned/derived participant frame (input + recoded items + composites + deltas + Bandit/CWE per-participant counts) |
| `sem_main_parameter_estimates_codechanges.csv` | `parameterEstimates(fit_main)` |
| `sem_delta_parameter_estimates_codechanges.csv` | `parameterEstimates(fit_delta)` |
| `paired_tests_by_nudge.csv` | `Group, construct, n, mean_pre, mean_post, t, df, p_t, wilcox_V, p_wilcox, cohens_d` |
| `between_group_tests.csv` | `variable, mean_A, mean_B, t, df, p_t, wilcox_W, p_wilcox, cohens_d` |
| `group_descriptives_by_nudge_codechanges.csv` | `NudgeType, n, CodeChangesWithTool_M, CodeChangesWithTool_SD, Motivation_M, dRisk_M, dSE_M, dTrust_M, dBI_M, HighSeverityDiff_M, MedSeverityDiff_M, LowSeverityDiff_M` |
| `bandit_by_nudge_codechanges.csv` | `NudgeType, n, CodeChangesWithTool_M, CodeChangesWithTool_SD, AnyCodeChangeWithTool_Rate, HighSeverityDiff_M, MedSeverityDiff_M, LowSeverityDiff_M` |
| `codechange_bandit_associations.csv` | `metric ∈ {TotalHighSeverityDiff, TotalMedSeverityDiff, TotalLowSeverityDiff}; cor_with_CodeChangesWithTool` |
| `cwe_bandit_freq_overall.csv` | `bandit_id, bandit_name, cwe, severity, total_occurrences` |
| `cwe_bandit_freq_by_nudge.csv` | `bandit_id, cwe, Nudge_A, Nudge_B` |
| `cwe_change_kind_by_nudge.csv` | `change_kind, Nudge_A, Nudge_B` |
| `cwe_bandit_change_crosstab.csv` | `bandit_id, fixed, common, new` |
| `cwe_bandit_change_by_nudge.csv` | `bandit_id, change_kind, Nudge_A, Nudge_B` |
| `cwe_correlations_with_codechanges.csv` | `metric ∈ {n_issues_fixed, n_issues_common, n_issues_new, TotalHighSeverityDiff, TotalLowSeverityDiff}; cor_with_CodeChangesWithTool` |
| `cwe_issue_descriptives_by_nudge.csv` | `NudgeType, n, fixed_M, fixed_SD, common_M, new_M, new_SD` |
| `sem_main_path_diagram_codechanges.png` | 1800×1200 @ 200 DPI |

---

## 7. Output Directory Reference

### 7.1 `sem_outputs/` — written by `sem_analysis.r`

| File | Notes |
|------|-------|
| `cleaned_sem_data.csv` | 181 KB, full cleaned input + derived items |
| `sem_main_parameter_estimates.csv` | `lhs, op, rhs, label, est, se, z, pvalue, ci.lower, ci.upper, std.lv, std.all` |
| `sem_delta_parameter_estimates.csv` | same schema as above |
| `paired_t_tests_summary.csv` | 4 rows (one per construct) |
| `group_descriptives_by_nudge.csv` | 2 rows (NudgeType 0 / 1) |
| `sem_main_path_diagram.png` | 193 KB |
| `SEM.xlsx` | Excel rollup of the CSVs (manual / external) |

### 7.2 `sem_outputs_codechanges/` — written by `SEM_CodeChanges.R`

Same as 7.1 but with `_codechanges` suffix on filenames; adds `bandit_by_nudge_codechanges.csv`, `codechange_bandit_associations.csv`, `wilcoxon_summary_codechanges.csv`. Contains both `SEM.xlsx` and `SEM_Codechanges.xlsx` Excel rollups (manual).

### 7.3 `sem_outputs_codechanges_nudges/` — canonical home of `SEMFinal.R` output

Adds the full set of CWE / Bandit issue tables, `paired_tests_by_nudge.csv`, and `between_group_tests.csv` (see §6.3 for full list). Contains `SEMCodeChangesNudges.xlsx` and `SEM_Analysis.Rproj.xlsx` Excel rollups (manual).

---

## 8. Caveats and Known Issues

1. **Three scripts, one input.** All three load `participant_profiles_schema.csv` and re-derive every composite. `SEMFinal.R` is the canonical analysis; the other two are kept for historical/comparison purposes. Don't compose results across scripts as if they were one analysis — each one estimates its own SEM with a different mediator.
2. **Brittle column-name matching.** The Likert column names contain non-breaking spaces, smart quotes (`'` vs `'`), and trailing whitespace. Any change in the survey export format upstream will silently break literal lookups. The scripts try to mitigate this with regex fallbacks (`SEMFinal.R` for Motivation; auto-detection for BI and Risk in earlier scripts), but the current Risk-POST lookup in `SEMFinal.R` is purely literal (`__dup_1` suffix) and **does not** auto-detect.
3. **Suffix mismatch between Python and R.** Python's `make_unique_headers()` emits `__2`/`__3`/... Suffixes; R's `make.unique(... sep = "__dup_")` emits `__dup_1`/`__dup_2`/... When both deduplications stack, the final column names look like `]__2`, `]__2__dup_1`, etc. **Re-check suffixes after every upstream re-export.**
4. **Working-directory and absolute-path dependence.**
   - `sem_analysis.r` reads from / writes to the R working directory.
   - `SEM_CodeChanges.R` reads from the working directory but writes to `sem_outputs_codechanges/`.
   - `SEMFinal.R` uses an absolute `~/Desktop/work/Fard Lab/Analysis/SEM_Analysis` path.
   None of the scripts are portable as-is; either set the working directory via the `.Rproj` or edit `base_path`.
5. **Output-folder vs script-folder mismatch in `SEMFinal.R`.** The script's `output_dir <- "sem_outputs_codechanges"`, but the canonical on-disk artifacts live in `sem_outputs_codechanges_nudges/`. Treat the latter as authoritative; rerunning `SEMFinal.R` will overwrite `sem_outputs_codechanges/` and **not** the `_nudges` folder.
6. **`safe_cor` only in `SEMFinal.R`.** Earlier scripts will produce `cor()` warnings (or NaN) if any variable has zero variance after filtering.
7. **`fixed.x = FALSE` + bootstrap = 5000.** Each model takes meaningful time to fit (3 models × 3 scripts × 5000 reps). Be patient on first run; rerun via `.RData` if available.
8. **Pre-Risk vs Post-Risk scale mismatch.** PRE Risk is a 6-pt agreement scale, POST Risk is a 5-pt frequency scale. The scripts handle this by min-max normalizing both to 0–1 before composing `PreRiskTolerance` / `PostRiskTolerance`, but **delta/correlation interpretations involving Risk are bounded to the [-1, 1] interval**, not the raw 1–6 / 1–5 spaces.
9. **Reverse coding direction.** Higher composite values mean **more risk-tolerant**. `risk_*_1` ("I avoid advanced GenAI features...") and `risk_*_2` ("I avoid activities...that are dangerous...") are reverse-scored; `risk_*_3` ("Despite the risks I use...") is not. If you change the recoding logic, audit all three reverse flags.
10. **CWE map is hardcoded.** The Bandit-ID → CWE / severity / task lookup in `SEMFinal.R` Section 5b reflects the *expected* set of issues for tasks 1/2/3 in this study. New tasks or new Bandit findings will not be joined, and any unmapped `bandit_id` will appear in the issue tables with `NA` for `cwe`/`severity`.
11. **No per-script main entry / CLI.** All three scripts are run by `source("...")` from R/RStudio, top-to-bottom. There are no functions named `main()` and no command-line arguments.
12. **`.RData` / `.Rhistory` are kept under version control.** Treat them as session state, not analysis artifacts.

---

## 9. Reproducibility Notes

### 9.1 Required R packages

```r
install.packages(c(
  "tidyverse", "readr", "psych", "lavaan", "semPlot",
  "effectsize", "broom", "knitr", "stringr"
))
```

### 9.2 Deterministic results

`lavaan` bootstrap CIs depend on the RNG seed. None of the scripts set `set.seed()` before `sem(...)`. To reproduce identical bootstrap CIs across runs, add e.g. `set.seed(2024)` at the top of each script.

### 9.3 Recommended run order

1. Re-export `Aggregation/participant_profiles_schema.csv` from upstream Python pipeline (see `docs/CSV_BUILD_METHODS.md` step 10).
2. Copy it into `SEM_Analysis/participant_profiles_schema.csv`.
3. Open `SEM_Analysis.Rproj` (sets working directory).
4. Source `SEMFinal.R` (canonical). Optionally re-run `SEM_CodeChanges.R` and `sem_analysis.r` if the historical comparisons are needed.
5. After `SEMFinal.R` finishes, manually move/copy the contents of `sem_outputs_codechanges/` to `sem_outputs_codechanges_nudges/` if you want the canonical folder layout to remain stable across reruns.

### 9.4 Linking back to the rest of the project

- Upstream input contract: `docs/TABLE_DOCUMENTATION.md` → "Participant Profiles Schema" section.
- Upstream lineage: `docs/CSV_BUILD_METHODS.md` step 10 (`Aggregation/generate_participant_profiles_schema.py`).
- Sibling analyses (not in this folder): `psychological_constructs_analysis/`, `rq1_statistical_analysis/`. They consume the same wide schema but with a different statistical lens.
