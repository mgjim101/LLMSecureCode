"""Generate tool usage summary per participant.

Reads participant_ids from outputs/prolific_ids_with_counts.txt and summarizes
tool usage (used vs skipped) from Tool_CSV/tool_usage.csv. Results are written
to outputs/tool_usage_summary.txt and CSV files.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
LIMESURVEY_IDS_PATH = BASE_DIR / "data_cleanup" / "filter_limesurvey_ids.csv"
TOOL_USAGE_PATH = BASE_DIR / "Tool_CSV" / "tool_usage.csv"
OUTPUT_PATH = SCRIPT_DIR / "tool_usage_summary.txt"
OUTPUT_CSV_PARTICIPANT = SCRIPT_DIR / "tool_usage_participant_summary.csv"
OUTPUT_CSV_INTERACTIONS = SCRIPT_DIR / "tool_usage_task_interactions.csv"
OUTPUT_CSV_METADATA = SCRIPT_DIR / "tool_usage_global_metrics.csv"
PARTICIPANTS_CSV = BASE_DIR / "Tool_CSV" / "participants.csv"
COUNTS_CSV_PATH = SCRIPT_DIR / "tool_usage_nudge_counts.csv"
NUDGE_COMPARISON_CSV_PATH = SCRIPT_DIR / "tool_usage_nudge_comparison.csv"


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


def load_participant_ids(limesurvey_path: Path, participants_path: Path) -> List[int]:
    """Resolve participant_id integers from filter_limesurvey_ids.csv.

    Reads the list of prolific hex IDs from limesurvey_path, then looks each
    one up in participants_path to find the corresponding integer participant_id.
    """
    with limesurvey_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        prolific_ids = {row["prolific_id"].strip() for row in reader}

    ids: set[int] = set()
    with participants_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pid_raw = (row.get("participant_id") or "").strip()
            ppid = (row.get("prolific_pid") or "").strip()
            if ppid in prolific_ids and pid_raw.isdigit():
                ids.add(int(pid_raw))
    return sorted(ids)


def load_tool_usage(
    path: Path, participant_ids: Iterable[int]
) -> Tuple[Dict[int, Dict[str, List[Dict[str, str]]]], List[Dict]]:
    """Load tool usage rows for target participants, keeping only the latest attempt per task."""
    usage: Dict[int, Dict[str, List[Dict[str, str]]]] = {
        pid: {"used": [], "skipped": []} for pid in participant_ids
    }
    latest_per_task: Dict[Tuple[int, str], Dict[str, object]] = {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pid = int(row["participant_id"])
            if pid not in usage:
                continue
            task_id = row["taskid"]
            timestamp = datetime.fromisoformat(row["tool_decision_time"])
            key = (pid, task_id)
            existing = latest_per_task.get(key)
            if existing and existing["timestamp"] >= timestamp:
                continue
            latest_per_task[key] = {
                "participant_id": pid,
                "taskid": task_id,
                "tool_used": row["tool_used"],
                "timestamp": timestamp,
            }

    raw_interactions: List[Dict] = []
    sequence_counters: Dict[int, int] = {pid: 0 for pid in participant_ids}

    sorted_entries = sorted(
        latest_per_task.values(), key=lambda entry: entry["timestamp"]
    )
    for entry in sorted_entries:
        pid = entry["participant_id"]
        used_tool = entry["tool_used"].strip().lower() == "true"
        bucket = "used" if used_tool else "skipped"
        usage[pid][bucket].append({"taskid": entry["taskid"]})

        sequence_counters[pid] += 1
        raw_interactions.append({
            "participant_id": pid,
            "task_id": entry["taskid"],
            "action": "Used" if used_tool else "Skipped",
            "sequence_order": sequence_counters[pid],
        })

    return usage, raw_interactions


def summarize_counts(
    usage: Dict[int, Dict[str, List[Dict[str, str]]]]
) -> Tuple[int, int]:
    """Return overall counts of used and skipped events."""
    total_used = sum(len(info["used"]) for info in usage.values())
    total_skipped = sum(len(info["skipped"]) for info in usage.values())
    return total_used, total_skipped


def format_participant_section(
    pid: int,
    usage: Dict[str, List[Dict[str, str]]],
    nudge_label: str = "?",
) -> List[str]:
    """Format the section for a single participant."""
    lines: List[str] = []
    used = usage["used"]
    skipped = usage["skipped"]

    lines.append(f"Participant {pid} (Nudge {nudge_label})")
    lines.append(f"  Used tool: {len(used)} time(s)")
    lines.append(f"  Skipped tool: {len(skipped)} time(s)")

    lines.append("  Used tool details:")
    if used:
        for entry in used:
            lines.append(f"    - taskid={entry['taskid']}")
    else:
        lines.append("    None")

    lines.append("  Skipped tool details:")
    if skipped:
        for entry in skipped:
            lines.append(f"    - taskid={entry['taskid']}")
    else:
        lines.append("    None")

    lines.append("")  # spacer between participants
    return lines


def aggregate_task_breakdown(
    usage: Dict[int, Dict[str, List[Dict[str, str]]]]
) -> Dict[str, Dict[str, int]]:
    """Compute breakdowns by taskid."""
    task_breakdown: Dict[str, Dict[str, int]] = {}

    for participant_usage in usage.values():
        for bucket_name in ("used", "skipped"):
            for entry in participant_usage[bucket_name]:
                task_id = entry["taskid"]
                task_stats = task_breakdown.setdefault(
                    task_id, {"used": 0, "skipped": 0}
                )
                task_stats[bucket_name] += 1

    return task_breakdown


def write_participant_summary_csv(
    path: Path,
    participant_ids: List[int],
    usage: Dict[int, Dict[str, List[Dict[str, str]]]],
    nudge_mapping: Dict[int, str] = None,
) -> None:
    """Write Sheet 1: Participant Summary CSV."""
    if nudge_mapping is None:
        nudge_mapping = {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Participant_ID", "nudge", "Total_Uses", "Total_Skips", "Completion_Rate"])
        
        for pid in participant_ids:
            nudge_label = nudge_mapping.get(pid, "?")
            total_uses = len(usage[pid]["used"])
            total_skips = len(usage[pid]["skipped"])
            total = total_uses + total_skips
            completion_rate = (total_uses / total * 100) if total > 0 else 0.0
            writer.writerow([pid, nudge_label, total_uses, total_skips, f"{completion_rate:.2f}%"])


def write_task_interactions_csv(
    path: Path,
    raw_interactions: List[Dict],
    nudge_mapping: Dict[int, str] = None,
) -> None:
    """Write Sheet 2: Task Interaction Log CSV."""
    if nudge_mapping is None:
        nudge_mapping = {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Interaction_ID", "Participant_ID", "nudge", "Task_ID", "Action", "Sequence_Order"])
        
        for interaction_id, interaction in enumerate(raw_interactions, start=1):
            nudge_label = nudge_mapping.get(interaction["participant_id"], "?")
            writer.writerow([
                interaction_id,
                interaction["participant_id"],
                nudge_label,
                interaction["task_id"],
                interaction["action"],
                interaction["sequence_order"],
            ])


def write_global_metrics_csv(
    path: Path,
    participant_ids: List[int],
    usage: Dict[int, Dict[str, List[Dict[str, str]]]],
) -> None:
    """Write Summary Reference Table (Metadata) CSV."""
    total_used, total_skipped = summarize_counts(usage)
    task_breakdown = aggregate_task_breakdown(usage)
    avg_used = total_used / len(participant_ids) if participant_ids else 0
    avg_skipped = total_skipped / len(participant_ids) if participant_ids else 0
    
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total_Participants", len(participant_ids)])
        writer.writerow(["Total_Tool_Uses", total_used])
        writer.writerow(["Total_Tool_Skips", total_skipped])
        writer.writerow(["Avg_Uses_Per_Participant", f"{avg_used:.2f}"])
        writer.writerow(["Avg_Skips_Per_Participant", f"{avg_skipped:.2f}"])
        
        # Task breakdown
        for task_id in sorted(task_breakdown.keys(), key=int):
            stats = task_breakdown[task_id]
            writer.writerow([f"Task_{task_id}_Uses", stats["used"]])
            writer.writerow([f"Task_{task_id}_Skips", stats["skipped"]])


def build_report(
    participant_ids: List[int],
    usage: Dict[int, Dict[str, List[Dict[str, str]]]],
    nudge_mapping: Dict[int, str] = None,
) -> List[str]:
    """Create the full text report."""
    if nudge_mapping is None:
        nudge_mapping = {}
    lines: List[str] = []
    lines.append("Tool usage summary per participant")
    lines.append(
        f"Participants in scope: {len(participant_ids)} "
        f"(from prolific_ids_with_counts.txt)"
    )
    lines.append("")

    for pid in participant_ids:
        nudge_label = nudge_mapping.get(pid, "?")
        lines.extend(format_participant_section(pid, usage[pid], nudge_label))

    total_used, total_skipped = summarize_counts(usage)
    task_breakdown = aggregate_task_breakdown(usage)
    avg_used = total_used / len(participant_ids) if participant_ids else 0
    avg_skipped = total_skipped / len(participant_ids) if participant_ids else 0

    lines.append("Overall summary")
    lines.append(f"  Total tool uses: {total_used}")
    lines.append(f"  Total tool skips: {total_skipped}")
    lines.append(f"  Avg uses per participant: {avg_used:.2f}")
    lines.append(f"  Avg skips per participant: {avg_skipped:.2f}")
    lines.append("")
    lines.append("  Task breakdown (used | skipped):")
    for task_id in sorted(task_breakdown.keys(), key=int):
        stats = task_breakdown[task_id]
        lines.append(f"    taskid={task_id}: {stats['used']} | {stats['skipped']}")
    lines.append("")
    return lines


def write_nudge_counts(
    participant_ids: List[int],
    usage: Dict[int, Dict[str, List[Dict[str, str]]]],
    nudge_mapping: Dict[int, str],
    report_lines: List[str],
) -> None:
    """Write per-nudge per-task counts CSV and append section to text report."""
    from collections import defaultdict

    nudge_task_used: Dict[tuple, int] = defaultdict(int)
    nudge_task_skipped: Dict[tuple, int] = defaultdict(int)
    nudge_task_total: Dict[tuple, int] = defaultdict(int)

    for pid in participant_ids:
        nudge_label = nudge_mapping.get(pid, "?")
        for entry in usage[pid]["used"]:
            key = (nudge_label, entry["taskid"])
            nudge_task_used[key] += 1
            nudge_task_total[key] += 1
        for entry in usage[pid]["skipped"]:
            key = (nudge_label, entry["taskid"])
            nudge_task_skipped[key] += 1
            nudge_task_total[key] += 1

    all_keys = sorted(set(nudge_task_total.keys()))
    count_fieldnames = [
        "nudge", "task_id", "n", "used_count", "skipped_count", "avg_tool_uses",
    ]

    with COUNTS_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=count_fieldnames)
        writer.writeheader()
        for (nudge, task_id) in all_keys:
            n = nudge_task_total[(nudge, task_id)]
            used_count = nudge_task_used.get((nudge, task_id), 0)
            skipped_count = nudge_task_skipped.get((nudge, task_id), 0)
            avg_tool_uses = used_count / n if n > 0 else 0.0
            writer.writerow({
                "nudge": nudge,
                "task_id": task_id,
                "n": n,
                "used_count": used_count,
                "skipped_count": skipped_count,
                "avg_tool_uses": f"{avg_tool_uses:.4f}",
            })

    report_lines.append("")
    report_lines.append("Per-Nudge Per-Task Counts")
    for (nudge, task_id) in all_keys:
        n = nudge_task_total[(nudge, task_id)]
        used_count = nudge_task_used.get((nudge, task_id), 0)
        skipped_count = nudge_task_skipped.get((nudge, task_id), 0)
        report_lines.append(
            f"  Nudge {nudge}, taskid={task_id} (n={n}): "
            f"used={used_count}, skipped={skipped_count}"
        )


def write_nudge_comparison_csv(
    participant_ids: List[int],
    usage: Dict[int, Dict[str, List[Dict[str, str]]]],
    nudge_mapping: Dict[int, str],
) -> None:
    """Write per-nudge AVG tool use rate averaged across all tasks."""
    from collections import defaultdict

    nudge_task_used: Dict[tuple, int] = defaultdict(int)
    nudge_task_total: Dict[tuple, int] = defaultdict(int)

    for pid in participant_ids:
        nudge_label = nudge_mapping.get(pid, "?")
        for entry in usage[pid]["used"]:
            key = (nudge_label, entry["taskid"])
            nudge_task_used[key] += 1
            nudge_task_total[key] += 1
        for entry in usage[pid]["skipped"]:
            key = (nudge_label, entry["taskid"])
            nudge_task_total[key] += 1

    all_task_ids = sorted(
        {task_id for (_, task_id) in nudge_task_total.keys()}, key=int
    )

    rows = []
    for nudge_label in ("A", "B"):
        per_task_avgs = []
        total_n = 0
        total_used = 0
        for task_id in all_task_ids:
            n = nudge_task_total.get((nudge_label, task_id), 0)
            used = nudge_task_used.get((nudge_label, task_id), 0)
            total_n += n
            total_used += used
            if n > 0:
                per_task_avgs.append(used / n)
        avg_across_tasks = sum(per_task_avgs) / len(per_task_avgs) if per_task_avgs else 0.0
        rows.append({
            "nudge": nudge_label,
            "n": total_n,
            "total_used_count": total_used,
            "avg_tool_uses": f"{avg_across_tasks:.4f}",
        })

    fieldnames = ["nudge", "n", "total_used_count", "avg_tool_uses"]
    with NUDGE_COMPARISON_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    participant_ids = load_participant_ids(LIMESURVEY_IDS_PATH, PARTICIPANTS_CSV)
    nudge_mapping = load_nudge_mapping(PARTICIPANTS_CSV)
    usage, raw_interactions = load_tool_usage(TOOL_USAGE_PATH, participant_ids)

    # Write text report
    report_lines = build_report(participant_ids, usage, nudge_mapping)
    write_nudge_counts(participant_ids, usage, nudge_mapping, report_lines)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote summary to {OUTPUT_PATH}")
    
    # Write CSV outputs
    write_participant_summary_csv(OUTPUT_CSV_PARTICIPANT, participant_ids, usage, nudge_mapping)
    print(f"Wrote participant summary CSV to {OUTPUT_CSV_PARTICIPANT}")
    
    write_task_interactions_csv(OUTPUT_CSV_INTERACTIONS, raw_interactions, nudge_mapping)
    print(f"Wrote task interactions CSV to {OUTPUT_CSV_INTERACTIONS}")
    
    write_global_metrics_csv(OUTPUT_CSV_METADATA, participant_ids, usage)
    print(f"Wrote global metrics CSV to {OUTPUT_CSV_METADATA}")

    print(f"Wrote nudge counts CSV to {COUNTS_CSV_PATH}")

    write_nudge_comparison_csv(participant_ids, usage, nudge_mapping)
    print(f"Wrote nudge comparison CSV to {NUDGE_COMPARISON_CSV_PATH}")


if __name__ == "__main__":
    main()
