#!/usr/bin/env python3
"""
Psychological Constructs Analysis: Trust, Motivation, Self-Efficacy,
Risk Avoidance, and Behavioral Intention.

Analyses performed:
  1. Likert encoding and reverse-coding of survey items
  2. Composite score computation (mean across items per construct)
  3. Cronbach's alpha reliability for each construct
  4. Paired-sample t-tests (PRE vs POST) — overall and stratified by nudge
  5. SEM path analysis: which psychological antecedents predict nudge
     effectiveness (tool usage, code changes, vulnerability reduction)

Input:
  Aggregation/participant_profiles_schema.csv

Outputs:
  psychological_constructs_analysis/
    construct_analysis_report.txt
    construct_composites.csv
    paired_ttest_results.csv
    sem_results.csv
"""

from __future__ import annotations

import csv
import math
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pingouin as pg
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_CSV = BASE_DIR / "Aggregation" / "participant_profiles_schema.csv"

OUTPUT_TXT = SCRIPT_DIR / "construct_analysis_report.txt"
OUTPUT_COMPOSITES_CSV = SCRIPT_DIR / "construct_composites.csv"
OUTPUT_TTEST_CSV = SCRIPT_DIR / "paired_ttest_results.csv"
OUTPUT_SEM_CSV = SCRIPT_DIR / "sem_results.csv"

ALPHA = 0.05

# ---------------------------------------------------------------------------
# Likert encoding maps
# ---------------------------------------------------------------------------

AGREE_MAP = {
    "COMPLETELY DISAGREE": 1,
    "DISAGREE": 2,
    "SOMEHOW DISAGREE": 3,
    "SOMEHOW AGREE": 4,
    "AGREE": 5,
    "COMPLETELY AGREE": 6,
}
AGREE_MAX = 6

FREQ_MAP = {
    "NEVER": 1,
    "RARELY": 2,
    "SOMETIMES": 3,
    "OFTEN": 4,
    "ALWAYS": 5,
}
FREQ_MAX = 5


def encode_column(series: pd.Series, mapping: Dict[str, int]) -> pd.Series:
    return series.astype(str).str.strip().str.upper().map(mapping)


def reverse_code(series: pd.Series, scale_max: int) -> pd.Series:
    return (scale_max + 1) - series


# ---------------------------------------------------------------------------
# Column indices — mapped from participant_profiles_schema.csv header
#
# PRE items use the 6-point agreement scale (COMPLETELY DISAGREE … AGREE).
# POST items also use agreement except POST Risk (cols 117-119) which uses
# the 5-point frequency scale (NEVER … ALWAYS).
# ---------------------------------------------------------------------------

# PRE: Risk Avoidance (agreement scale)
PRE_RISK_COLS = [84, 85, 86]
PRE_RISK_REVERSE = {86}  # "Despite the risks …" is reverse-coded

# PRE: Motivation (agreement scale) — no POST equivalent
PRE_MOTIVATION_COLS = [92, 93, 94]

# PRE: Self-Efficacy (agreement scale)
PRE_SE_COLS = [96, 97, 98, 99]
PRE_SE_REVERSE = {97}  # "I don't feel confident …"

# PRE: Trust (agreement scale)
PRE_TRUST_COLS = [100, 101, 102, 103]

# PRE: Behavioral Intention (agreement scale)
PRE_INTENT_COLS = [104, 105, 106]

# POST: Behavioral Intention (agreement scale)
POST_INTENT_COLS = [114, 115, 116]

# POST: Risk Avoidance (frequency scale — NEVER … ALWAYS)
POST_RISK_COLS = [117, 118, 119]
POST_RISK_REVERSE = {119}  # "Despite the risks …"

# POST: Trust (agreement scale, cols suffixed __2)
POST_TRUST_COLS = [120, 121, 122, 123]

# POST: Self-Efficacy (agreement scale, cols suffixed __2)
POST_SE_COLS = [124, 125, 126, 127]
POST_SE_REVERSE = {125}  # "I don't feel confident …"

# Behavioral outcome columns
COL_TOOL_USES = 3       # "Number of tasks tool used"
COL_NUDGE = 2           # "Nudge" (A or B)
COL_PARTICIPANT = 1     # "participant_id"

# Per-task changed BOOL columns
COL_TASK_CHANGED = [6, 22, 38]   # Task 1/2/3 changed BOOL

# Per-task severity diff columns (high, med, low per task)
COL_SEVERITY_DIFF = {
    "high": [15, 31, 47],
    "med":  [16, 32, 48],
    "low":  [17, 33, 49],
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_data() -> pd.DataFrame:
    """Load participant_profiles_schema.csv by column index."""
    with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        headers = next(reader)
        rows = list(reader)

    short_names = [f"col_{i}" for i in range(len(headers))]
    df = pd.DataFrame(rows, columns=short_names)

    # Drop rows without a nudge assignment (incomplete)
    df = df[df["col_2"].str.strip().isin(["A", "B"])].copy()
    df.reset_index(drop=True, inplace=True)

    return df, headers


# ---------------------------------------------------------------------------
# Composite score computation
# ---------------------------------------------------------------------------


def compute_construct(
    df: pd.DataFrame,
    col_indices: List[int],
    name: str,
    encoding_map: Dict[str, int],
    scale_max: int,
    reverse_set: Optional[set] = None,
    normalize: bool = False,
) -> pd.Series:
    """Encode items, reverse-code where needed, average into composite."""
    items = pd.DataFrame()
    for idx in col_indices:
        col_name = f"col_{idx}"
        encoded = encode_column(df[col_name], encoding_map)
        if reverse_set and idx in reverse_set:
            encoded = reverse_code(encoded, scale_max)
        items[col_name] = encoded

    composite = items.mean(axis=1)
    if normalize:
        composite = (composite - 1) / (scale_max - 1)
    return composite


def compute_all_composites(df: pd.DataFrame) -> pd.DataFrame:
    """Add all PRE/POST composite scores to the dataframe."""
    # PRE composites
    df["risk_avoidance_pre"] = compute_construct(
        df, PRE_RISK_COLS, "risk_pre", AGREE_MAP, AGREE_MAX, PRE_RISK_REVERSE
    )
    df["motivation_pre"] = compute_construct(
        df, PRE_MOTIVATION_COLS, "motiv_pre", AGREE_MAP, AGREE_MAX
    )
    df["self_efficacy_pre"] = compute_construct(
        df, PRE_SE_COLS, "se_pre", AGREE_MAP, AGREE_MAX, PRE_SE_REVERSE
    )
    df["trust_pre"] = compute_construct(
        df, PRE_TRUST_COLS, "trust_pre", AGREE_MAP, AGREE_MAX
    )
    df["intention_pre"] = compute_construct(
        df, PRE_INTENT_COLS, "intent_pre", AGREE_MAP, AGREE_MAX
    )

    # POST composites
    df["intention_post"] = compute_construct(
        df, POST_INTENT_COLS, "intent_post", AGREE_MAP, AGREE_MAX
    )
    df["trust_post"] = compute_construct(
        df, POST_TRUST_COLS, "trust_post", AGREE_MAP, AGREE_MAX
    )
    df["self_efficacy_post"] = compute_construct(
        df, POST_SE_COLS, "se_post", AGREE_MAP, AGREE_MAX, POST_SE_REVERSE
    )

    # POST Risk uses frequency scale — raw composite on its own scale
    df["risk_avoidance_post"] = compute_construct(
        df, POST_RISK_COLS, "risk_post", FREQ_MAP, FREQ_MAX, POST_RISK_REVERSE
    )

    # Normalized versions (0-1) for PRE/POST Risk comparison
    df["risk_avoidance_pre_norm"] = compute_construct(
        df, PRE_RISK_COLS, "risk_pre_n", AGREE_MAP, AGREE_MAX, PRE_RISK_REVERSE,
        normalize=True,
    )
    df["risk_avoidance_post_norm"] = compute_construct(
        df, POST_RISK_COLS, "risk_post_n", FREQ_MAP, FREQ_MAX, POST_RISK_REVERSE,
        normalize=True,
    )

    # Behavioral outcomes
    df["tool_uses"] = pd.to_numeric(df[f"col_{COL_TOOL_USES}"], errors="coerce").fillna(0)
    df["nudge"] = df[f"col_{COL_NUDGE}"].str.strip()

    # Code changes: count of tasks where code changed (True)
    changed_cols = []
    for c in COL_TASK_CHANGED:
        changed_cols.append(df[f"col_{c}"].str.strip().str.lower().isin(["true", "1"]).astype(float))
    df["code_changed_count"] = pd.concat(changed_cols, axis=1).sum(axis=1)

    # Vulnerability reduction: sum of severity diffs (negative = improvement)
    sev_total = pd.Series(0.0, index=df.index)
    for severity, cols in COL_SEVERITY_DIFF.items():
        for c in cols:
            sev_total += pd.to_numeric(df[f"col_{c}"], errors="coerce").fillna(0)
    df["vuln_diff_total"] = sev_total

    return df


# ---------------------------------------------------------------------------
# Cronbach's alpha
# ---------------------------------------------------------------------------


def cronbach_alpha_manual(item_scores: pd.DataFrame) -> Tuple[float, int]:
    """Compute Cronbach's alpha for a set of item columns."""
    valid = item_scores.dropna()
    n_items = valid.shape[1]
    n_obs = len(valid)
    if n_items < 2 or n_obs < 3:
        return float("nan"), n_obs

    item_vars = valid.var(ddof=1)
    total_var = valid.sum(axis=1).var(ddof=1)
    if total_var == 0:
        return float("nan"), n_obs

    alpha = (n_items / (n_items - 1)) * (1 - item_vars.sum() / total_var)
    return alpha, n_obs


def compute_reliability(
    df: pd.DataFrame,
    col_indices: List[int],
    encoding_map: Dict[str, int],
    scale_max: int,
    reverse_set: Optional[set] = None,
) -> Tuple[float, int]:
    """Encode items and compute Cronbach's alpha."""
    items = pd.DataFrame()
    for idx in col_indices:
        encoded = encode_column(df[f"col_{idx}"], encoding_map)
        if reverse_set and idx in reverse_set:
            encoded = reverse_code(encoded, scale_max)
        items[f"item_{idx}"] = encoded
    return cronbach_alpha_manual(items)


# ---------------------------------------------------------------------------
# Paired t-test
# ---------------------------------------------------------------------------


def paired_ttest(
    pre: np.ndarray, post: np.ndarray, label: str
) -> Dict:
    """Run paired-sample t-test with assumption checks."""
    diff = post - pre
    n = len(diff)
    mean_diff = diff.mean()
    sd_diff = diff.std(ddof=1) if n > 1 else 0.0

    # Normality of differences
    shapiro_w, shapiro_p = (np.nan, np.nan)
    if 3 <= n <= 5000:
        shapiro_w, shapiro_p = stats.shapiro(diff)

    # Paired t-test
    t_stat, t_p = stats.ttest_rel(pre, post) if n >= 2 else (np.nan, np.nan)

    # Cohen's d for paired samples
    cohens_d = mean_diff / sd_diff if sd_diff > 0 else 0.0

    # Non-parametric fallback
    wilcoxon_stat, wilcoxon_p = (np.nan, np.nan)
    non_zero = diff[diff != 0]
    if len(non_zero) >= 10:
        wilcoxon_stat, wilcoxon_p = stats.wilcoxon(pre, post)

    return {
        "label": label,
        "n": n,
        "mean_pre": pre.mean(),
        "sd_pre": pre.std(ddof=1),
        "mean_post": post.mean(),
        "sd_post": post.std(ddof=1),
        "mean_diff": mean_diff,
        "sd_diff": sd_diff,
        "shapiro_W": shapiro_w,
        "shapiro_p": shapiro_p,
        "normality_ok": shapiro_p > ALPHA if not np.isnan(shapiro_p) else None,
        "t_stat": t_stat,
        "p_value": t_p,
        "cohens_d": cohens_d,
        "significant_0.05": t_p < ALPHA if not np.isnan(t_p) else None,
        "wilcoxon_stat": wilcoxon_stat,
        "wilcoxon_p": wilcoxon_p,
    }


def run_all_paired_ttests(df: pd.DataFrame) -> List[Dict]:
    """Run paired t-tests for each construct with PRE/POST, overall and by nudge."""
    results = []

    constructs = [
        ("trust_pre", "trust_post", "Trust"),
        ("self_efficacy_pre", "self_efficacy_post", "Self-Efficacy"),
        ("intention_pre", "intention_post", "Behavioral Intention"),
        ("risk_avoidance_pre_norm", "risk_avoidance_post_norm",
         "Risk Avoidance (normalized 0-1)"),
    ]

    for pre_col, post_col, name in constructs:
        # Overall
        valid = df[[pre_col, post_col]].dropna()
        if len(valid) >= 2:
            results.append(paired_ttest(
                valid[pre_col].values, valid[post_col].values,
                f"{name} — Overall",
            ))

        # By nudge
        for nudge in ["A", "B"]:
            sub = df[df["nudge"] == nudge][[pre_col, post_col]].dropna()
            if len(sub) >= 2:
                results.append(paired_ttest(
                    sub[pre_col].values, sub[post_col].values,
                    f"{name} — Nudge {nudge}",
                ))

    return results


# ---------------------------------------------------------------------------
# SEM / Path Analysis
# ---------------------------------------------------------------------------


def run_sem(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Path analysis: PRE composites → behavioral outcomes."""
    try:
        import semopy
    except ImportError:
        return None

    sem_cols = [
        "trust_pre", "self_efficacy_pre", "risk_avoidance_pre",
        "motivation_pre", "intention_pre",
        "tool_uses", "code_changed_count", "vuln_diff_total",
    ]
    sem_df = df[sem_cols].dropna().copy()

    if len(sem_df) < 20:
        return None

    # Standardize for better convergence
    for col in sem_cols:
        sem_df[col] = (sem_df[col] - sem_df[col].mean()) / (sem_df[col].std() + 1e-10)

    model_spec = """
    tool_uses ~ trust_pre + self_efficacy_pre + risk_avoidance_pre + motivation_pre + intention_pre
    code_changed_count ~ trust_pre + self_efficacy_pre + risk_avoidance_pre + motivation_pre + intention_pre
    vuln_diff_total ~ trust_pre + self_efficacy_pre + risk_avoidance_pre + motivation_pre + intention_pre

    trust_pre ~~ self_efficacy_pre
    trust_pre ~~ risk_avoidance_pre
    trust_pre ~~ motivation_pre
    trust_pre ~~ intention_pre
    self_efficacy_pre ~~ risk_avoidance_pre
    self_efficacy_pre ~~ motivation_pre
    self_efficacy_pre ~~ intention_pre
    risk_avoidance_pre ~~ motivation_pre
    risk_avoidance_pre ~~ intention_pre
    motivation_pre ~~ intention_pre
    """

    model = semopy.Model(model_spec)
    model.fit(sem_df)
    estimates = model.inspect()

    try:
        fit_stats = semopy.calc_stats(model)
    except Exception:
        fit_stats = None

    return estimates, fit_stats, sem_df


def run_sem_by_nudge(df: pd.DataFrame) -> Dict[str, Optional[pd.DataFrame]]:
    """Run SEM path analysis separately for each nudge group."""
    try:
        import semopy
    except ImportError:
        return {}

    sem_cols = [
        "trust_pre", "self_efficacy_pre", "risk_avoidance_pre",
        "motivation_pre", "intention_pre",
        "tool_uses", "code_changed_count", "vuln_diff_total",
    ]

    model_spec = """
    tool_uses ~ trust_pre + self_efficacy_pre + risk_avoidance_pre + motivation_pre + intention_pre
    code_changed_count ~ trust_pre + self_efficacy_pre + risk_avoidance_pre + motivation_pre + intention_pre
    vuln_diff_total ~ trust_pre + self_efficacy_pre + risk_avoidance_pre + motivation_pre + intention_pre

    trust_pre ~~ self_efficacy_pre
    trust_pre ~~ risk_avoidance_pre
    trust_pre ~~ motivation_pre
    trust_pre ~~ intention_pre
    self_efficacy_pre ~~ risk_avoidance_pre
    self_efficacy_pre ~~ motivation_pre
    self_efficacy_pre ~~ intention_pre
    risk_avoidance_pre ~~ motivation_pre
    risk_avoidance_pre ~~ intention_pre
    motivation_pre ~~ intention_pre
    """

    results = {}
    for nudge in ["A", "B"]:
        sub = df[df["nudge"] == nudge][sem_cols].dropna().copy()
        if len(sub) < 15:
            results[nudge] = None
            continue
        for col in sem_cols:
            sub[col] = (sub[col] - sub[col].mean()) / (sub[col].std() + 1e-10)
        model = semopy.Model(model_spec)
        model.fit(sub)
        results[nudge] = model.inspect()

    return results


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def fmt_val(v, decimals=4) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return "N/A"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def build_report(
    df: pd.DataFrame,
    headers: List[str],
    reliability: Dict[str, Tuple[float, int]],
    ttest_results: List[Dict],
    sem_result,
    sem_by_nudge: Dict,
) -> str:
    lines: List[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("=" * 76)
    lines.append("  PSYCHOLOGICAL CONSTRUCTS ANALYSIS REPORT")
    lines.append(f"  Generated: {timestamp}")
    lines.append("=" * 76)

    # ---- Section 1: Construct overview ----
    lines.append("")
    lines.append("-" * 76)
    lines.append("  SECTION 1: CONSTRUCT DEFINITIONS AND ITEM MAPPING")
    lines.append("-" * 76)

    construct_items = {
        "Risk Avoidance (PRE)": (PRE_RISK_COLS, PRE_RISK_REVERSE),
        "Motivation (PRE only)": (PRE_MOTIVATION_COLS, set()),
        "Self-Efficacy (PRE)": (PRE_SE_COLS, PRE_SE_REVERSE),
        "Trust (PRE)": (PRE_TRUST_COLS, set()),
        "Behavioral Intention (PRE)": (PRE_INTENT_COLS, set()),
        "Behavioral Intention (POST)": (POST_INTENT_COLS, set()),
        "Risk Avoidance (POST)": (POST_RISK_COLS, POST_RISK_REVERSE),
        "Trust (POST)": (POST_TRUST_COLS, set()),
        "Self-Efficacy (POST)": (POST_SE_COLS, POST_SE_REVERSE),
    }

    for cname, (cols, rev) in construct_items.items():
        lines.append(f"\n  {cname}:")
        for c in cols:
            prefix = "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools."
            h = headers[c]
            short = h[len(prefix):].strip() if h.startswith(prefix) else h[:80]
            rev_tag = " [REVERSE]" if c in rev else ""
            lines.append(f"    col {c:3d}: {short}{rev_tag}")

    # ---- Section 2: Scale note ----
    lines.append("")
    lines.append("  NOTE: PRE Risk uses 6-point agreement scale (1-6).")
    lines.append("        POST Risk uses 5-point frequency scale (1-5).")
    lines.append("        For paired t-tests on Risk Avoidance, both are")
    lines.append("        normalized to 0-1 range before comparison.")

    # ---- Section 3: Reliability ----
    lines.append("")
    lines.append("-" * 76)
    lines.append("  SECTION 2: RELIABILITY (CRONBACH'S ALPHA)")
    lines.append("-" * 76)
    lines.append(f"  {'Construct':<40s}  {'Alpha':>8s}  {'n':>5s}")
    lines.append(f"  {'-'*40}  {'-'*8}  {'-'*5}")
    for cname, (alpha, n) in reliability.items():
        lines.append(f"  {cname:<40s}  {fmt_val(alpha):>8s}  {n:>5d}")
    lines.append("")
    lines.append("  Interpretation: alpha >= 0.70 is acceptable;")
    lines.append("                  alpha >= 0.80 is good.")

    # ---- Section 4: Descriptive statistics ----
    lines.append("")
    lines.append("-" * 76)
    lines.append("  SECTION 3: DESCRIPTIVE STATISTICS (COMPOSITE SCORES)")
    lines.append("-" * 76)

    composite_cols = [
        ("risk_avoidance_pre", "Risk Avoidance (PRE, 1-6)"),
        ("risk_avoidance_post", "Risk Avoidance (POST, 1-5)"),
        ("risk_avoidance_pre_norm", "Risk Avoidance PRE (norm 0-1)"),
        ("risk_avoidance_post_norm", "Risk Avoidance POST (norm 0-1)"),
        ("motivation_pre", "Motivation (PRE, 1-6)"),
        ("self_efficacy_pre", "Self-Efficacy (PRE, 1-6)"),
        ("self_efficacy_post", "Self-Efficacy (POST, 1-6)"),
        ("trust_pre", "Trust (PRE, 1-6)"),
        ("trust_post", "Trust (POST, 1-6)"),
        ("intention_pre", "Intention (PRE, 1-6)"),
        ("intention_post", "Intention (POST, 1-6)"),
        ("tool_uses", "Tool Uses (count)"),
        ("code_changed_count", "Code Changes (count)"),
        ("vuln_diff_total", "Vuln Severity Diff (total)"),
    ]

    lines.append(f"  {'Measure':<38s}  {'n':>4s}  {'M':>7s}  {'SD':>7s}  "
                  f"{'Mdn':>7s}  {'Min':>7s}  {'Max':>7s}")
    lines.append(f"  {'-'*38}  {'-'*4}  {'-'*7}  {'-'*7}  "
                 f"{'-'*7}  {'-'*7}  {'-'*7}")
    for col, label in composite_cols:
        vals = df[col].dropna()
        if len(vals) == 0:
            continue
        lines.append(
            f"  {label:<38s}  {len(vals):>4d}  {vals.mean():>7.3f}  "
            f"{vals.std(ddof=1):>7.3f}  {vals.median():>7.3f}  "
            f"{vals.min():>7.3f}  {vals.max():>7.3f}"
        )

    # By nudge
    for nudge in ["A", "B"]:
        sub = df[df["nudge"] == nudge]
        lines.append(f"\n  --- Nudge {nudge} ---")
        lines.append(f"  {'Measure':<38s}  {'n':>4s}  {'M':>7s}  {'SD':>7s}")
        lines.append(f"  {'-'*38}  {'-'*4}  {'-'*7}  {'-'*7}")
        for col, label in composite_cols:
            vals = sub[col].dropna()
            if len(vals) == 0:
                continue
            lines.append(
                f"  {label:<38s}  {len(vals):>4d}  {vals.mean():>7.3f}  "
                f"{vals.std(ddof=1):>7.3f}"
            )

    # ---- Section 5: Paired t-tests ----
    lines.append("")
    lines.append("-" * 76)
    lines.append("  SECTION 4: PAIRED-SAMPLE T-TESTS (PRE vs POST)")
    lines.append("-" * 76)
    lines.append("")
    n_primary = sum(1 for r in ttest_results if "Overall" in r["label"])
    bonf_alpha = ALPHA / n_primary if n_primary > 0 else ALPHA
    lines.append(f"  Number of primary comparisons: {n_primary}")
    lines.append(f"  Bonferroni-corrected alpha: {bonf_alpha:.4f}")
    lines.append("")

    for r in ttest_results:
        lines.append(f"  {'='*70}")
        lines.append(f"  {r['label']}")
        lines.append(f"  {'='*70}")
        lines.append(f"    n = {r['n']}")
        lines.append(f"    PRE:   M = {fmt_val(r['mean_pre'])}, SD = {fmt_val(r['sd_pre'])}")
        lines.append(f"    POST:  M = {fmt_val(r['mean_post'])}, SD = {fmt_val(r['sd_post'])}")
        lines.append(f"    Mean difference (POST - PRE): {fmt_val(r['mean_diff'])}")
        lines.append(f"    SD of differences: {fmt_val(r['sd_diff'])}")
        lines.append(f"    Shapiro-Wilk on diffs: W={fmt_val(r['shapiro_W'])}, "
                     f"p={fmt_val(r['shapiro_p'])} "
                     f"({'normal' if r['normality_ok'] else 'NOT normal'})")
        lines.append(f"    Paired t-test: t = {fmt_val(r['t_stat'])}, "
                     f"p = {fmt_val(r['p_value'])}")
        lines.append(f"    Cohen's d = {fmt_val(r['cohens_d'])}")
        sig = "SIGNIFICANT" if r["significant_0.05"] else "NOT significant"
        lines.append(f"    -> {sig} at alpha = {ALPHA}")
        if "Overall" in r["label"]:
            bonf_sig = r["p_value"] < bonf_alpha if not np.isnan(r["p_value"]) else False
            bonf_label = "SIGNIFICANT" if bonf_sig else "NOT significant"
            lines.append(f"    -> {bonf_label} after Bonferroni correction "
                        f"(alpha = {bonf_alpha:.4f})")
        if not np.isnan(r["wilcoxon_stat"]):
            lines.append(f"    [Non-parametric] Wilcoxon signed-rank: "
                        f"W = {fmt_val(r['wilcoxon_stat'])}, "
                        f"p = {fmt_val(r['wilcoxon_p'])}")
        lines.append("")

    # ---- Section 6: SEM ----
    lines.append("-" * 76)
    lines.append("  SECTION 5: SEM PATH ANALYSIS")
    lines.append("  Antecedents (PRE composites) → Behavioral Outcomes")
    lines.append("-" * 76)

    if sem_result is not None:
        estimates, fit_stats, sem_df = sem_result
        lines.append(f"\n  Sample size for SEM: n = {len(sem_df)}")

        if fit_stats is not None:
            lines.append("\n  Model Fit Indices:")
            for col in fit_stats.columns:
                val = fit_stats[col].iloc[0]
                lines.append(f"    {col}: {fmt_val(val)}")

        lines.append("\n  Path Estimates (Overall):")
        lines.append(f"  {'lval':<24s} {'op':>3s} {'rval':<24s} "
                     f"{'Estimate':>10s} {'Std.Err':>10s} {'z-value':>10s} {'p-value':>10s}")
        lines.append(f"  {'-'*24} {'-'*3} {'-'*24} "
                     f"{'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        for _, row in estimates.iterrows():
            lines.append(
                f"  {str(row['lval']):<24s} {str(row['op']):>3s} "
                f"{str(row['rval']):<24s} "
                f"{fmt_val(row.get('Estimate', np.nan)):>10s} "
                f"{fmt_val(row.get('Std. Err', np.nan)):>10s} "
                f"{fmt_val(row.get('z-value', np.nan)):>10s} "
                f"{fmt_val(row.get('p-value', np.nan)):>10s}"
            )
    else:
        lines.append("\n  SEM could not be fitted (insufficient data or semopy not available).")

    # SEM by nudge
    for nudge, est in sem_by_nudge.items():
        lines.append(f"\n  --- SEM Path Estimates — Nudge {nudge} ---")
        if est is None:
            lines.append("    Insufficient data for this group.")
            continue
        # Only show regression paths (op == '~')
        reg = est[est["op"] == "~"]
        lines.append(f"  {'Outcome':<24s} {'<-':>3s} {'Predictor':<24s} "
                     f"{'Estimate':>10s} {'p-value':>10s}")
        lines.append(f"  {'-'*24} {'-'*3} {'-'*24} {'-'*10} {'-'*10}")
        for _, row in reg.iterrows():
            lines.append(
                f"  {str(row['lval']):<24s} {'<-':>3s} "
                f"{str(row['rval']):<24s} "
                f"{fmt_val(row.get('Estimate', np.nan)):>10s} "
                f"{fmt_val(row.get('p-value', np.nan)):>10s}"
            )

    lines.append("")
    lines.append("  Effect size benchmarks (Cohen's d):")
    lines.append("    |0.2| = small, |0.5| = medium, |0.8| = large")
    lines.append("")
    lines.append("=" * 76)
    lines.append("  END OF REPORT")
    lines.append("=" * 76)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Loading data...")
    df, headers = load_data()
    print(f"  Loaded {len(df)} participants with nudge assignment.")

    print("Computing composite scores...")
    df = compute_all_composites(df)

    # Reliability
    print("Computing reliability (Cronbach's alpha)...")
    reliability = {}
    reliability["Risk Avoidance (PRE)"] = compute_reliability(
        df, PRE_RISK_COLS, AGREE_MAP, AGREE_MAX, PRE_RISK_REVERSE
    )
    reliability["Motivation (PRE)"] = compute_reliability(
        df, PRE_MOTIVATION_COLS, AGREE_MAP, AGREE_MAX
    )
    reliability["Self-Efficacy (PRE)"] = compute_reliability(
        df, PRE_SE_COLS, AGREE_MAP, AGREE_MAX, PRE_SE_REVERSE
    )
    reliability["Trust (PRE)"] = compute_reliability(
        df, PRE_TRUST_COLS, AGREE_MAP, AGREE_MAX
    )
    reliability["Intention (PRE)"] = compute_reliability(
        df, PRE_INTENT_COLS, AGREE_MAP, AGREE_MAX
    )
    reliability["Intention (POST)"] = compute_reliability(
        df, POST_INTENT_COLS, AGREE_MAP, AGREE_MAX
    )
    reliability["Risk Avoidance (POST)"] = compute_reliability(
        df, POST_RISK_COLS, FREQ_MAP, FREQ_MAX, POST_RISK_REVERSE
    )
    reliability["Trust (POST)"] = compute_reliability(
        df, POST_TRUST_COLS, AGREE_MAP, AGREE_MAX
    )
    reliability["Self-Efficacy (POST)"] = compute_reliability(
        df, POST_SE_COLS, AGREE_MAP, AGREE_MAX, POST_SE_REVERSE
    )

    # Paired t-tests
    print("Running paired-sample t-tests...")
    ttest_results = run_all_paired_ttests(df)

    # SEM
    print("Running SEM path analysis...")
    sem_result = run_sem(df)
    sem_by_nudge = run_sem_by_nudge(df)

    # Build report
    print("Building report...")
    report = build_report(df, headers, reliability, ttest_results,
                          sem_result, sem_by_nudge)

    # Write outputs
    OUTPUT_TXT.write_text(report, encoding="utf-8")
    print(f"\nReport written to {OUTPUT_TXT}")

    # Composites CSV
    composite_output_cols = [
        f"col_{COL_PARTICIPANT}", "nudge",
        "risk_avoidance_pre", "risk_avoidance_post",
        "risk_avoidance_pre_norm", "risk_avoidance_post_norm",
        "motivation_pre",
        "self_efficacy_pre", "self_efficacy_post",
        "trust_pre", "trust_post",
        "intention_pre", "intention_post",
        "tool_uses", "code_changed_count", "vuln_diff_total",
    ]
    composites_df = df[composite_output_cols].copy()
    composites_df.rename(columns={f"col_{COL_PARTICIPANT}": "participant_id"}, inplace=True)
    composites_df.to_csv(OUTPUT_COMPOSITES_CSV, index=False)
    print(f"Composites CSV written to {OUTPUT_COMPOSITES_CSV}")

    # T-test CSV
    ttest_df = pd.DataFrame(ttest_results)
    ttest_df.to_csv(OUTPUT_TTEST_CSV, index=False)
    print(f"Paired t-test CSV written to {OUTPUT_TTEST_CSV}")

    # SEM CSV
    if sem_result is not None:
        estimates, _, _ = sem_result
        estimates.to_csv(OUTPUT_SEM_CSV, index=False)
        print(f"SEM estimates CSV written to {OUTPUT_SEM_CSV}")

    print("\n" + report)


if __name__ == "__main__":
    main()
