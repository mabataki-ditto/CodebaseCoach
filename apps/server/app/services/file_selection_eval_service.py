from typing import Any


TOP_K = 12


def evaluate_file_selection(
    *,
    selected_paths: list[str],
    expected_entry_paths: list[str],
    expected_core_paths: list[str],
) -> dict[str, Any]:
    selected_files = selected_paths[:TOP_K]
    selected_set = set(selected_files)
    matched_entry_files = [path for path in expected_entry_paths if path in selected_set]
    matched_core_files = [path for path in expected_core_paths if path in selected_set]

    return {
        "selected_files": selected_files,
        "entry_recall": _recall(matched_entry_files, expected_entry_paths),
        "core_recall_at_12": _recall(matched_core_files, expected_core_paths),
        "matched_entry_files": matched_entry_files,
        "missed_entry_files": [path for path in expected_entry_paths if path not in selected_set],
        "matched_core_files": matched_core_files,
        "missed_core_files": [path for path in expected_core_paths if path not in selected_set],
    }


def aggregate_file_selection_reports(reports: list[dict[str, Any]]) -> dict[str, int | float]:
    count = len(reports)
    if count == 0:
        return {
            "repository_count": 0,
            "average_entry_recall": 0.0,
            "average_core_recall_at_12": 0.0,
        }

    return {
        "repository_count": count,
        "average_entry_recall": sum(report["entry_recall"] for report in reports) / count,
        "average_core_recall_at_12": sum(report["core_recall_at_12"] for report in reports) / count,
    }


def _recall(matched_paths: list[str], expected_paths: list[str]) -> float:
    return len(matched_paths) / len(expected_paths) if expected_paths else 0.0
