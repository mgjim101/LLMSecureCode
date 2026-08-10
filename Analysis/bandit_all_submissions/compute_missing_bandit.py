#!/usr/bin/env python3
"""
Compute Bandit security metrics for EVERY included participant-task final
submission, including the "unchanged" cases that the two existing Bandit
scripts intentionally skip (they gate on `identify_changed_tasks`).

This is an additive / non-destructive supplement:
  - It does NOT modify any existing script, CSV, or SEM/rq1 input.
  - It reuses the same helpers and the same comparison convention as the
    existing Bandit scripts (absolute counts on the final submission, and
    severity/type diffs relative to the LLM-generated baseline in LLMCode/).

For each participant in data_cleanup/prolific_ids_with_counts.csv and each task
in {1,2,3}, the branch is chosen exactly like the profile generator
(Aggregation/generate_participant_profiles_schema.py):
  - tool used    -> start = event 2 (RUN_TOOL),      final = event 4 (SUB_TOOL)
  - tool skipped -> start = event 1 (SUB_NO_NUDGE),   final = event 3 (SUB_NO_TOOL)

Output:
  bandit_all_submissions/bandit_all_submissions_supplement.csv
    One row per (participant_id, task_id) with the Bandit values plus provenance
    flags (`previously_computed`, `was_missing`, `has_final_snapshot`) so the
    newly filled rows (was_missing=TRUE) can be pasted into the spreadsheet's
    per-task security block.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_IDS_CSV = BASE_DIR / "data_cleanup" / "prolific_ids_with_counts.csv"
PARTICIPANTS_CSV = BASE_DIR / "Tool_CSV" / "participants.csv"
TOOL_USAGE_TASK_CSV = BASE_DIR / "tool_usage" / "tool_usage_task_interactions.csv"
SNAPSHOTS_PATH = BASE_DIR / "Tool_CSV" / "code_snapshots.csv"
LLMCODE_DIR = BASE_DIR / "LLMCode"

# Existing changed-only outputs, used only to flag which rows already existed.
BANDIT_TOOL_SUBMISSIONS_CSV = (
    BASE_DIR / "bandit_comparison_with_tool" / "bandit_comparison_participant_submissions.csv"
)
BANDIT_NO_TOOL_SUBMISSIONS_CSV = (
    BASE_DIR
    / "bandit_comparison_without_tool"
    / "bandit_comparison_nudge_participant_submissions.csv"
)

OUTPUT_CSV = SCRIPT_DIR / "bandit_all_submissions_supplement.csv"

TASK_IDS = ("1", "2", "3")


# ---------------------------------------------------------------------------
# Helpers copied from the existing Bandit scripts (kept self-contained, matching
# the repo's pattern of duplicating these helpers across scripts).
# ---------------------------------------------------------------------------
def load_nudge_mapping(path: Path) -> Dict[int, str]:
    """Build participant_id -> nudge type ('A' or 'B') from participants.csv.

    Group IDs 1-6 map to Nudge A, 7-12 map to Nudge B.
    """
    mapping: Dict[int, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pid_raw = (row.get("participant_id") or "").strip()
            gid_raw = (row.get("group_id") or "").strip()
            if pid_raw.isdigit() and gid_raw.isdigit():
                pid = int(pid_raw)
                gid = int(gid_raw)
                mapping[pid] = "A" if 1 <= gid <= 6 else "B"
    return mapping


def parse_timestamp(raw: str) -> Optional[datetime]:
    """Return datetime from ISO-ish string; fallback to None if parsing fails."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def select_event(
    current: Optional[Tuple[Optional[datetime], int, str]],
    ts: Optional[datetime],
    row_idx: int,
    code: str,
    prefer_latest: bool,
) -> Tuple[Optional[datetime], int, str]:
    """
    Keep the earliest (start events) or latest (final events) entry using
    timestamp, with row order as a tiebreaker when timestamps are missing/equal.
    """
    if current is None:
        return (ts, row_idx, code)

    cur_ts, cur_idx, _ = current

    if ts and cur_ts:
        if prefer_latest:
            return (ts, row_idx, code) if ts > cur_ts else current
        return (ts, row_idx, code) if ts < cur_ts else current

    if ts and not cur_ts:
        return (ts, row_idx, code)
    if cur_ts and not ts:
        return current

    # No timestamps; rely on row order
    if prefer_latest:
        return (ts, row_idx, code) if row_idx > cur_idx else current
    return (ts, row_idx, code) if row_idx < cur_idx else current


def load_original_tasks(llmcode_dir: Path) -> Dict[str, str]:
    """Load original task code from LLMCode/*.json files. Returns {taskid: code}."""
    tasks: Dict[str, str] = {}
    for json_file in sorted(llmcode_dir.glob("task*.json")):
        with json_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            taskid = str(data.get("id", ""))
            code = data.get("code", "")
            if taskid:
                tasks[taskid] = code
    return tasks


def run_bandit_on_code(code: str) -> Dict[str, Any]:
    """Run Bandit on the given code and return parsed results."""
    result: Dict[str, Any] = {"issues": [], "metrics": {}, "error": None}

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            ["bandit", "-f", "json", "-q", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.stdout:
            try:
                data = json.loads(proc.stdout)
                result["issues"] = data.get("results", [])
                result["metrics"] = data.get("metrics", {})
            except json.JSONDecodeError:
                result["error"] = "Failed to parse Bandit JSON output"
        elif proc.stderr and "No issues" not in proc.stderr:
            if "error" in proc.stderr.lower() or "exception" in proc.stderr.lower():
                result["error"] = proc.stderr.strip()
    except FileNotFoundError:
        result["error"] = "Bandit not installed. Install with: pip install bandit"
    except subprocess.TimeoutExpired:
        result["error"] = "Bandit timed out"
    except Exception as exc:  # noqa: BLE001 - mirror existing scripts
        result["error"] = str(exc)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return result


def summarize_issues(issues: List[Dict]) -> Dict[str, List[Dict]]:
    """Summarize issues by test_id (e.g., B101). Returns {test_id: [details, ...]}."""
    summary: Dict[str, List[Dict]] = {}
    for issue in issues:
        test_id = issue.get("test_id", "UNKNOWN")
        summary.setdefault(test_id, []).append(
            {
                "test_name": issue.get("test_name", ""),
                "severity": issue.get("issue_severity", ""),
                "confidence": issue.get("issue_confidence", ""),
                "line_number": issue.get("line_number", 0),
                "issue_text": issue.get("issue_text", ""),
            }
        )
    return summary


def count_by_severity(summary: Dict[str, List[Dict]]) -> Dict[str, int]:
    """Count issues by severity level."""
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNDEFINED": 0}
    for issue_list in summary.values():
        for iss in issue_list:
            sev = (iss.get("severity") or "UNDEFINED").upper()
            if sev in counts:
                counts[sev] += 1
            else:
                counts["UNDEFINED"] += 1
    return counts


def compare_issues(
    original_summary: Dict[str, List[Dict]],
    submitted_summary: Dict[str, List[Dict]],
) -> Dict[str, Any]:
    """Compare issues between original (LLM) and submitted code."""
    original_ids = set(original_summary.keys())
    submitted_ids = set(submitted_summary.keys())

    original_severity = count_by_severity(original_summary)
    submitted_severity = count_by_severity(submitted_summary)

    return {
        "original_count": sum(len(v) for v in original_summary.values()),
        "submitted_count": sum(len(v) for v in submitted_summary.values()),
        "fixed_types": sorted(original_ids - submitted_ids),
        "new_types": sorted(submitted_ids - original_ids),
        "common_types": sorted(original_ids & submitted_ids),
        "original_severity": original_severity,
        "submitted_severity": submitted_severity,
    }


# ---------------------------------------------------------------------------
# Supplement-specific loading / logic
# ---------------------------------------------------------------------------
def norm(value: Optional[str]) -> str:
    return (value or "").strip()


def count_lines(code: str) -> int:
    return len(code.splitlines())


def load_id_rows(path: Path) -> List[Tuple[int, str]]:
    """Return [(participant_id, prolific_id), ...] mirroring the profile generator."""
    out: List[Tuple[int, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            pid_raw = norm(row.get("participant_id"))
            prolific = norm(row.get("prolific_id"))
            if pid_raw.isdigit() and prolific:
                out.append((int(pid_raw), prolific))
    return out


def load_tool_use(path: Path) -> Dict[Tuple[int, str], bool]:
    """(participant_id, task_id) -> tool used? using the same rule as the profile."""
    out: Dict[Tuple[int, str], bool] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            pid_raw = norm(row.get("Participant_ID"))
            task = norm(row.get("Task_ID"))
            action = norm(row.get("Action"))
            if pid_raw.isdigit() and task:
                out[(int(pid_raw), task)] = action.lower() == "used"
    return out


def collect_code_events(
    path: Path, target_ids: set
) -> Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]]:
    """Collect events 1-4 per (participant, task): earliest start, latest final."""
    pair_events: Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]] = {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_idx, row in enumerate(reader):
            pid_raw = norm(row.get("participant_id"))
            if not pid_raw.isdigit():
                continue
            pid = int(pid_raw)
            if pid not in target_ids:
                continue

            event = norm(row.get("eventid"))
            if event not in {"1", "2", "3", "4"}:
                continue

            taskid = norm(row.get("taskid"))
            code = row.get("code") or ""
            ts = parse_timestamp(norm(row.get("timestamp")))

            key = (pid, taskid)
            bucket = pair_events.setdefault(key, {})
            prefer_latest = event in {"3", "4"}
            bucket[event] = select_event(bucket.get(event), ts, row_idx, code, prefer_latest)

    return pair_events


def load_existing_pairs(path: Path, branch: str) -> set:
    """Return {(participant_id, task_id, branch)} already present in an existing CSV."""
    pairs: set = set()
    if not path.exists():
        return pairs
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            pid = norm(row.get("participant_id"))
            task = norm(row.get("task_id"))
            if pid.isdigit() and task:
                pairs.add((int(pid), task, branch))
    return pairs


def type_name_from_summaries(
    test_id: str,
    submitted_summary: Dict[str, List[Dict]],
    original_summary: Dict[str, List[Dict]],
) -> str:
    for summary in (submitted_summary, original_summary):
        entries = summary.get(test_id)
        if entries:
            return entries[0].get("test_name", "")
    return ""


def sort_type_key(type_id: str) -> Tuple[int, str]:
    """Sort B-codes numerically (B101 before B602), matching the profile ordering."""
    if len(type_id) > 1 and type_id[0].upper() == "B" and type_id[1:].isdigit():
        return (int(type_id[1:]), type_id)
    return (10**9, type_id)


def build_type_columns(
    comparison: Dict[str, Any],
    submitted_summary: Dict[str, List[Dict]],
    original_summary: Dict[str, List[Dict]],
) -> Tuple[str, str, str]:
    """Return (type_ids, type_names, change_kinds) joined by ',' in type-id order."""
    kind_by_type: Dict[str, str] = {}
    for tid in comparison.get("new_types", []):
        kind_by_type[tid] = "new"
    for tid in comparison.get("fixed_types", []):
        kind_by_type[tid] = "fixed"
    for tid in comparison.get("common_types", []):
        kind_by_type[tid] = "common"

    ordered = sorted(kind_by_type.keys(), key=sort_type_key)
    type_ids = ",".join(ordered)
    type_names = ",".join(
        type_name_from_summaries(tid, submitted_summary, original_summary) for tid in ordered
    )
    change_kinds = ",".join(kind_by_type[tid] for tid in ordered)
    return type_ids, type_names, change_kinds


def main() -> None:
    print("Loading participant / prolific list...")
    id_rows = load_id_rows(INPUT_IDS_CSV)
    target_ids = {pid for pid, _ in id_rows}
    print(f"  {len(id_rows)} participants")

    print("Loading nudge mapping and tool-use decisions...")
    nudge_mapping = load_nudge_mapping(PARTICIPANTS_CSV)
    tool_use = load_tool_use(TOOL_USAGE_TASK_CSV)

    print("Loading LLM baselines and running Bandit on them...")
    original_tasks = load_original_tasks(LLMCODE_DIR)
    original_summaries: Dict[str, Dict[str, List[Dict]]] = {}
    for taskid, code in original_tasks.items():
        original_summaries[taskid] = summarize_issues(run_bandit_on_code(code).get("issues", []))

    print("Collecting code snapshots (events 1-4)...")
    pair_events = collect_code_events(SNAPSHOTS_PATH, target_ids)

    print("Loading existing changed-only Bandit rows (for provenance flags)...")
    existing_pairs = load_existing_pairs(BANDIT_TOOL_SUBMISSIONS_CSV, "tool")
    existing_pairs |= load_existing_pairs(BANDIT_NO_TOOL_SUBMISSIONS_CSV, "no_tool")

    fieldnames = [
        "participant_id",
        "prolific_id",
        "nudge",
        "task_id",
        "branch",
        "tool_used",
        "code_changed",
        "final_event",
        "final_timestamp",
        "has_final_snapshot",
        "previously_computed",
        "was_missing",
        "start_lines",
        "end_lines",
        "line_delta",
        "issue_count",
        "high_severity",
        "medium_severity",
        "low_severity",
        "severity_diff_high",
        "severity_diff_medium",
        "severity_diff_low",
        "issue_type_ids",
        "issue_type_names",
        "issue_change_kinds",
    ]

    rows: List[Dict[str, Any]] = []
    stats = {
        "total": 0,
        "was_missing": 0,
        "previously_computed": 0,
        "no_final_snapshot": 0,
    }

    print("Running Bandit on final submissions (incl. unchanged)...")
    for pid, prolific in id_rows:
        nudge_label = nudge_mapping.get(pid, "")
        for task in TASK_IDS:
            stats["total"] += 1
            used_tool = tool_use.get((pid, task), False)
            branch = "tool" if used_tool else "no_tool"
            start_event = "2" if used_tool else "1"
            final_event = "4" if used_tool else "3"

            events = pair_events.get((pid, task), {})
            start = events.get(start_event)
            final = events.get(final_event)

            previously_computed = (pid, task, branch) in existing_pairs

            base_row: Dict[str, Any] = {
                "participant_id": pid,
                "prolific_id": prolific,
                "nudge": nudge_label,
                "task_id": task,
                "branch": branch,
                "tool_used": str(used_tool),
                "final_event": final_event,
            }

            if final is None:
                # No final submission snapshot for this branch -> genuinely absent.
                stats["no_final_snapshot"] += 1
                base_row.update(
                    {
                        "code_changed": "",
                        "final_timestamp": "",
                        "has_final_snapshot": "False",
                        "previously_computed": str(previously_computed),
                        "was_missing": str(not previously_computed),
                        "start_lines": count_lines(start[2]) if start else "",
                        "end_lines": "",
                        "line_delta": "",
                        "issue_count": "",
                        "high_severity": "",
                        "medium_severity": "",
                        "low_severity": "",
                        "severity_diff_high": "",
                        "severity_diff_medium": "",
                        "severity_diff_low": "",
                        "issue_type_ids": "",
                        "issue_type_names": "",
                        "issue_change_kinds": "",
                    }
                )
                rows.append(base_row)
                continue

            final_ts, _, final_code = final
            start_code = start[2] if start else None
            code_changed = "" if start is None else str(start_code != final_code)

            submitted_summary = summarize_issues(run_bandit_on_code(final_code).get("issues", []))
            original_summary = original_summaries.get(task, {})
            comparison = compare_issues(original_summary, submitted_summary)

            sub_sev = comparison["submitted_severity"]
            orig_sev = comparison["original_severity"]
            type_ids, type_names, change_kinds = build_type_columns(
                comparison, submitted_summary, original_summary
            )

            if previously_computed:
                stats["previously_computed"] += 1
            else:
                stats["was_missing"] += 1

            base_row.update(
                {
                    "code_changed": code_changed,
                    "final_timestamp": final_ts.isoformat() if final_ts else "",
                    "has_final_snapshot": "True",
                    "previously_computed": str(previously_computed),
                    "was_missing": str(not previously_computed),
                    "start_lines": count_lines(start_code) if start is not None else "",
                    "end_lines": count_lines(final_code),
                    "line_delta": (
                        count_lines(final_code) - count_lines(start_code)
                        if start is not None
                        else ""
                    ),
                    "issue_count": comparison["submitted_count"],
                    "high_severity": sub_sev.get("HIGH", 0),
                    "medium_severity": sub_sev.get("MEDIUM", 0),
                    "low_severity": sub_sev.get("LOW", 0),
                    "severity_diff_high": sub_sev.get("HIGH", 0) - orig_sev.get("HIGH", 0),
                    "severity_diff_medium": sub_sev.get("MEDIUM", 0) - orig_sev.get("MEDIUM", 0),
                    "severity_diff_low": sub_sev.get("LOW", 0) - orig_sev.get("LOW", 0),
                    "issue_type_ids": type_ids,
                    "issue_type_names": type_names,
                    "issue_change_kinds": change_kinds,
                }
            )
            rows.append(base_row)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")
    print(f"  participant-task cells:        {stats['total']}")
    print(f"  previously computed (changed): {stats['previously_computed']}")
    print(f"  newly filled (was_missing):    {stats['was_missing']}")
    print(f"  no final snapshot:             {stats['no_final_snapshot']}")


if __name__ == "__main__":
    main()
