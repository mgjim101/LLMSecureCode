#!/usr/bin/env python3
"""
Compute time from nudge (eventid=1) to task completion (eventid=3 or 4) for
participants listed in outputs/prolific_ids_with_counts.txt using
Tool_CSV/code_snapshots.csv.

For each participant/task pair that has at least one nudge and one completion
event, we take the earliest nudge and the earliest completion event (3 or 4)
that occurs at or after that nudge. Results are written to
outputs/nudge_to_completion_durations.txt with a per-participant breakdown and
summary statistics printed to stdout.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Dict, Iterable, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
PROLIFIC_PATH = BASE_DIR / "outputs" / "prolific_ids_with_counts.txt"
SNAPSHOTS_PATH = BASE_DIR / "Tool_CSV" / "code_snapshots.csv"
OUTPUT_PATH = BASE_DIR / "outputs" / "nudge_to_completion_durations.txt"
PARTICIPANTS_CSV = BASE_DIR / "Tool_CSV" / "participants.csv"
AVG_CSV_PATH = SCRIPT_DIR / "nudge_to_completion_avg_by_task_nudge.csv"


def parse_timestamp(raw: str) -> Optional[datetime]:
    """Return datetime from ISO-like string; None if parsing fails."""
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


def load_nudge_mapping(path: Path) -> Dict[int, str]:
    """Build participant_id -> nudge type ('A' or 'B') from participants.csv."""
    mapping: Dict[int, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pid_raw = (row.get("participant_id") or "").strip()
            gid_raw = (row.get("group_id") or "").strip()
            if not pid_raw.isdigit() or not gid_raw.isdigit():
                continue
            pid = int(pid_raw)
            gid = int(gid_raw)
            mapping[pid] = "A" if 1 <= gid <= 6 else "B"
    return mapping


def collect_nudge_completion_events(
    path: Path, target_ids: Iterable[int]
) -> Dict[Tuple[int, str], Dict[str, List[Tuple[Optional[datetime], str]]]]:
    """
    Collect nudge (event 1) and completion (event 3 or 4) timestamps.

    Returns mapping of (participant_id, taskid) -> {"nudge": [...], "completion": [...]}.
    Each list item is a tuple of (datetime|None, eventid).
    """
    target_set = set(target_ids)
    events: Dict[Tuple[int, str], Dict[str, List[Tuple[Optional[datetime], str]]]] = {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pid_raw = (row.get("participant_id") or "").strip()
            if not pid_raw.isdigit():
                continue
            pid = int(pid_raw)
            if pid not in target_set:
                continue

            eventid = (row.get("eventid") or "").strip()
            if eventid not in {"1", "3", "4"}:
                continue

            taskid = (row.get("taskid") or "").strip()
            ts = parse_timestamp((row.get("timestamp") or "").strip())

            bucket = events.setdefault((pid, taskid), {"nudge": [], "completion": []})
            if eventid == "1":
                bucket["nudge"].append((ts, eventid))
            else:
                bucket["completion"].append((ts, eventid))

    return events


def select_completion_after_nudge(
    nudges: List[Tuple[Optional[datetime], str]],
    completions: List[Tuple[Optional[datetime], str]],
) -> Optional[Tuple[datetime, str, timedelta]]:
    """Pick earliest nudge and earliest completion at/after that nudge."""
    nudges_sorted = sorted([ts for ts, _ in nudges if ts is not None])
    completions_sorted = sorted([(ts, ev) for ts, ev in completions if ts is not None])

    if not nudges_sorted or not completions_sorted:
        return None

    first_nudge = nudges_sorted[0]
    for comp_ts, comp_event in completions_sorted:
        if comp_ts >= first_nudge:
            duration = comp_ts - first_nudge
            return first_nudge, comp_event, duration

    # No completion after the first nudge; skip pairing
    return None


def build_results(
    events: Dict[Tuple[int, str], Dict[str, List[Tuple[Optional[datetime], str]]]],
    participant_ids: List[int],
    nudge_by_participant: Dict[int, str],
):
    """Compute per-participant durations and track missing data."""
    per_participant: Dict[int, Dict[str, List[Dict[str, object]]]] = {
        pid: {"durations": [], "missing": []} for pid in participant_ids
    }
    durations_seconds: List[float] = []

    for (pid, taskid), parts in events.items():
        nudges = parts.get("nudge", [])
        completions = parts.get("completion", [])

        if not nudges or not completions:
            per_participant.setdefault(pid, {"durations": [], "missing": []})["missing"].append(
                {
                    "taskid": taskid,
                    "reason": "no nudge" if not nudges else "no completion (event 3/4)",
                }
            )
            continue

        selection = select_completion_after_nudge(nudges, completions)
        if not selection:
            per_participant.setdefault(pid, {"durations": [], "missing": []})["missing"].append(
                {
                    "taskid": taskid,
                    "reason": "no completion timestamp after nudge",
                }
            )
            continue

        nudge_ts, completion_event, duration = selection
        duration_sec = duration.total_seconds()
        durations_seconds.append(duration_sec)
        per_participant.setdefault(pid, {"durations": [], "missing": []})["durations"].append(
            {
                "nudge": nudge_by_participant.get(pid, ""),
                "taskid": taskid,
                "nudge_ts": nudge_ts,
                "completion_event": completion_event,
                "completion_after": nudge_ts + duration,
                "duration_sec": duration_sec,
            }
        )

    return per_participant, durations_seconds


def format_timedelta(seconds: float) -> str:
    """Return a human-friendly hh:mm:ss string for a duration in seconds."""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_output(
    participant_ids: List[int],
    per_participant: Dict[int, Dict[str, List[Dict[str, object]]]],
    durations_seconds: List[float],
) -> List[str]:
    """Build report lines for output file."""
    lines: List[str] = []
    lines.append("Nudge to completion durations (eventid 1 -> eventid 3 or 4)")
    lines.append(f"Participants in scope: {len(participant_ids)} (from prolific_ids_with_counts.txt)")
    lines.append("Rule: take earliest nudge (event 1) and earliest completion (event 3/4) at or after that nudge.")
    lines.append("")

    for pid in participant_ids:
        buckets = per_participant.get(pid, {"durations": [], "missing": []})
        durations = buckets.get("durations", [])
        missing = buckets.get("missing", [])

        lines.append(f"Participant {pid}")
        lines.append(f"  Tasks with duration: {len(durations)}")
        if durations:
            lines.append("  Task details:")

            def sort_key(entry: Dict[str, object]):
                try:
                    return int(entry["taskid"])  # type: ignore[arg-type]
                except Exception:
                    return entry["taskid"]  # type: ignore[return-value]

            for entry in sorted(durations, key=sort_key):
                dur_str = format_timedelta(entry["duration_sec"])  # type: ignore[arg-type]
                lines.append(
                    f"    - taskid={entry['taskid']}: "
                    f"nudge={entry['nudge_ts']}, completion(event {entry['completion_event']})={entry['completion_after']}, "
                    f"duration={dur_str} ({entry['duration_sec']:.2f} seconds)"
                )
        else:
            lines.append("  Task details: none (no matched nudge & completion)")

        if missing:
            lines.append("  Missing pairs:")
            for item in sorted(missing, key=lambda x: x["taskid"]):
                lines.append(f"    - taskid={item['taskid']}: {item['reason']}")

        lines.append("")  # spacer

    lines.append("Summary")
    total_pairs = len(durations_seconds)
    lines.append(f"  Matched task pairs: {total_pairs}")
    if total_pairs:
        lines.append(f"  Mean duration: {format_timedelta(mean(durations_seconds))} ({mean(durations_seconds):.2f} seconds)")
        lines.append(f"  Median duration: {format_timedelta(median(durations_seconds))} ({median(durations_seconds):.2f} seconds)")
        lines.append(f"  Min duration: {format_timedelta(min(durations_seconds))} ({min(durations_seconds):.2f} seconds)")
        lines.append(f"  Max duration: {format_timedelta(max(durations_seconds))} ({max(durations_seconds):.2f} seconds)")
    else:
        lines.append("  No matched nudge->completion pairs found.")

    return lines


def write_csv(
    per_participant: Dict[int, Dict[str, List[Dict[str, object]]]],
    csv_path: Path,
) -> None:
    """Dump matched durations to a simple CSV schema."""
    fieldnames = [
        "participant_id",
        "nudge",
        "taskid",
        "nudge_event",
        "nudge_timestamp",
        "completion_event",
        "completion_timestamp",
        "duration_seconds",
        "duration_hh_mm_ss",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for participant_id in sorted(per_participant):
            durations = per_participant[participant_id].get("durations", [])
            for entry in durations:
                writer.writerow(
                    {
                        "participant_id": participant_id,
                        "nudge": entry["nudge"],
                        "taskid": entry["taskid"],
                        "nudge_event": 1,
                        "nudge_timestamp": entry["nudge_ts"].isoformat()
                        if entry["nudge_ts"]
                        else "",
                        "completion_event": entry["completion_event"],
                        "completion_timestamp": entry["completion_after"].isoformat()
                        if entry["completion_after"]
                        else "",
                        "duration_seconds": f"{entry['duration_sec']:.2f}",
                        "duration_hh_mm_ss": format_timedelta(entry["duration_sec"]),  # type: ignore[arg-type]
                    }
                )


def write_avg_csv_by_task_nudge(
    per_participant: Dict[int, Dict[str, List[Dict[str, object]]]],
    csv_path: Path,
) -> None:
    """Write average duration by task (1/2/3) and nudge (A/B)."""
    durations: Dict[Tuple[str, str], List[float]] = {}

    for participant_data in per_participant.values():
        for entry in participant_data.get("durations", []):
            taskid = str(entry.get("taskid", "")).strip()
            nudge = str(entry.get("nudge", "")).strip()
            duration_sec = float(entry.get("duration_sec", 0.0))
            if not taskid or nudge not in {"A", "B"}:
                continue
            durations.setdefault((taskid, nudge), []).append(duration_sec)

    fieldnames = [
        "taskid",
        "nudge",
        "average_duration_seconds",
        "average_duration_hh_mm_ss",
        "sample_size",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for taskid in ("1", "2", "3"):
            for nudge in ("A", "B"):
                values = durations.get((taskid, nudge), [])
                avg_seconds = mean(values) if values else None
                writer.writerow(
                    {
                        "taskid": taskid,
                        "nudge": nudge,
                        "average_duration_seconds": (
                            f"{avg_seconds:.2f}" if avg_seconds is not None else ""
                        ),
                        "average_duration_hh_mm_ss": (
                            format_timedelta(avg_seconds)
                            if avg_seconds is not None
                            else ""
                        ),
                        "sample_size": len(values),
                    }
                )


def print_summary(durations_seconds: List[float]) -> None:
    """Print a brief console summary."""
    total = len(durations_seconds)
    print(f"Matched nudge->completion pairs: {total}")
    if not total:
        print("No durations to summarize.")
        return

    print(f"  Mean: {mean(durations_seconds):.2f} sec")
    print(f"  Median: {median(durations_seconds):.2f} sec")
    print(f"  Min: {min(durations_seconds):.2f} sec")
    print(f"  Max: {max(durations_seconds):.2f} sec")


def main() -> None:
    participant_ids = load_participant_ids(PROLIFIC_PATH)
    nudge_by_participant = load_nudge_mapping(PARTICIPANTS_CSV)
    events = collect_nudge_completion_events(SNAPSHOTS_PATH, participant_ids)
    per_participant, durations_seconds = build_results(
        events,
        participant_ids,
        nudge_by_participant,
    )

    report_lines = format_output(participant_ids, per_participant, durations_seconds)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    csv_path = OUTPUT_PATH.with_suffix(".csv")
    write_csv(per_participant, csv_path)
    write_avg_csv_by_task_nudge(per_participant, AVG_CSV_PATH)
    print(
        f"Wrote nudge-to-completion durations to {OUTPUT_PATH} and {csv_path}"
    )
    print(f"Wrote task x nudge average CSV to {AVG_CSV_PATH}")
    print_summary(durations_seconds)


if __name__ == "__main__":
    main()
