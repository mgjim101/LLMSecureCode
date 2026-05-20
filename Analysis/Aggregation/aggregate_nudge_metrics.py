#!/usr/bin/env python3
"""Aggregate nudge A/B metrics from multiple CSV sources into one schema."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, Tuple


NUDGES = ("A", "B")
TASKS = (1, 2, 3)


def read_indexed_csv(
    path: Path,
    *,
    key_fields: Tuple[str, str],
    value_fields: Iterable[str],
) -> Dict[Tuple[str, int], Dict[str, str]]:
    """Read CSV rows indexed by (nudge, task_id/taskid)."""
    result: Dict[Tuple[str, int], Dict[str, str]] = {}

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nudge = (row.get(key_fields[0]) or "").strip()
            task_raw = (row.get(key_fields[1]) or "").strip()
            if not nudge or not task_raw:
                continue
            try:
                task_id = int(task_raw)
            except ValueError:
                continue
            key = (nudge, task_id)
            result[key] = {field: (row.get(field) or "").strip() for field in value_fields}
    return result


def get_value(
    table: Dict[Tuple[str, int], Dict[str, str]],
    nudge: str,
    task_id: int,
    field: str,
    default: str = "0",
) -> str:
    return table.get((nudge, task_id), {}).get(field, default) or default


def build_output_headers() -> list[str]:
    headers = ["Nudge"]
    for task_id in TASKS:
        prefix = f"Task {task_id}"
        headers.extend(
            [
                f"{prefix} used tool count",
                f"{prefix} skipped tool count",
                f"{prefix} changes after tool used",
                f"{prefix} changes after tool not used",
                f"{prefix} unchanged after tool used",
                f"{prefix} unchanged after tool not used",
                f"{prefix} total issue count tool used",
                f"{prefix} total issue count tool not used",
                f"{prefix} total high severity issues tool used",
                f"{prefix} total high severity issues tool not used",
                f"{prefix} total low severity issues tool used",
                f"{prefix} total low severity issues tool not used",
                f"{prefix} total medium severity issues tool used",
                f"{prefix} total medium severity issues tool not used",
                f"{prefix} total diff high severity issues tool used",
                f"{prefix} total diff high severity issues tool not used",
                f"{prefix} total diff medium severity issues tool used",
                f"{prefix} total diff medium severity issues tool not used",
                f"{prefix} total diff low severity issues tool used",
                f"{prefix} total diff low severity issues tool not used",
                f"{prefix} average duration from nudge to completion (hh_mm_ss)",
            ]
        )
    return headers


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate nudge-level metrics for tasks 1-3 into a single CSV with two rows (A and B)."
        )
    )
    parser.add_argument(
        "--root-dir",
        default=".",
        help="Root directory containing the source folders (default: current directory).",
    )
    parser.add_argument(
        "--output",
        default="nudge_aggregated_summary.csv",
        help="Output CSV path (default: nudge_aggregated_summary.csv).",
    )
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    output_path = Path(args.output).resolve()

    tool_usage = read_indexed_csv(
        root / "tool_usage" / "tool_usage_nudge_counts.csv",
        key_fields=("nudge", "task_id"),
        value_fields=("used_count", "skipped_count"),
    )
    changes_with_tool = read_indexed_csv(
        root / "code_changes_with_tool" / "code_changes_after_tool_nudge_counts.csv",
        key_fields=("nudge", "task_id"),
        value_fields=("changed_count", "unchanged_count"),
    )
    changes_without_tool = read_indexed_csv(
        root / "code_changes_without_tool" / "code_changes_after_nudge_nudge_counts.csv",
        key_fields=("nudge", "task_id"),
        value_fields=("changed_count", "unchanged_count"),
    )
    issues_without_tool = read_indexed_csv(
        root / "bandit_comparison_without_tool" / "bandit_comparison_nudge_nudge_counts.csv",
        key_fields=("nudge", "task_id"),
        value_fields=(
            "total_issue_count",
            "total_high_severity",
            "total_low_severity",
            "total_medium_severity",
        ),
    )
    issues_with_tool = read_indexed_csv(
        root / "bandit_comparison_with_tool" / "bandit_comparison_nudge_counts.csv",
        key_fields=("nudge", "task_id"),
        value_fields=(
            "total_issue_count",
            "total_high_severity",
            "total_low_severity",
            "total_medium_severity",
        ),
    )
    diffs_with_tool = read_indexed_csv(
        root / "bandit_comparison_with_tool" / "bandit_comparison_nudge_task_total_diffs.csv",
        key_fields=("nudge", "task_id"),
        value_fields=("total_diff_high_severity", "total_diff_medium_severity", "total_diff_low_severity"),
    )
    diffs_without_tool = read_indexed_csv(
        root / "bandit_comparison_without_tool" / "bandit_comparison_nudge_nudge_task_total_diffs.csv",
        key_fields=("nudge", "task_id"),
        value_fields=("total_diff_high_severity", "total_diff_medium_severity", "total_diff_low_severity"),
    )
    durations = read_indexed_csv(
        root / "nudge_to_completion_duration" / "nudge_to_completion_avg_by_task_nudge.csv",
        key_fields=("nudge", "taskid"),
        value_fields=("average_duration_hh_mm_ss",),
    )

    headers = build_output_headers()
    rows: list[dict[str, str]] = []

    for nudge in NUDGES:
        row: dict[str, str] = {"Nudge": nudge}
        for task_id in TASKS:
            prefix = f"Task {task_id}"
            row[f"{prefix} used tool count"] = get_value(tool_usage, nudge, task_id, "used_count")
            row[f"{prefix} skipped tool count"] = get_value(tool_usage, nudge, task_id, "skipped_count")
            row[f"{prefix} changes after tool used"] = get_value(
                changes_with_tool, nudge, task_id, "changed_count"
            )
            row[f"{prefix} changes after tool not used"] = get_value(
                changes_without_tool, nudge, task_id, "changed_count"
            )
            row[f"{prefix} unchanged after tool used"] = get_value(
                changes_with_tool, nudge, task_id, "unchanged_count"
            )
            row[f"{prefix} unchanged after tool not used"] = get_value(
                changes_without_tool, nudge, task_id, "unchanged_count"
            )
            row[f"{prefix} total issue count tool used"] = get_value(
                issues_with_tool, nudge, task_id, "total_issue_count"
            )
            row[f"{prefix} total issue count tool not used"] = get_value(
                issues_without_tool, nudge, task_id, "total_issue_count"
            )
            row[f"{prefix} total high severity issues tool used"] = get_value(
                issues_with_tool, nudge, task_id, "total_high_severity"
            )
            row[f"{prefix} total high severity issues tool not used"] = get_value(
                issues_without_tool, nudge, task_id, "total_high_severity"
            )
            row[f"{prefix} total low severity issues tool used"] = get_value(
                issues_with_tool, nudge, task_id, "total_low_severity"
            )
            row[f"{prefix} total low severity issues tool not used"] = get_value(
                issues_without_tool, nudge, task_id, "total_low_severity"
            )
            row[f"{prefix} total medium severity issues tool used"] = get_value(
                issues_with_tool, nudge, task_id, "total_medium_severity"
            )
            row[f"{prefix} total medium severity issues tool not used"] = get_value(
                issues_without_tool, nudge, task_id, "total_medium_severity"
            )
            row[f"{prefix} total diff high severity issues tool used"] = get_value(
                diffs_with_tool, nudge, task_id, "total_diff_high_severity"
            )
            row[f"{prefix} total diff high severity issues tool not used"] = get_value(
                diffs_without_tool, nudge, task_id, "total_diff_high_severity"
            )
            row[f"{prefix} total diff medium severity issues tool used"] = get_value(
                diffs_with_tool, nudge, task_id, "total_diff_medium_severity"
            )
            row[f"{prefix} total diff medium severity issues tool not used"] = get_value(
                diffs_without_tool, nudge, task_id, "total_diff_medium_severity"
            )
            row[f"{prefix} total diff low severity issues tool used"] = get_value(
                diffs_with_tool, nudge, task_id, "total_diff_low_severity"
            )
            row[f"{prefix} total diff low severity issues tool not used"] = get_value(
                diffs_without_tool, nudge, task_id, "total_diff_low_severity"
            )
            row[f"{prefix} average duration from nudge to completion (hh_mm_ss)"] = get_value(
                durations, nudge, task_id, "average_duration_hh_mm_ss", default=""
            )
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
