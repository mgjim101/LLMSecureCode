#!/usr/bin/env python3
"""
Generate one-row-per-participant profiles using the requested schema.

Input IDs come from:
  data_cleanup/prolific_ids_with_counts.csv

Output:
  data_cleanup/participant_profiles_schema.csv
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_IDS_CSV = BASE_DIR / "data_cleanup" / "prolific_ids_with_counts.csv"
TOOL_USAGE_PARTICIPANT_CSV = BASE_DIR / "tool_usage" / "tool_usage_participant_summary.csv"
TOOL_USAGE_TASK_CSV = BASE_DIR / "tool_usage" / "tool_usage_task_interactions.csv"
CODE_CHANGES_TOOL_CSV = BASE_DIR / "code_changes_with_tool" / "code_changes_after_tool_tasks.csv"
CODE_CHANGES_NO_TOOL_CSV = BASE_DIR / "code_changes_without_tool" / "code_changes_after_nudge_tasks.csv"
COMPLETION_CSV = BASE_DIR / "nudge_to_completion_duration" / "nudge_to_completion_durations.csv"
BANDIT_TOOL_SUBMISSIONS_CSV = (
    BASE_DIR / "bandit_comparison_with_tool" / "bandit_comparison_participant_submissions.csv"
)
BANDIT_NO_TOOL_SUBMISSIONS_CSV = (
    BASE_DIR / "bandit_comparison_without_tool" / "bandit_comparison_nudge_participant_submissions.csv"
)
BANDIT_TOOL_TYPES_CSV = (
    BASE_DIR / "bandit_comparison_with_tool" / "bandit_comparison_type_changes.csv"
)
BANDIT_NO_TOOL_TYPES_CSV = (
    BASE_DIR / "bandit_comparison_without_tool" / "bandit_comparison_nudge_type_changes.csv"
)
SURVEY_CSV = BASE_DIR / "Aggregation" / "results-survey641369.csv"

OUTPUT_CSV = BASE_DIR / "Aggregation" / "participant_profiles_schema.csv"
TASK_IDS = (1, 2, 3)
SURVEY_PROLIFIC_ID_INDEX = 7


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def norm(value: Optional[str]) -> str:
    return (value or "").strip()


def parse_bool(value: Optional[str]) -> bool:
    lowered = norm(value).lower()
    return lowered in {"true", "1", "yes", "y", "used"}


def to_int_str(value: Optional[str], default: str = "") -> str:
    txt = norm(value)
    if txt == "":
        return default
    try:
        return str(int(float(txt)))
    except ValueError:
        return txt


def sort_type_key(item: Dict[str, str]) -> Tuple[int, str]:
    type_id = norm(item.get("type_id"))
    if len(type_id) > 1 and type_id[0].upper() == "B" and type_id[1:].isdigit():
        return (int(type_id[1:]), type_id)
    return (10**9, type_id)


def join_ordered(rows: Iterable[Dict[str, str]], key: str) -> str:
    return ",".join(norm(r.get(key)) for r in rows if norm(r.get(key)))


def make_unique_headers(raw_headers: List[str]) -> List[str]:
    """
    Make headers unique while preserving original names as much as possible.
    Empty names become `unnamed_{index}`.
    """
    used: Dict[str, int] = {}
    out: List[str] = []
    for idx, header in enumerate(raw_headers):
        base = norm(header) or f"unnamed_{idx}"
        count = used.get(base, 0)
        if count == 0:
            unique = base
        else:
            unique = f"{base}__{count + 1}"
        used[base] = count + 1
        out.append(unique)
    return out


def get_task_source_maps(
    rows: List[Dict[str, str]],
) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in rows:
        pid = norm(row.get("participant_id"))
        task = norm(row.get("taskid") or row.get("task_id") or row.get("Task_ID"))
        if pid and task:
            out[(pid, task)] = row
    return out


def get_bandit_submission_map(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in rows:
        pid = norm(row.get("participant_id"))
        task = norm(row.get("task_id"))
        if pid and task:
            out[(pid, task)] = row
    return out


def get_type_changes_map(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], List[Dict[str, str]]]:
    out: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in rows:
        pid = norm(row.get("participant_id"))
        task = norm(row.get("task_id"))
        if not pid or not task:
            continue
        out.setdefault((pid, task), []).append(row)
    return out


def build_output_headers() -> List[str]:
    headers: List[str] = [
        "Prolific ID",
        "participant_id",
        "Nudge",
        "Number of tasks tool used",
        "Number of tasks tool not used",
    ]
    for task in TASK_IDS:
        headers.extend(
            [
                f"Task {task} tool use BOOL",
                f"Task {task} changed BOOL",
                f"Task {task} completion time DATE",
                f"Task {task} start_lines",
                f"Task {task} End_lines",
                f"Task {task} line_delta",
                f"Task {task} issue count",
                f"Task {task} high severity count",
                f"Task {task} med severity count",
                f"Task {task} low severity count",
                f"Task {task} high severity diff",
                f"Task {task} med severity diff",
                f"Task {task} low severity diff",
                f"Task {task} issue type ID",
                f"Task {task} issue type name",
                f"Task {task} issue change kind [fixed, common, new]",
            ]
        )
    return headers


def main() -> None:
    ids_rows = read_csv(INPUT_IDS_CSV)
    usage_rows = read_csv(TOOL_USAGE_PARTICIPANT_CSV)
    usage_task_rows = read_csv(TOOL_USAGE_TASK_CSV)
    code_tool_rows = read_csv(CODE_CHANGES_TOOL_CSV)
    code_no_tool_rows = read_csv(CODE_CHANGES_NO_TOOL_CSV)
    completion_rows = read_csv(COMPLETION_CSV)
    bandit_tool_sub_rows = read_csv(BANDIT_TOOL_SUBMISSIONS_CSV)
    bandit_no_tool_sub_rows = read_csv(BANDIT_NO_TOOL_SUBMISSIONS_CSV)
    bandit_tool_type_rows = read_csv(BANDIT_TOOL_TYPES_CSV)
    bandit_no_tool_type_rows = read_csv(BANDIT_NO_TOOL_TYPES_CSV)

    # Read survey with csv.reader to preserve all columns (including duplicate/blank headers).
    with SURVEY_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        survey_reader = csv.reader(fh)
        survey_raw_headers = next(survey_reader)
        survey_headers = make_unique_headers(survey_raw_headers)
        survey_rows_by_prolific: Dict[str, List[str]] = {}
        for raw_row in survey_reader:
            if len(raw_row) < len(survey_headers):
                raw_row = raw_row + [""] * (len(survey_headers) - len(raw_row))
            prolific_value = norm(
                raw_row[SURVEY_PROLIFIC_ID_INDEX] if len(raw_row) > SURVEY_PROLIFIC_ID_INDEX else ""
            )
            if prolific_value:
                non_empty = sum(1 for v in raw_row if norm(v))
                existing = survey_rows_by_prolific.get(prolific_value)
                if existing is None or non_empty > sum(1 for v in existing if norm(v)):
                    survey_rows_by_prolific[prolific_value] = raw_row

    # participant_id -> row
    usage_participant: Dict[str, Dict[str, str]] = {
        norm(r.get("Participant_ID")): r for r in usage_rows if norm(r.get("Participant_ID"))
    }

    # (participant_id, task_id) -> bool
    task_tool_use: Dict[Tuple[str, str], bool] = {}
    for row in usage_task_rows:
        pid = norm(row.get("Participant_ID"))
        task = norm(row.get("Task_ID"))
        action = norm(row.get("Action"))
        if pid and task:
            task_tool_use[(pid, task)] = action.lower() == "used"

    # task-level source maps
    code_tool_map = get_task_source_maps(code_tool_rows)
    code_no_tool_map = get_task_source_maps(code_no_tool_rows)
    completion_map = get_task_source_maps(completion_rows)
    bandit_tool_sub_map = get_bandit_submission_map(bandit_tool_sub_rows)
    bandit_no_tool_sub_map = get_bandit_submission_map(bandit_no_tool_sub_rows)
    bandit_tool_type_map = get_type_changes_map(bandit_tool_type_rows)
    bandit_no_tool_type_map = get_type_changes_map(bandit_no_tool_type_rows)

    headers = build_output_headers()
    headers.extend(survey_headers)
    output_rows: List[Dict[str, str]] = []

    for id_row in ids_rows:
        pid = norm(id_row.get("participant_id"))
        prolific_id = norm(id_row.get("prolific_id"))
        if not pid or not prolific_id:
            continue

        usage_row = usage_participant.get(pid, {})
        out: Dict[str, str] = {
            "Prolific ID": prolific_id,
            "participant_id": pid,
            "Nudge": norm(usage_row.get("nudge")),
            "Number of tasks tool used": to_int_str(usage_row.get("Total_Uses"), default="0"),
            "Number of tasks tool not used": to_int_str(usage_row.get("Total_Skips"), default="0"),
        }

        for task in TASK_IDS:
            task_s = str(task)
            key = (pid, task_s)
            used_tool = task_tool_use.get(key, False)

            selected_code_row = code_tool_map.get(key, {}) if used_tool else code_no_tool_map.get(key, {})
            selected_bandit_sub = (
                bandit_tool_sub_map.get(key, {}) if used_tool else bandit_no_tool_sub_map.get(key, {})
            )
            selected_type_rows = (
                bandit_tool_type_map.get(key, []) if used_tool else bandit_no_tool_type_map.get(key, [])
            )

            # Keep per-issue fields aligned by sorting all three lists by type_id.
            selected_type_rows = sorted(selected_type_rows, key=sort_type_key)

            changed = parse_bool(selected_code_row.get("changed"))
            completion_row = completion_map.get(key, {})
            completion_time = norm(completion_row.get("duration_hh_mm_ss")) if used_tool else ""

            out[f"Task {task} tool use BOOL"] = str(used_tool)
            out[f"Task {task} changed BOOL"] = str(changed)
            out[f"Task {task} completion time DATE"] = completion_time
            out[f"Task {task} start_lines"] = to_int_str(selected_code_row.get("start_lines"), default="")
            out[f"Task {task} End_lines"] = to_int_str(selected_code_row.get("end_lines"), default="")
            out[f"Task {task} line_delta"] = to_int_str(selected_code_row.get("line_delta"), default="")

            # Requested source for issue count is code-changes files, but those files do not expose issue_count.
            # Fallback to the matched bandit participant submissions to populate this field.
            issue_count_val = selected_code_row.get("issue_count")
            if norm(issue_count_val) == "":
                issue_count_val = selected_bandit_sub.get("issue_count")
            out[f"Task {task} issue count"] = to_int_str(issue_count_val, default="")

            out[f"Task {task} high severity count"] = to_int_str(
                selected_bandit_sub.get("high_severity"), default=""
            )
            out[f"Task {task} med severity count"] = to_int_str(
                selected_bandit_sub.get("medium_severity"), default=""
            )
            out[f"Task {task} low severity count"] = to_int_str(
                selected_bandit_sub.get("low_severity"), default=""
            )
            out[f"Task {task} high severity diff"] = to_int_str(
                selected_bandit_sub.get("severity_diff_high"), default=""
            )
            out[f"Task {task} med severity diff"] = to_int_str(
                selected_bandit_sub.get("severity_diff_medium"), default=""
            )
            out[f"Task {task} low severity diff"] = to_int_str(
                selected_bandit_sub.get("severity_diff_low"), default=""
            )

            out[f"Task {task} issue type ID"] = join_ordered(selected_type_rows, "type_id")
            out[f"Task {task} issue type name"] = join_ordered(selected_type_rows, "type_name")
            out[f"Task {task} issue change kind [fixed, common, new]"] = join_ordered(
                selected_type_rows, "change_kind"
            )

        survey_row = survey_rows_by_prolific.get(prolific_id)
        if survey_row:
            for idx, header in enumerate(survey_headers):
                out[header] = survey_row[idx] if idx < len(survey_row) else ""
        else:
            for header in survey_headers:
                out[header] = ""

        output_rows.append(out)

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} rows to {OUTPUT_CSV}")
    print(f"Columns: {len(headers)}")


if __name__ == "__main__":
    main()
