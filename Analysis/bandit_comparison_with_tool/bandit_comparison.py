#!/usr/bin/env python3
"""
Compare Bandit security warnings between LLM-generated task code and participant submissions.

This script:
1. Runs Bandit on the three LLM-generated tasks from LLMCode/*.json
2. For participants who changed their code (event 2 vs event 4), runs Bandit on
   the eventID=4 code snapshot (submitted solution) only for changed tasks
3. Compares the number and type of warnings between LLM code and submitted code

Results are written to outputs/bandit_comparison.txt
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
PROLIFIC_PATH = BASE_DIR / "outputs" / "prolific_ids_with_counts.txt"
SNAPSHOTS_PATH = BASE_DIR / "Tool_CSV" / "code_snapshots.csv"
LLMCODE_DIR = BASE_DIR / "LLMCode"
OUTPUT_PATH = SCRIPT_DIR / "bandit_comparison.txt"
PARTICIPANTS_CSV = BASE_DIR / "Tool_CSV" / "participants.csv"


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


def load_participant_ids(path: Path) -> List[int]:
    """Extract participant_id values from the prolific output file."""
    pattern = re.compile(r"participant_id=(\d+)")
    ids = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = pattern.search(line)
            if match:
                ids.add(int(match.group(1)))
    return sorted(ids)


def load_original_tasks(llmcode_dir: Path) -> Dict[str, str]:
    """Load original task code from LLMCode/*.json files. Returns {taskid: code}."""
    tasks = {}
    for json_file in sorted(llmcode_dir.glob("task*.json")):
        with json_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            taskid = str(data.get("id", ""))
            code = data.get("code", "")
            if taskid:
                tasks[taskid] = code
    return tasks


def select_event(
    current: Optional[Tuple[Optional[datetime], int, str]],
    ts: Optional[datetime],
    row_idx: int,
    code: str,
    prefer_latest: bool,
) -> Tuple[Optional[datetime], int, str]:
    """
    Keep the earliest (for event 2) or latest (for event 4) entry using timestamp,
    with row order as a tiebreaker when timestamps are missing or equal.
    """
    if current is None:
        return (ts, row_idx, code)

    cur_ts, cur_idx, cur_code = current

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


def collect_code_events(
    path: Path, target_ids: set
) -> Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]]:
    """Collect event 2 and event 4 code snapshots for target participants."""
    pair_events: Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]] = {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_idx, row in enumerate(reader):
            pid_raw = (row.get("participant_id") or "").strip()
            if not pid_raw.isdigit():
                continue
            pid = int(pid_raw)
            if pid not in target_ids:
                continue

            event = (row.get("eventid") or "").strip()
            if event not in {"2", "4"}:
                continue

            taskid = (row.get("taskid") or "").strip()
            code = row.get("code") or ""
            ts = parse_timestamp((row.get("timestamp") or "").strip())

            key = (pid, taskid)
            bucket = pair_events.setdefault(key, {})
            prefer_latest = event == "4"
            bucket[event] = select_event(bucket.get(event), ts, row_idx, code, prefer_latest)

    return pair_events


def identify_changed_tasks(
    pair_events: Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]]
) -> Dict[Tuple[int, str], str]:
    """
    Identify tasks where code changed between event 2 and event 4.
    Returns {(participant_id, taskid): event4_code} for changed tasks only.
    """
    changed_tasks = {}
    for (pid, taskid), events in pair_events.items():
        if "2" not in events or "4" not in events:
            continue
        start_code = events["2"][2]
        end_code = events["4"][2]
        if start_code != end_code:
            changed_tasks[(pid, taskid)] = end_code
    return changed_tasks


def run_bandit_on_code(code: str) -> Dict[str, Any]:
    """
    Run Bandit on the given code and return parsed results.
    Returns a dict with 'issues' list and 'metrics'.
    """
    result = {
        "issues": [],
        "metrics": {},
        "error": None
    }
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(code)
        tmp_path = tmp.name
    
    try:
        proc = subprocess.run(
            ["bandit", "-f", "json", "-q", tmp_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Bandit returns non-zero if it finds issues, so we parse output regardless
        if proc.stdout:
            try:
                data = json.loads(proc.stdout)
                result["issues"] = data.get("results", [])
                result["metrics"] = data.get("metrics", {})
            except json.JSONDecodeError:
                result["error"] = "Failed to parse Bandit JSON output"
        elif proc.stderr and "No issues" not in proc.stderr:
            # Check for actual errors
            if "error" in proc.stderr.lower() or "exception" in proc.stderr.lower():
                result["error"] = proc.stderr.strip()
    except FileNotFoundError:
        result["error"] = "Bandit not installed. Install with: pip install bandit"
    except subprocess.TimeoutExpired:
        result["error"] = "Bandit timed out"
    except Exception as e:
        result["error"] = str(e)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    
    return result


def summarize_issues(issues: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Summarize issues by test_id (e.g., B101, B102).
    Returns {test_id: [issue_details, ...]}
    """
    summary = {}
    for issue in issues:
        test_id = issue.get("test_id", "UNKNOWN")
        if test_id not in summary:
            summary[test_id] = []
        summary[test_id].append({
            "test_name": issue.get("test_name", ""),
            "severity": issue.get("issue_severity", ""),
            "confidence": issue.get("issue_confidence", ""),
            "line_number": issue.get("line_number", 0),
            "issue_text": issue.get("issue_text", ""),
        })
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
    submitted_summary: Dict[str, List[Dict]]
) -> Dict[str, Any]:
    """
    Compare issues between original and submitted code.
    Returns comparison metrics including counts, types, and severity breakdown.
    """
    original_ids = set(original_summary.keys())
    submitted_ids = set(submitted_summary.keys())
    
    original_severity = count_by_severity(original_summary)
    submitted_severity = count_by_severity(submitted_summary)
    
    return {
        "original_count": sum(len(v) for v in original_summary.values()),
        "submitted_count": sum(len(v) for v in submitted_summary.values()),
        "original_types": sorted(original_ids),
        "submitted_types": sorted(submitted_ids),
        "fixed_types": sorted(original_ids - submitted_ids),
        "new_types": sorted(submitted_ids - original_ids),
        "common_types": sorted(original_ids & submitted_ids),
        "original_severity": original_severity,
        "submitted_severity": submitted_severity,
    }


def format_output(
    original_tasks: Dict[str, str],
    original_results: Dict[str, Dict],
    changed_tasks: Dict[Tuple[int, str], str],
    submitted_results: Dict[Tuple[int, str], Dict],
    nudge_mapping: Dict[int, str] = None,
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]]]:
    """Build human-readable report lines and normalized CSV-friendly rows."""
    if nudge_mapping is None:
        nudge_mapping = {}
    lines: List[str] = []
    llm_rows: List[Dict[str, Any]] = []
    submission_rows: List[Dict[str, Any]] = []
    type_change_rows: List[Dict[str, Any]] = []
    
    # Section 1: LLM-Generated Tasks Bandit Analysis
    lines.append("=" * 80)
    lines.append("BANDIT SECURITY ANALYSIS: LLM-GENERATED TASKS")
    lines.append("=" * 80)
    lines.append("")
    
    total_original_issues = 0
    all_original_types: Dict[str, int] = {}
    test_id_to_name: Dict[str, str] = {}  # Map test_id to test_name for later use
    
    for taskid in sorted(original_tasks.keys()):
        result = original_results.get(taskid, {})
        issues = result.get("issues", [])
        error = result.get("error")
        summary = summarize_issues(issues)
        severity_counts = count_by_severity(summary)
        
        lines.append(f"Task {taskid}:")
        if error:
            lines.append(f"  Error: {error}")
        else:
            lines.append(f"  Total issues found: {len(issues)}")
            if issues:
                lines.append("  Issues by type:")
                for test_id, issue_list in sorted(summary.items()):
                    all_original_types[test_id] = all_original_types.get(test_id, 0) + len(issue_list)
                    total_original_issues += len(issue_list)
                    test_name = issue_list[0]["test_name"] if issue_list else ""
                    test_id_to_name[test_id] = test_name
                    lines.append(f"    - {test_id} ({test_name}): {len(issue_list)} issue(s)")
                    for i, iss in enumerate(issue_list, 1):
                        severity = iss.get('severity') or 'N/A'
                        confidence = iss.get('confidence') or 'N/A'
                        lines.append(f"        {i}. Line {iss['line_number']}")
                        lines.append(f"           Severity: {severity}, Confidence: {confidence}")
                        lines.append(f"           Description: {iss['issue_text']}")
            else:
                lines.append("  No security issues detected.")
        lines.append("")
        llm_rows.append({
            "task_id": taskid,
            "issue_count": len(issues),
            "high_severity": severity_counts.get("HIGH", 0),
            "medium_severity": severity_counts.get("MEDIUM", 0),
            "low_severity": severity_counts.get("LOW", 0),
        })
    
    lines.append("LLM-Generated Tasks Summary:")
    lines.append(f"  Total issues across all tasks: {total_original_issues}")
    lines.append(f"  Issue types found: {sorted(all_original_types.keys())}")
    for test_id, count in sorted(all_original_types.items()):
        name = test_id_to_name.get(test_id, "")
        lines.append(f"    - {test_id} ({name}): {count} occurrence(s)")
    lines.append("")
    
    # Section 2: Changed Tasks Bandit Analysis
    lines.append("=" * 80)
    lines.append("BANDIT SECURITY ANALYSIS: PARTICIPANT SUBMISSIONS (CHANGED TASKS ONLY)")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Total changed task submissions analyzed: {len(changed_tasks)}")
    lines.append("")
    
    # Group by participant
    by_participant: Dict[int, List[Tuple[str, Dict]]] = {}
    for (pid, taskid), code in changed_tasks.items():
        if pid not in by_participant:
            by_participant[pid] = []
        result = submitted_results.get((pid, taskid), {})
        by_participant[pid].append((taskid, result))
    
    all_comparisons: List[Dict] = []
    
    for pid in sorted(by_participant.keys()):
        task_results = by_participant[pid]
        nudge_label = nudge_mapping.get(pid, "?")
        lines.append(f"Participant {pid} (Nudge {nudge_label}):")
        
        for taskid, result in sorted(task_results, key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
            issues = result.get("issues", [])
            error = result.get("error")
            summary = summarize_issues(issues)
            
            # Build test_id to name mapping for this submission
            for test_id, issue_list in summary.items():
                if issue_list and test_id not in test_id_to_name:
                    test_id_to_name[test_id] = issue_list[0]["test_name"]
            
            # Get original task issues for comparison
            orig_result = original_results.get(taskid, {})
            orig_summary = summarize_issues(orig_result.get("issues", []))
            comparison = compare_issues(orig_summary, summary)
            comparison["participant_id"] = pid
            comparison["taskid"] = taskid
            all_comparisons.append(comparison)
            submitted_severity = comparison["submitted_severity"]
            original_severity = comparison["original_severity"]
            submission_rows.append({
                "participant_id": pid,
                "nudge": nudge_label,
                "task_id": taskid,
                "issue_count": comparison["submitted_count"],
                "high_severity": submitted_severity.get("HIGH", 0),
                "medium_severity": submitted_severity.get("MEDIUM", 0),
                "low_severity": submitted_severity.get("LOW", 0),
                "severity_diff_high": submitted_severity.get("HIGH", 0) - original_severity.get("HIGH", 0),
                "severity_diff_medium": submitted_severity.get("MEDIUM", 0) - original_severity.get("MEDIUM", 0),
                "severity_diff_low": submitted_severity.get("LOW", 0) - original_severity.get("LOW", 0),
            })
            for change_kind, type_list in [
                ("new", comparison.get("new_types", [])),
                ("fixed", comparison.get("fixed_types", [])),
                ("common", comparison.get("common_types", [])),
            ]:
                for type_id in type_list:
                    type_change_rows.append({
                        "participant_id": pid,
                        "nudge": nudge_label,
                        "task_id": taskid,
                        "type_id": type_id,
                        "type_name": test_id_to_name.get(type_id, ""),
                        "change_kind": change_kind,
                    })
            
            lines.append(f"  Task {taskid} (eventID=4 submission):")
            if error:
                lines.append(f"    Error: {error}")
            else:
                lines.append(f"    Issues found: {len(issues)}")
                if issues:
                    lines.append("    Issues by type:")
                    for test_id, issue_list in sorted(summary.items()):
                        test_name = issue_list[0]["test_name"] if issue_list else ""
                        lines.append(f"      - {test_id} ({test_name}): {len(issue_list)} issue(s)")
                        for i, iss in enumerate(issue_list, 1):
                            severity = iss.get('severity') or 'N/A'
                            confidence = iss.get('confidence') or 'N/A'
                            lines.append(f"          {i}. Line {iss['line_number']}")
                            lines.append(f"             Severity: {severity}, Confidence: {confidence}")
                            lines.append(f"             Description: {iss['issue_text']}")
                
                # Comparison with LLM-generated code
                lines.append(f"    Comparison with LLM task {taskid}:")
                lines.append(f"      Total issues - LLM: {comparison['original_count']}, Submitted: {comparison['submitted_count']}")
                
                diff = comparison['submitted_count'] - comparison['original_count']
                if diff > 0:
                    lines.append(f"      Change: +{diff} issues (MORE vulnerabilities)")
                elif diff < 0:
                    lines.append(f"      Change: {diff} issues (FEWER vulnerabilities)")
                else:
                    lines.append(f"      Change: 0 (same count)")
                
                # Severity comparison
                orig_sev = comparison['original_severity']
                sub_sev = comparison['submitted_severity']
                lines.append(f"      By Severity:")
                for sev in ["HIGH", "MEDIUM", "LOW"]:
                    o, s = orig_sev.get(sev, 0), sub_sev.get(sev, 0)
                    diff_sev = s - o
                    diff_str = f"+{diff_sev}" if diff_sev > 0 else str(diff_sev)
                    lines.append(f"        {sev}: LLM={o}, Submitted={s} ({diff_str})")
                
                # Type comparison
                lines.append(f"      By Type:")
                if comparison['fixed_types']:
                    fixed_with_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in comparison['fixed_types']]
                    lines.append(f"        Fixed (removed): {fixed_with_names}")
                if comparison['new_types']:
                    new_with_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in comparison['new_types']]
                    lines.append(f"        New (introduced): {new_with_names}")
                if comparison['common_types']:
                    common_with_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in comparison['common_types']]
                    lines.append(f"        Common (both have): {common_with_names}")
        
        lines.append("")
    
    # Section 3: Overall Comparison Summary
    lines.append("=" * 80)
    lines.append("OVERALL COMPARISON SUMMARY")
    lines.append("=" * 80)
    lines.append("")
    
    if all_comparisons:
        total_orig = sum(c['original_count'] for c in all_comparisons)
        total_sub = sum(c['submitted_count'] for c in all_comparisons)
        
        improved = sum(1 for c in all_comparisons if c['submitted_count'] < c['original_count'])
        worsened = sum(1 for c in all_comparisons if c['submitted_count'] > c['original_count'])
        same = sum(1 for c in all_comparisons if c['submitted_count'] == c['original_count'])
        
        # Collect all issue types
        all_fixed = set()
        all_new = set()
        all_common = set()
        for c in all_comparisons:
            all_fixed.update(c['fixed_types'])
            all_new.update(c['new_types'])
            all_common.update(c['common_types'])
        
        # Aggregate severity counts
        total_orig_sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNDEFINED": 0}
        total_sub_sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNDEFINED": 0}
        for c in all_comparisons:
            for sev in total_orig_sev:
                total_orig_sev[sev] += c['original_severity'].get(sev, 0)
                total_sub_sev[sev] += c['submitted_severity'].get(sev, 0)
        
        lines.append(f"Changed task submissions analyzed: {len(all_comparisons)}")
        lines.append("")
        lines.append("Issue Count Comparison:")
        lines.append(f"  Total LLM issues (for compared tasks): {total_orig}")
        lines.append(f"  Total submitted issues: {total_sub}")
        lines.append(f"  Net change: {total_sub - total_orig:+d}")
        lines.append("")
        
        lines.append("Severity Breakdown (Aggregated):")
        lines.append(f"  {'Severity':<12} {'LLM':>8} {'Submitted':>12} {'Change':>10}")
        lines.append(f"  {'-'*12} {'-'*8} {'-'*12} {'-'*10}")
        for sev in ["HIGH", "MEDIUM", "LOW"]:
            o, s = total_orig_sev[sev], total_sub_sev[sev]
            diff = s - o
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            lines.append(f"  {sev:<12} {o:>8} {s:>12} {diff_str:>10}")
        lines.append("")
        
        lines.append("Submission Outcomes:")
        lines.append(f"  Improved (fewer issues): {improved} submissions")
        lines.append(f"  Worsened (more issues): {worsened} submissions")
        lines.append(f"  Same issue count: {same} submissions")
        lines.append("")
        
        lines.append("Issue Types Analysis:")
        if all_fixed:
            fixed_with_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in sorted(all_fixed)]
            lines.append(f"  Fixed (removed) across submissions: {fixed_with_names}")
        else:
            lines.append(f"  Fixed (removed) across submissions: None")
        if all_new:
            new_with_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in sorted(all_new)]
            lines.append(f"  New (introduced) across submissions: {new_with_names}")
        else:
            lines.append(f"  New (introduced) across submissions: None")
        if all_common:
            common_with_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in sorted(all_common)]
            lines.append(f"  Common (present in both): {common_with_names}")
        lines.append("")
        
        # Per-task breakdown
        lines.append("Per-Task Breakdown:")
        for taskid in sorted(original_tasks.keys()):
            task_comps = [c for c in all_comparisons if c['taskid'] == taskid]
            if task_comps:
                task_orig = sum(c['original_count'] for c in task_comps)
                task_sub = sum(c['submitted_count'] for c in task_comps)
                task_improved = sum(1 for c in task_comps if c['submitted_count'] < c['original_count'])
                task_worsened = sum(1 for c in task_comps if c['submitted_count'] > c['original_count'])
                task_same = sum(1 for c in task_comps if c['submitted_count'] == c['original_count'])
                
                # Task severity breakdown
                task_orig_sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                task_sub_sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                for c in task_comps:
                    for sev in task_orig_sev:
                        task_orig_sev[sev] += c['original_severity'].get(sev, 0)
                        task_sub_sev[sev] += c['submitted_severity'].get(sev, 0)
                
                # Collect types for this task
                task_fixed = set()
                task_new = set()
                for c in task_comps:
                    task_fixed.update(c['fixed_types'])
                    task_new.update(c['new_types'])
                
                lines.append(f"  Task {taskid}:")
                lines.append(f"    Changed submissions: {len(task_comps)}")
                lines.append(f"    LLM issues per task: {original_results.get(taskid, {}).get('issues', []).__len__()}")
                lines.append(f"    Outcomes - Improved: {task_improved}, Worsened: {task_worsened}, Same: {task_same}")
                
                # Severity for this task
                sev_parts = []
                for sev in ["HIGH", "MEDIUM", "LOW"]:
                    o, s = task_orig_sev[sev], task_sub_sev[sev]
                    if o > 0 or s > 0:
                        diff = s - o
                        diff_str = f"+{diff}" if diff > 0 else str(diff)
                        sev_parts.append(f"{sev}: {o}→{s} ({diff_str})")
                if sev_parts:
                    lines.append(f"    Severity changes: {', '.join(sev_parts)}")
                
                # Types for this task
                if task_fixed:
                    fixed_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in sorted(task_fixed)]
                    lines.append(f"    Fixed types: {fixed_names}")
                if task_new:
                    new_names = [f"{tid} ({test_id_to_name.get(tid, '')})" for tid in sorted(task_new)]
                    lines.append(f"    New types: {new_names}")
    else:
        lines.append("No changed task submissions found for comparison.")
    
    # Section 4: Per-Nudge Per-Task Counts
    lines.append("")
    lines.append("=" * 80)
    lines.append("PER-NUDGE PER-TASK COUNTS")
    lines.append("=" * 80)
    lines.append("")
    nudge_task_buckets: Dict[Tuple[str, str], List[Dict]] = {}
    for row in submission_rows:
        key = (row["nudge"], row["task_id"])
        nudge_task_buckets.setdefault(key, []).append(row)
    count_rows: List[Dict[str, Any]] = []
    for (nudge, task_id) in sorted(nudge_task_buckets.keys()):
        bucket = nudge_task_buckets[(nudge, task_id)]
        n = len(bucket)
        row_data = {
            "nudge": nudge,
            "task_id": task_id,
            "n": n,
            "total_issue_count": sum(r["issue_count"] for r in bucket),
            "total_high_severity": sum(r["high_severity"] for r in bucket),
            "total_medium_severity": sum(r["medium_severity"] for r in bucket),
            "total_low_severity": sum(r["low_severity"] for r in bucket),
        }
        count_rows.append(row_data)
        lines.append(
            f"  Nudge {nudge}, Task {task_id} (n={n}): "
            f"total_issues={row_data['total_issue_count']}, "
            f"high={row_data['total_high_severity']}, "
            f"medium={row_data['total_medium_severity']}, "
            f"low={row_data['total_low_severity']}"
        )
    if not count_rows:
        lines.append("  No data for per-nudge per-task counts.")
    lines.append("")

    normalized = {
        "llm_tasks": llm_rows,
        "participant_submissions": submission_rows,
        "type_changes": type_change_rows,
        "nudge_counts": count_rows,
    }
    return lines, normalized


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    """Persist rows to a CSV with the provided headers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_nudge_diff_rows(
    submission_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build summed (not averaged) diffs of participant-vs-original issues.

    Returns:
      1) per-task rows grouped by (nudge, task_id)
      2) overall rows grouped by nudge across all tasks
    """
    per_task_totals: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in submission_rows:
        nudge = row.get("nudge", "?")
        task_id = str(row.get("task_id", ""))
        key = (nudge, task_id)
        bucket = per_task_totals.setdefault(
            key,
            {
                "nudge": nudge,
                "task_id": task_id,
                "n": 0,
                "total_diff_issue_count": 0,
                "total_diff_high_severity": 0,
                "total_diff_medium_severity": 0,
                "total_diff_low_severity": 0,
            },
        )
        bucket["n"] += 1
        bucket["total_diff_issue_count"] += int(row.get("issue_count", 0))
        bucket["total_diff_high_severity"] += int(row.get("severity_diff_high", 0))
        bucket["total_diff_medium_severity"] += int(row.get("severity_diff_medium", 0))
        bucket["total_diff_low_severity"] += int(row.get("severity_diff_low", 0))

    for bucket in per_task_totals.values():
        bucket["total_diff_issue_count"] = (
            bucket["total_diff_high_severity"]
            + bucket["total_diff_medium_severity"]
            + bucket["total_diff_low_severity"]
        )

    per_task_rows = [
        per_task_totals[key]
        for key in sorted(per_task_totals.keys(), key=lambda x: (x[0], x[1]))
    ]

    by_nudge_totals: Dict[str, Dict[str, Any]] = {}
    for row in per_task_rows:
        nudge = row["nudge"]
        bucket = by_nudge_totals.setdefault(
            nudge,
            {
                "nudge": nudge,
                "task_groups": 0,
                "n_submissions": 0,
                "total_diff_issue_count": 0,
                "total_diff_high_severity": 0,
                "total_diff_medium_severity": 0,
                "total_diff_low_severity": 0,
            },
        )
        bucket["task_groups"] += 1
        bucket["n_submissions"] += int(row["n"])
        bucket["total_diff_issue_count"] += int(row["total_diff_issue_count"])
        bucket["total_diff_high_severity"] += int(row["total_diff_high_severity"])
        bucket["total_diff_medium_severity"] += int(row["total_diff_medium_severity"])
        bucket["total_diff_low_severity"] += int(row["total_diff_low_severity"])

    by_nudge_rows = [by_nudge_totals[k] for k in sorted(by_nudge_totals.keys())]
    return per_task_rows, by_nudge_rows


def main() -> None:
    print("Loading participant IDs...")
    participant_ids = load_participant_ids(PROLIFIC_PATH)
    target_set = set(participant_ids)
    print(f"Found {len(participant_ids)} participants")

    print("Loading nudge mapping...")
    nudge_mapping = load_nudge_mapping(PARTICIPANTS_CSV)
    print(f"Mapped {len(nudge_mapping)} participants to nudge groups")
    
    print("Loading LLM-generated tasks from LLMCode/...")
    original_tasks = load_original_tasks(LLMCODE_DIR)
    print(f"Found {len(original_tasks)} tasks")
    
    print("Collecting code snapshots...")
    pair_events = collect_code_events(SNAPSHOTS_PATH, target_set)
    
    print("Identifying changed tasks...")
    changed_tasks = identify_changed_tasks(pair_events)
    print(f"Found {len(changed_tasks)} changed task submissions")
    
    print("\nRunning Bandit on LLM-generated tasks...")
    original_results: Dict[str, Dict] = {}
    for taskid, code in original_tasks.items():
        print(f"  Analyzing LLM task {taskid}...")
        original_results[taskid] = run_bandit_on_code(code)
    
    print("\nRunning Bandit on changed submissions...")
    submitted_results: Dict[Tuple[int, str], Dict] = {}
    count = 0
    total = len(changed_tasks)
    for (pid, taskid), code in changed_tasks.items():
        count += 1
        if count % 10 == 0 or count == total:
            print(f"  Analyzing submission {count}/{total}...")
        submitted_results[(pid, taskid)] = run_bandit_on_code(code)
    
    print("\nGenerating report...")
    report_lines, normalized_data = format_output(
        original_tasks, original_results, changed_tasks, submitted_results,
        nudge_mapping,
    )
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\nWrote Bandit comparison report to {OUTPUT_PATH}")

    llm_csv = SCRIPT_DIR / "bandit_comparison_llm_tasks.csv"
    submission_csv = SCRIPT_DIR / "bandit_comparison_participant_submissions.csv"
    type_changes_csv = SCRIPT_DIR / "bandit_comparison_type_changes.csv"
    counts_csv = SCRIPT_DIR / "bandit_comparison_nudge_counts.csv"
    diffs_per_task_csv = SCRIPT_DIR / "bandit_comparison_nudge_task_total_diffs.csv"
    diffs_by_nudge_csv = SCRIPT_DIR / "bandit_comparison_nudge_total_diffs.csv"

    write_csv(
        llm_csv,
        ["task_id", "issue_count", "high_severity", "medium_severity", "low_severity"],
        normalized_data["llm_tasks"],
    )
    print(f"Wrote LLM task CSV to {llm_csv}")

    write_csv(
        submission_csv,
        [
            "participant_id",
            "nudge",
            "task_id",
            "issue_count",
            "high_severity",
            "medium_severity",
            "low_severity",
            "severity_diff_high",
            "severity_diff_medium",
            "severity_diff_low",
        ],
        normalized_data["participant_submissions"],
    )
    print(f"Wrote participant submissions CSV to {submission_csv}")

    write_csv(
        type_changes_csv,
        ["participant_id", "nudge", "task_id", "type_id", "type_name", "change_kind"],
        normalized_data["type_changes"],
    )
    print(f"Wrote type change CSV to {type_changes_csv}")

    write_csv(
        counts_csv,
        [
            "nudge",
            "task_id",
            "n",
            "total_issue_count",
            "total_high_severity",
            "total_medium_severity",
            "total_low_severity",
        ],
        normalized_data["nudge_counts"],
    )
    print(f"Wrote nudge counts CSV to {counts_csv}")

    diff_rows_per_task, diff_rows_by_nudge = build_nudge_diff_rows(
        normalized_data["participant_submissions"]
    )

    write_csv(
        diffs_per_task_csv,
        [
            "nudge",
            "task_id",
            "n",
            "total_diff_issue_count",
            "total_diff_high_severity",
            "total_diff_medium_severity",
            "total_diff_low_severity",
        ],
        diff_rows_per_task,
    )
    print(f"Wrote per-task nudge total diffs CSV to {diffs_per_task_csv}")

    write_csv(
        diffs_by_nudge_csv,
        [
            "nudge",
            "task_groups",
            "n_submissions",
            "total_diff_issue_count",
            "total_diff_high_severity",
            "total_diff_medium_severity",
            "total_diff_low_severity",
        ],
        diff_rows_by_nudge,
    )
    print(f"Wrote overall nudge total diffs CSV to {diffs_by_nudge_csv}")


if __name__ == "__main__":
    main()
