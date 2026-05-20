#!/usr/bin/env python3
"""
Print Prolific IDs from complete_submissions.txt that have data in both
code_snapshots.csv and tool_usage.csv.

Assumptions:
- A participant has "complete data" if their participant_id appears at least
  once in both code_snapshots.csv and tool_usage.csv.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Set


# Base directory containing the files.
BASE_DIR = Path("/Users/mgsakr/Desktop/work/Fard Lab/Analysis")


def load_complete_prolific_ids(path: Path) -> List[str]:
    """Return Prolific IDs listed in complete_submissions.txt (skip header line)."""
    prolific_ids: List[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            clean = line.strip()
            if not clean or clean.lower().startswith("found"):
                continue
            prolific_ids.append(clean)
    return prolific_ids


def load_prolific_to_participant(path: Path) -> Dict[str, str]:
    """Map prolific_pid -> participant_id from participants.csv."""
    mapping: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            prolific = (row.get("prolific_pid") or "").strip()
            participant = (row.get("participant_id") or "").strip()
            if prolific and participant:
                mapping[prolific] = participant
                counts[prolific] = counts.get(prolific, 0) + 1
    return mapping, counts


def load_participant_ids(path: Path, participant_field: str = "participant_id") -> Set[str]:
    """Collect participant_ids present in a CSV file."""
    ids: Set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            participant = (row.get(participant_field) or "").strip()
            if participant:
                ids.add(participant)
    return ids


def load_participant_counts(path: Path, participant_field: str = "participant_id") -> Dict[str, int]:
    """Count how many rows each participant_id has in a CSV file."""
    counts: Dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            participant = (row.get(participant_field) or "").strip()
            if participant:
                counts[participant] = counts.get(participant, 0) + 1
    return counts


def intersect_ordered(
    prolific_ids: Iterable[str],
    mapping: Dict[str, str],
    code_ids: Set[str],
    usage_ids: Set[str],
) -> List[str]:
    """Return prolific IDs whose participant_id is in both code_ids and usage_ids, preserving order."""
    result: List[str] = []
    for prolific in prolific_ids:
        participant = mapping.get(prolific)
        if participant and participant in code_ids and participant in usage_ids:
            result.append(prolific)
    return result


def main() -> None:
    # Prefer the copy in outputs if present; otherwise fall back to root.
    complete_path = BASE_DIR / "outputs" / "complete_submissions.txt"
    if not complete_path.exists():
        complete_path = BASE_DIR / "complete_submissions.txt"
    participants_path = BASE_DIR / "Tool_CSV" / "participants.csv"
    code_snapshots_path = BASE_DIR / "Tool_CSV" / "code_snapshots.csv"
    tool_usage_path = BASE_DIR / "Tool_CSV" / "tool_usage.csv"
    output_path = BASE_DIR / "outputs" / "prolific_ids_with_counts.txt"

    prolific_complete = load_complete_prolific_ids(complete_path)
    prolific_to_participant, prolific_counts = load_prolific_to_participant(participants_path)

    code_participants = load_participant_ids(code_snapshots_path)
    usage_participants = load_participant_ids(tool_usage_path)

    code_counts = load_participant_counts(code_snapshots_path)
    usage_counts = load_participant_counts(tool_usage_path)

    matching = intersect_ordered(
        prolific_complete, prolific_to_participant, code_participants, usage_participants
    )

    lines = []
    lines.append("Prolific IDs with data in both code_snapshots.csv and tool_usage.csv:")
    for pid in matching:
        participant_id = prolific_to_participant.get(pid)
        lines.append(
            f"{pid} | participant_id={participant_id} | "
            f"code_snapshots={code_counts.get(participant_id, 0)} | "
            f"tool_usage={usage_counts.get(participant_id, 0)}"
        )
    lines.append(f"\nTotal matched prolific IDs: {len(matching)}")

    duplicates = [pid for pid, count in prolific_counts.items() if count > 1]
    lines.append("\nPotential duplicate survey submissions (prolific_pid appearing more than once):")
    if duplicates:
        for pid in duplicates:
            lines.append(
                f"{pid} | occurrences={prolific_counts[pid]} | participant_id={prolific_to_participant.get(pid)}"
            )
    else:
        lines.append("None found.")

    csv_rows = []
    for pid in matching:
        participant_id = prolific_to_participant.get(pid, "")
        csv_rows.append(
            {
                "section": "match",
                "prolific_id": pid,
                "participant_id": participant_id,
                "code_snapshots": code_counts.get(participant_id, 0),
                "tool_usage": usage_counts.get(participant_id, 0),
                "occurrences": "",
            }
        )
    for pid in duplicates:
        csv_rows.append(
            {
                "section": "duplicate",
                "prolific_id": pid,
                "participant_id": prolific_to_participant.get(pid, ""),
                "code_snapshots": "",
                "tool_usage": "",
                "occurrences": prolific_counts.get(pid, 0),
            }
        )

    csv_output_path = output_path.with_suffix(".csv")
    fieldnames = [
        "section",
        "prolific_id",
        "participant_id",
        "code_snapshots",
        "tool_usage",
        "occurrences",
    ]
    with csv_output_path.open("w", encoding="utf-8", newline="") as csv_fh:
        writer = csv.DictWriter(csv_fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)

    # Print to console.
    for line in lines:
        print(line)

    # Write to outputs file.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
