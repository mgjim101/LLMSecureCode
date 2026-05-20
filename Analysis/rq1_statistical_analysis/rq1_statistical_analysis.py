#!/usr/bin/env python3
"""
RQ1 Statistical Analysis: Can behavioural interventions promote security-aware
practices among software developers when using LLMs?

Compares Group A vs Group B (independent samples) on three behavioural metrics:
  1. Tool usage count (# times tool was used per participant)
  2. New vulnerabilities introduced (Bandit issue_count, with/without tool)
  3. Code changes made (# tasks with code changes, with/without tool)

For each metric the script:
  - Aggregates to the participant level
  - Checks normality (Shapiro-Wilk) and variance homogeneity (Levene)
  - Runs Welch's t-test (parametric) or Mann-Whitney U (non-parametric)
  - Computes effect size (Hedges' g / rank-biserial r)
  - Repeats per task as a secondary analysis

Outputs are written to rq1_statistical_analysis/ as a .txt report and .csv
summary table.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

TOOL_PARTICIPANT_CSV = BASE_DIR / "tool_usage" / "tool_usage_participant_summary.csv"
TOOL_INTERACTIONS_CSV = BASE_DIR / "tool_usage" / "tool_usage_task_interactions.csv"

BANDIT_WT_SUBMISSIONS_CSV = (
    BASE_DIR / "bandit_comparison_with_tool" / "bandit_comparison_participant_submissions.csv"
)
BANDIT_WOT_SUBMISSIONS_CSV = (
    BASE_DIR
    / "bandit_comparison_without_tool"
    / "bandit_comparison_nudge_participant_submissions.csv"
)

CC_WT_SUMMARY_CSV = BASE_DIR / "code_changes_with_tool" / "code_changes_after_tool_summary.csv"
CC_WT_TASKS_CSV = BASE_DIR / "code_changes_with_tool" / "code_changes_after_tool_tasks.csv"
CC_WOT_SUMMARY_CSV = (
    BASE_DIR / "code_changes_without_tool" / "code_changes_after_nudge_summary.csv"
)
CC_WOT_TASKS_CSV = (
    BASE_DIR / "code_changes_without_tool" / "code_changes_after_nudge_tasks.csv"
)

OUTPUT_TXT = SCRIPT_DIR / "rq1_statistical_analysis.txt"
OUTPUT_CSV = SCRIPT_DIR / "rq1_statistical_analysis_summary.csv"

ALPHA = 0.05
BONFERRONI_ALPHA = ALPHA / 3  # three primary comparisons

# ---------------------------------------------------------------------------
# Effect-size helpers
# ---------------------------------------------------------------------------


def hedges_g(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d with Hedges' g small-sample correction."""
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return float("nan")
    var1, var2 = a.var(ddof=1), b.var(ddof=1)
    pooled = math.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled == 0:
        return 0.0
    d = (a.mean() - b.mean()) / pooled
    correction = 1 - 3 / (4 * (n1 + n2) - 9)
    return d * correction


def rank_biserial_r(U: float, n1: int, n2: int) -> float:
    """Rank-biserial correlation from Mann-Whitney U."""
    return 1 - (2 * U) / (n1 * n2)


# ---------------------------------------------------------------------------
# Core comparison routine
# ---------------------------------------------------------------------------


class TestResult:
    """Container for one A-vs-B comparison."""

    def __init__(self, label: str):
        self.label = label
        self.n_a: int = 0
        self.n_b: int = 0
        self.mean_a: float = float("nan")
        self.mean_b: float = float("nan")
        self.sd_a: float = float("nan")
        self.sd_b: float = float("nan")
        self.median_a: float = float("nan")
        self.median_b: float = float("nan")
        self.shapiro_a: Tuple[float, float] = (float("nan"), float("nan"))
        self.shapiro_b: Tuple[float, float] = (float("nan"), float("nan"))
        self.levene: Tuple[float, float] = (float("nan"), float("nan"))
        self.normality_ok: bool = False
        self.primary_test: str = ""
        self.test_stat: float = float("nan")
        self.p_value: float = float("nan")
        self.effect_size_name: str = ""
        self.effect_size: float = float("nan")
        self.supplementary_test: Optional[str] = None
        self.supplementary_stat: float = float("nan")
        self.supplementary_p: float = float("nan")
        self.supplementary_es_name: str = ""
        self.supplementary_es: float = float("nan")
        self.too_small: bool = False


def run_comparison(a: np.ndarray, b: np.ndarray, label: str) -> TestResult:
    """Full assumption-checking + test pipeline for independent groups."""
    res = TestResult(label)
    res.n_a, res.n_b = len(a), len(b)

    if res.n_a < 3 or res.n_b < 3:
        res.too_small = True
        if res.n_a > 1:
            res.mean_a, res.sd_a, res.median_a = a.mean(), a.std(ddof=1), float(np.median(a))
        elif res.n_a == 1:
            res.mean_a, res.median_a = a.mean(), float(np.median(a))
        if res.n_b > 1:
            res.mean_b, res.sd_b, res.median_b = b.mean(), b.std(ddof=1), float(np.median(b))
        elif res.n_b == 1:
            res.mean_b, res.median_b = b.mean(), float(np.median(b))
        return res

    res.mean_a = a.mean()
    res.mean_b = b.mean()
    res.sd_a = a.std(ddof=1)
    res.sd_b = b.std(ddof=1)
    res.median_a = float(np.median(a))
    res.median_b = float(np.median(b))

    # Constant arrays have zero variance — no test is meaningful
    if res.sd_a == 0 and res.sd_b == 0:
        res.primary_test = "(no variance in either group)"
        return res

    # Shapiro-Wilk (skip for constant arrays to avoid scipy warnings)
    if res.sd_a > 0:
        res.shapiro_a = stats.shapiro(a)
    else:
        res.shapiro_a = (float("nan"), 1.0)
    if res.sd_b > 0:
        res.shapiro_b = stats.shapiro(b)
    else:
        res.shapiro_b = (float("nan"), 1.0)
    res.normality_ok = res.shapiro_a[1] > ALPHA and res.shapiro_b[1] > ALPHA

    # Levene
    res.levene = stats.levene(a, b)

    if res.normality_ok:
        t_stat, t_p = stats.ttest_ind(a, b, equal_var=False)
        res.primary_test = "Welch's t-test"
        res.test_stat = t_stat
        res.p_value = t_p
        res.effect_size_name = "Hedges' g"
        res.effect_size = hedges_g(a, b)
    else:
        u_stat, u_p = stats.mannwhitneyu(a, b, alternative="two-sided")
        res.primary_test = "Mann-Whitney U"
        res.test_stat = u_stat
        res.p_value = u_p
        res.effect_size_name = "rank-biserial r"
        res.effect_size = rank_biserial_r(u_stat, len(a), len(b))

        # Supplementary parametric test (CLT justification for n~48)
        t_stat, t_p = stats.ttest_ind(a, b, equal_var=False)
        res.supplementary_test = "Welch's t-test"
        res.supplementary_stat = t_stat
        res.supplementary_p = t_p
        res.supplementary_es_name = "Hedges' g"
        res.supplementary_es = hedges_g(a, b)

    return res


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def fmt(result: TestResult) -> str:
    """Format a TestResult into a human-readable block."""
    lines: List[str] = []
    lines.append("")
    lines.append("=" * 72)
    lines.append(f"  {result.label}")
    lines.append("=" * 72)

    if result.too_small:
        lines.append(f"  Group A: n={result.n_a}")
        lines.append(f"  Group B: n={result.n_b}")
        lines.append("  *** TOO FEW OBSERVATIONS FOR INFERENTIAL TESTING ***")
        if not math.isnan(result.mean_a):
            lines.append(f"  Descriptive A: M={result.mean_a:.4f}, SD={result.sd_a:.4f}")
        if not math.isnan(result.mean_b):
            lines.append(f"  Descriptive B: M={result.mean_b:.4f}, SD={result.sd_b:.4f}")
        return "\n".join(lines)

    lines.append(
        f"  Group A: n={result.n_a}, M={result.mean_a:.4f}, "
        f"SD={result.sd_a:.4f}, Mdn={result.median_a:.4f}"
    )
    lines.append(
        f"  Group B: n={result.n_b}, M={result.mean_b:.4f}, "
        f"SD={result.sd_b:.4f}, Mdn={result.median_b:.4f}"
    )
    lines.append("")

    w_a, p_a = result.shapiro_a
    w_b, p_b = result.shapiro_b
    lines.append(
        f"  Shapiro-Wilk A: W={w_a:.4f}, p={p_a:.4f} "
        f"{'(normal)' if p_a > ALPHA else '(NOT normal)'}"
    )
    lines.append(
        f"  Shapiro-Wilk B: W={w_b:.4f}, p={p_b:.4f} "
        f"{'(normal)' if p_b > ALPHA else '(NOT normal)'}"
    )

    lev_f, lev_p = result.levene
    lines.append(
        f"  Levene's test:  F={lev_f:.4f}, p={lev_p:.4f} "
        f"{'(equal var)' if lev_p > ALPHA else '(unequal var)'}"
    )

    lines.append("")
    lines.append(
        f"  Primary test: {result.primary_test}  "
        f"stat={result.test_stat:.4f}, p={result.p_value:.4f}"
    )
    lines.append(f"  Effect size:  {result.effect_size_name} = {result.effect_size:.4f}")

    sig_label = "SIGNIFICANT" if result.p_value < ALPHA else "NOT significant"
    lines.append(f"  -> {sig_label} at alpha={ALPHA} (p={result.p_value:.4f})")

    bonf_label = "SIGNIFICANT" if result.p_value < BONFERRONI_ALPHA else "NOT significant"
    lines.append(
        f"  -> {bonf_label} after Bonferroni correction "
        f"(alpha={BONFERRONI_ALPHA:.4f}, p={result.p_value:.4f})"
    )

    if result.supplementary_test:
        lines.append("")
        lines.append(
            f"  [Supplementary] {result.supplementary_test}:  "
            f"stat={result.supplementary_stat:.4f}, p={result.supplementary_p:.4f}"
        )
        lines.append(
            f"  [Supplementary] {result.supplementary_es_name} = "
            f"{result.supplementary_es:.4f}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


def analysis_1_tool_usage() -> List[TestResult]:
    """Compare AVG #TOOL=YES between Group A and Group B."""
    results: List[TestResult] = []

    # Aggregated per participant
    df = pd.read_csv(TOOL_PARTICIPANT_CSV)
    a = df.loc[df["nudge"] == "A", "Total_Uses"].to_numpy(dtype=float)
    b = df.loc[df["nudge"] == "B", "Total_Uses"].to_numpy(dtype=float)
    results.append(run_comparison(a, b, "Analysis 1: Tool Usage — Total_Uses per participant"))

    # Per task (binary used/skipped)
    interactions = pd.read_csv(TOOL_INTERACTIONS_CSV)
    interactions["used"] = (interactions["Action"] == "Used").astype(float)
    for task_id in sorted(interactions["Task_ID"].unique()):
        sub = interactions[interactions["Task_ID"] == task_id]
        ta = sub.loc[sub["nudge"] == "A", "used"].to_numpy(dtype=float)
        tb = sub.loc[sub["nudge"] == "B", "used"].to_numpy(dtype=float)
        results.append(
            run_comparison(ta, tb, f"Analysis 1 (per task): Task {task_id} — Tool Used (binary)")
        )

    return results


def analysis_2_vulnerabilities() -> List[TestResult]:
    """Compare AVG # NEW VULS between Group A and Group B."""
    results: List[TestResult] = []

    # --- 2a: With tool (events 2→4) ---
    df_wt = pd.read_csv(BANDIT_WT_SUBMISSIONS_CSV)
    agg_wt = df_wt.groupby(["participant_id", "nudge"])["issue_count"].sum().reset_index()
    a = agg_wt.loc[agg_wt["nudge"] == "A", "issue_count"].to_numpy(dtype=float)
    b = agg_wt.loc[agg_wt["nudge"] == "B", "issue_count"].to_numpy(dtype=float)
    results.append(
        run_comparison(a, b, "Analysis 2a: New Vulnerabilities WITH TOOL (issue_count, aggregated)")
    )

    # Per task
    for task_id in sorted(df_wt["task_id"].unique()):
        sub = df_wt[df_wt["task_id"] == task_id]
        ta = sub.loc[sub["nudge"] == "A", "issue_count"].to_numpy(dtype=float)
        tb = sub.loc[sub["nudge"] == "B", "issue_count"].to_numpy(dtype=float)
        results.append(
            run_comparison(
                ta, tb, f"Analysis 2a (per task): Task {task_id} — Vulns WITH TOOL"
            )
        )

    # Severity diff columns
    for col in ["severity_diff_high", "severity_diff_medium", "severity_diff_low"]:
        agg = df_wt.groupby(["participant_id", "nudge"])[col].sum().reset_index()
        a = agg.loc[agg["nudge"] == "A", col].to_numpy(dtype=float)
        b = agg.loc[agg["nudge"] == "B", col].to_numpy(dtype=float)
        results.append(
            run_comparison(a, b, f"Analysis 2a: {col} WITH TOOL (aggregated)")
        )

    # --- 2b: Without tool (events 1→3) ---
    df_wot = pd.read_csv(BANDIT_WOT_SUBMISSIONS_CSV)
    agg_wot = df_wot.groupby(["participant_id", "nudge"])["issue_count"].sum().reset_index()
    a = agg_wot.loc[agg_wot["nudge"] == "A", "issue_count"].to_numpy(dtype=float)
    b = agg_wot.loc[agg_wot["nudge"] == "B", "issue_count"].to_numpy(dtype=float)
    results.append(
        run_comparison(
            a, b, "Analysis 2b: New Vulnerabilities WITHOUT TOOL (issue_count, aggregated)"
        )
    )

    return results


def analysis_3_code_changes() -> List[TestResult]:
    """Compare AVG # of code changes between Group A and Group B."""
    results: List[TestResult] = []

    # --- 3a: With tool (events 2→4) ---
    df_wt = pd.read_csv(CC_WT_SUMMARY_CSV)
    a = df_wt.loc[df_wt["nudge"] == "A", "changed_task_count"].to_numpy(dtype=float)
    b = df_wt.loc[df_wt["nudge"] == "B", "changed_task_count"].to_numpy(dtype=float)
    results.append(
        run_comparison(a, b, "Analysis 3a: Code Changes WITH TOOL (changed_task_count)")
    )

    # Per task (binary changed/not)
    tasks_wt = pd.read_csv(CC_WT_TASKS_CSV)
    tasks_wt["changed_int"] = tasks_wt["changed"].map(
        {True: 1.0, False: 0.0, "True": 1.0, "False": 0.0}
    )
    for task_id in sorted(tasks_wt["taskid"].unique()):
        sub = tasks_wt[tasks_wt["taskid"] == task_id]
        ta = sub.loc[sub["nudge"] == "A", "changed_int"].to_numpy(dtype=float)
        tb = sub.loc[sub["nudge"] == "B", "changed_int"].to_numpy(dtype=float)
        results.append(
            run_comparison(
                ta, tb, f"Analysis 3a (per task): Task {task_id} — Code Changed WITH TOOL"
            )
        )

    # --- 3b: Without tool (events 1→3) ---
    df_wot = pd.read_csv(CC_WOT_SUMMARY_CSV)
    a = df_wot.loc[df_wot["nudge"] == "A", "changed_task_count"].to_numpy(dtype=float)
    b = df_wot.loc[df_wot["nudge"] == "B", "changed_task_count"].to_numpy(dtype=float)
    results.append(
        run_comparison(a, b, "Analysis 3b: Code Changes WITHOUT TOOL (changed_task_count)")
    )

    # Per task
    tasks_wot = pd.read_csv(CC_WOT_TASKS_CSV)
    tasks_wot["changed_int"] = tasks_wot["changed"].map(
        {True: 1.0, False: 0.0, "True": 1.0, "False": 0.0}
    )
    for task_id in sorted(tasks_wot["taskid"].unique()):
        sub = tasks_wot[tasks_wot["taskid"] == task_id]
        ta = sub.loc[sub["nudge"] == "A", "changed_int"].to_numpy(dtype=float)
        tb = sub.loc[sub["nudge"] == "B", "changed_int"].to_numpy(dtype=float)
        if len(ta) > 0 and len(tb) > 0:
            results.append(
                run_comparison(
                    ta, tb,
                    f"Analysis 3b (per task): Task {task_id} — Code Changed WITHOUT TOOL",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def build_summary_rows(all_results: List[TestResult]) -> List[Dict]:
    """Build rows for the summary CSV."""
    rows = []
    for r in all_results:
        rows.append(
            {
                "analysis": r.label,
                "n_A": r.n_a,
                "n_B": r.n_b,
                "mean_A": f"{r.mean_a:.4f}" if not math.isnan(r.mean_a) else "",
                "mean_B": f"{r.mean_b:.4f}" if not math.isnan(r.mean_b) else "",
                "sd_A": f"{r.sd_a:.4f}" if not math.isnan(r.sd_a) else "",
                "sd_B": f"{r.sd_b:.4f}" if not math.isnan(r.sd_b) else "",
                "shapiro_p_A": (
                    f"{r.shapiro_a[1]:.4f}" if not math.isnan(r.shapiro_a[1]) else ""
                ),
                "shapiro_p_B": (
                    f"{r.shapiro_b[1]:.4f}" if not math.isnan(r.shapiro_b[1]) else ""
                ),
                "levene_p": f"{r.levene[1]:.4f}" if not math.isnan(r.levene[1]) else "",
                "primary_test": r.primary_test,
                "test_statistic": (
                    f"{r.test_stat:.4f}" if not math.isnan(r.test_stat) else ""
                ),
                "p_value": f"{r.p_value:.4f}" if not math.isnan(r.p_value) else "",
                "significant_0.05": (
                    "yes"
                    if not math.isnan(r.p_value) and r.p_value < ALPHA
                    else ("" if math.isnan(r.p_value) else "no")
                ),
                "significant_bonferroni": (
                    "yes"
                    if not math.isnan(r.p_value) and r.p_value < BONFERRONI_ALPHA
                    else ("" if math.isnan(r.p_value) else "no")
                ),
                "effect_size_name": r.effect_size_name,
                "effect_size": (
                    f"{r.effect_size:.4f}" if not math.isnan(r.effect_size) else ""
                ),
                "too_small": "yes" if r.too_small else "no",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    all_results: List[TestResult] = []

    all_results.extend(analysis_1_tool_usage())
    all_results.extend(analysis_2_vulnerabilities())
    all_results.extend(analysis_3_code_changes())

    # Build text report
    report_lines = [
        "RQ1 Statistical Analysis Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Design: Independent samples (between-subjects), Group A vs Group B",
        f"Primary alpha: {ALPHA}",
        f"Bonferroni-corrected alpha (3 primary tests): {BONFERRONI_ALPHA:.4f}",
        "",
        "Procedure per comparison:",
        "  1. Aggregate to participant level",
        "  2. Shapiro-Wilk normality test per group",
        "  3. Levene's test for homogeneity of variance",
        "  4. If normal -> Welch's t-test; otherwise -> Mann-Whitney U",
        "  5. Effect size: Hedges' g (parametric) or rank-biserial r (non-parametric)",
        "",
        "Effect size benchmarks:",
        "  Hedges' g:        |0.2| small, |0.5| medium, |0.8| large",
        "  Rank-biserial r:  |0.1| small, |0.3| medium, |0.5| large",
    ]

    for r in all_results:
        report_lines.append(fmt(r))

    report_lines.append("")
    report_lines.append("=" * 72)
    report_lines.append("  END OF REPORT")
    report_lines.append("=" * 72)

    report_text = "\n".join(report_lines)
    OUTPUT_TXT.write_text(report_text, encoding="utf-8")

    # Build summary CSV
    rows = build_summary_rows(all_results)
    summary_df = pd.DataFrame(rows)
    summary_df.to_csv(OUTPUT_CSV, index=False)

    print(report_text)
    print(f"\nReport written to {OUTPUT_TXT}")
    print(f"Summary CSV written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
