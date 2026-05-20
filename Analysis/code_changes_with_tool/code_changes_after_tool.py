#!/usr/bin/env python3
"""
Count code changes after tool usage by comparing eventid 2 (start) and eventid 4
 (end) code snapshots for the participants listed in outputs/prolific_ids_with_counts.txt.

For each participant/task pair that has both events, we compare the code strings:
- If identical, the participant ran the tool but did not change the code.
- If different, the participant modified the code after running the tool.

Results are written to outputs/code_changes_after_tool.txt with a per-participant
breakdown and a summary at the end.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
PROLIFIC_PATH = BASE_DIR / "outputs" / "prolific_ids_with_counts.txt"
SNAPSHOTS_PATH = BASE_DIR / "Tool_CSV" / "code_snapshots.csv"
OUTPUT_PATH = SCRIPT_DIR / "code_changes_after_tool.txt"
TASKS_CSV_PATH = SCRIPT_DIR / "code_changes_after_tool_tasks.csv"
SUMMARY_CSV_PATH = SCRIPT_DIR / "code_changes_after_tool_summary.csv"
PARTICIPANTS_CSV = BASE_DIR / "Tool_CSV" / "participants.csv"
COUNTS_CSV_PATH = SCRIPT_DIR / "code_changes_after_tool_nudge_counts.csv"


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
    path: Path, target_ids: Iterable[int]
) -> Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]]:
    """Collect event 2 and event 4 code snapshots for target participants."""
    target_set = set(target_ids)
    pair_events: Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]] = {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_idx, row in enumerate(reader):
            pid_raw = (row.get("participant_id") or "").strip()
            if not pid_raw.isdigit():
                continue
            pid = int(pid_raw)
            if pid not in target_set:
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


def build_results(
    pair_events: Dict[Tuple[int, str], Dict[str, Tuple[Optional[datetime], int, str]]],
    participant_ids: List[int],
):
    """Compute per-participant change counts and track incomplete pairs."""
    per_participant: Dict[int, List[Dict[str, object]]] = {pid: [] for pid in participant_ids}
    skipped_pairs: List[Tuple[int, str]] = []
    total_pairs = 0
    changed_pairs = 0

    def count_lines(code: str) -> int:
        # Preserve behavior for empty strings
        return len(code.splitlines())

    for (pid, taskid), events in pair_events.items():
        has_start = "2" in events
        has_end = "4" in events
        if not (has_start and has_end):
            skipped_pairs.append((pid, taskid))
            continue

        total_pairs += 1
        start_code = events["2"][2]
        end_code = events["4"][2]
        changed = start_code != end_code
        if changed:
            changed_pairs += 1

        start_lines = count_lines(start_code)
        end_lines = count_lines(end_code)
        per_participant.setdefault(pid, []).append(
            {
                "taskid": taskid,
                "changed": changed,
                "start_lines": start_lines,
                "end_lines": end_lines,
                "line_delta": end_lines - start_lines,
                "start_timestamp": events["2"][0],
                "end_timestamp": events["4"][0],
            }
        )

    return per_participant, skipped_pairs, total_pairs, changed_pairs


def format_output(
    participant_ids: List[int],
    per_participant: Dict[int, List[Dict[str, object]]],
    skipped_pairs: List[Tuple[int, str]],
    total_pairs: int,
    changed_pairs: int,
    nudge_mapping: Dict[int, str] = None,
) -> List[str]:
    """Build human-readable report lines."""
    if nudge_mapping is None:
        nudge_mapping = {}
    lines: List[str] = []
    lines.append("Code changes after running the tool (event 2 vs event 4)")
    lines.append(f"Participants in scope: {len(participant_ids)} (from prolific_ids_with_counts.txt)")
    lines.append("Comparison rule: eventid=2 code is start, eventid=4 code is end.")
    lines.append("")

    participants_with_changes = 0
    for pid in participant_ids:
        tasks = per_participant.get(pid, [])
        changed_count = sum(1 for t in tasks if t["changed"])
        unchanged_count = len(tasks) - changed_count
        if changed_count > 0:
            participants_with_changes += 1

        nudge_label = nudge_mapping.get(pid, "?")
        lines.append(f"Participant {pid} (Nudge {nudge_label})")
        lines.append(f"  Task pairs analyzed: {len(tasks)}")
        lines.append(f"  Changed after tool: {changed_count}")
        lines.append(f"  No change after tool: {unchanged_count}")

        if tasks:
            lines.append("  Task details:")
            def sort_key(entry: Dict[str, object]):
                try:
                    return int(entry["taskid"])  # type: ignore[arg-type]
                except Exception:
                    return entry["taskid"]  # type: ignore[return-value]

            for entry in sorted(tasks, key=sort_key):
                status = "changed" if entry["changed"] else "no change"
                lines.append(
                    f"    - taskid={entry['taskid']}: {status} "
                    f"(lines {entry['start_lines']} -> {entry['end_lines']})"
                )
        else:
            lines.append("  Task details: none (no event 2 & 4 pair found)")

        lines.append("")  # spacer

    skipped_count = len(skipped_pairs)
    unchanged_pairs = total_pairs - changed_pairs

    lines.append("Summary")
    lines.append(f"  Task pairs analyzed: {total_pairs}")
    lines.append(f"    with changes: {changed_pairs}")
    lines.append(f"    no changes: {unchanged_pairs}")
    lines.append(f"  Participants with >=1 change: {participants_with_changes}")
    lines.append(f"  Participants with zero changes: {len(participant_ids) - participants_with_changes}")
    lines.append(f"  Incomplete pairs skipped (missing event 2 or 4): {skipped_count}")

    if skipped_count:
        lines.append("  Skipped pair list (participant_id, taskid):")
        for pid, taskid in sorted(skipped_pairs, key=lambda x: (x[0], x[1])):
            lines.append(f"    - {pid}, taskid={taskid}")

    return lines


def iso_or_empty(ts: Optional[datetime]) -> str:
    """Return ISO string for timestamps, or an empty string when absent."""
    return ts.isoformat() if ts else ""


def write_csv_reports(
    per_participant: Dict[int, List[Dict[str, object]]],
    participant_ids: List[int],
    nudge_mapping: Dict[int, str] = None,
) -> None:
    """Emit task-level and per-participant CSV summaries."""
    if nudge_mapping is None:
        nudge_mapping = {}

    tasks_fieldnames = [
        "participant_id",
        "nudge",
        "taskid",
        "changed",
        "start_lines",
        "end_lines",
        "line_delta",
        "start_timestamp",
        "end_timestamp",
    ]
    summary_fieldnames = [
        "participant_id",
        "nudge",
        "tasks_analyzed",
        "changed_task_count",
        "unchanged_task_count",
        "has_any_change",
    ]

    with TASKS_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tasks_fieldnames)
        writer.writeheader()
        for pid in sorted(participant_ids):
            nudge_label = nudge_mapping.get(pid, "?")
            for entry in per_participant.get(pid, []):
                writer.writerow(
                    {
                        "participant_id": pid,
                        "nudge": nudge_label,
                        "taskid": entry["taskid"],
                        "changed": entry["changed"],
                        "start_lines": entry["start_lines"],
                        "end_lines": entry["end_lines"],
                        "line_delta": entry["line_delta"],
                        "start_timestamp": iso_or_empty(entry["start_timestamp"]),
                        "end_timestamp": iso_or_empty(entry["end_timestamp"]),
                    }
                )

    with SUMMARY_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fieldnames)
        writer.writeheader()
        for pid in sorted(participant_ids):
            nudge_label = nudge_mapping.get(pid, "?")
            tasks = per_participant.get(pid, [])
            changed_count = sum(1 for entry in tasks if entry["changed"])
            writer.writerow(
                {
                    "participant_id": pid,
                    "nudge": nudge_label,
                    "tasks_analyzed": len(tasks),
                    "changed_task_count": changed_count,
                    "unchanged_task_count": len(tasks) - changed_count,
                    "has_any_change": changed_count > 0,
                }
            )

    # Write per-nudge per-task counts CSV
    from collections import defaultdict
    nudge_task_buckets: Dict[tuple, list] = defaultdict(list)
    for pid in participant_ids:
        nudge_label = nudge_mapping.get(pid, "?")
        for entry in per_participant.get(pid, []):
            nudge_task_buckets[(nudge_label, entry["taskid"])].append(entry)

    count_fieldnames = ["nudge", "task_id", "n", "changed_count", "unchanged_count"]
    with COUNTS_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=count_fieldnames)
        writer.writeheader()
        for (nudge, task_id) in sorted(nudge_task_buckets.keys()):
            bucket = nudge_task_buckets[(nudge, task_id)]
            n = len(bucket)
            changed_count = sum(1 for e in bucket if e["changed"])
            writer.writerow({
                "nudge": nudge,
                "task_id": task_id,
                "n": n,
                "changed_count": changed_count,
                "unchanged_count": n - changed_count,
            })


def append_nudge_counts_to_report(
    report_lines: List[str],
    per_participant: Dict[int, List[Dict[str, object]]],
    participant_ids: List[int],
    nudge_mapping: Dict[int, str],
) -> None:
    """Append a per-nudge per-task counts section to the text report."""
    from collections import defaultdict
    nudge_task_buckets: Dict[tuple, list] = defaultdict(list)
    for pid in participant_ids:
        nudge_label = nudge_mapping.get(pid, "?")
        for entry in per_participant.get(pid, []):
            nudge_task_buckets[(nudge_label, entry["taskid"])].append(entry)

    report_lines.append("")
    report_lines.append("Per-Nudge Per-Task Counts")
    for (nudge, task_id) in sorted(nudge_task_buckets.keys()):
        bucket = nudge_task_buckets[(nudge, task_id)]
        n = len(bucket)
        changed_count = sum(1 for e in bucket if e["changed"])
        report_lines.append(
            f"  Nudge {nudge}, taskid={task_id} (n={n}): "
            f"changed={changed_count}, unchanged={n - changed_count}"
        )


def main() -> None:
    participant_ids = load_participant_ids(PROLIFIC_PATH)
    nudge_mapping = load_nudge_mapping(PARTICIPANTS_CSV)
    pair_events = collect_code_events(SNAPSHOTS_PATH, participant_ids)
    per_participant, skipped_pairs, total_pairs, changed_pairs = build_results(
        pair_events, participant_ids
    )

    report_lines = format_output(
        participant_ids, per_participant, skipped_pairs, total_pairs, changed_pairs,
        nudge_mapping,
    )
    append_nudge_counts_to_report(report_lines, per_participant, participant_ids, nudge_mapping)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_csv_reports(per_participant, participant_ids, nudge_mapping)
    OUTPUT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote code change summary to {OUTPUT_PATH}")
    print(f"Wrote nudge counts CSV to {COUNTS_CSV_PATH}")


if __name__ == "__main__":
    main()
