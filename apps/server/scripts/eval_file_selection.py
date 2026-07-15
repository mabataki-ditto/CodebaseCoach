import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.file_selection_eval_service import aggregate_file_selection_reports, evaluate_file_selection
from app.services.file_selector_service import select_core_files
from app.services.github_service import clone_repository
from app.services.repo_parser import parse_github_repo_url


SERVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN_PATH = SERVER_DIR / "evals" / "file-selection.golden.json"
DEFAULT_REPORT_DIR = SERVER_DIR / "evals"


def run_file_selection_eval(golden: dict[str, Any]) -> dict[str, Any]:
    repository_reports: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="codebasecoach-file-selection-") as temp_dir:
        temp_root = Path(temp_dir)
        for repository in golden["repositories"]:
            repo_url = repository["repo_url"]
            repo_root = clone_repository(parse_github_repo_url(repo_url), temp_root)
            selected_paths = [file.path for file in select_core_files(repo_root, max_files=12, max_bytes=12_000)]
            report = evaluate_file_selection(
                selected_paths=selected_paths,
                expected_entry_paths=_expected_paths(repository["expected_entry_files"]),
                expected_core_paths=_expected_paths(repository["expected_core_files"]),
            )
            repository_reports.append({"repo_url": repo_url, **report})

    return {
        "repositories": repository_reports,
        "summary": aggregate_file_selection_reports(repository_reports),
    }


def format_file_selection_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    for repository in report["repositories"]:
        lines.extend(
            [
                repository["repo_url"],
                f"  Entry Recall: {repository['entry_recall']:.2%}",
                f"  Core Recall@12: {repository['core_recall_at_12']:.2%}",
                f"  Missed entry files: {', '.join(repository['missed_entry_files']) or '-'}",
                f"  Missed core files: {', '.join(repository['missed_core_files']) or '-'}",
            ]
        )

    summary = report["summary"]
    lines.extend(
        [
            "Macro average",
            f"  Entry Recall: {summary['average_entry_recall']:.2%}",
            f"  Core Recall@12: {summary['average_core_recall_at_12']:.2%}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate core-file selection on GitHub repositories.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--output", type=Path, help="Path for the JSON report. Must not already exist.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args()

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    report = run_file_selection_eval(golden)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    output_path = args.output or DEFAULT_REPORT_DIR / (
        f"file-selection.report-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as report_file:
        report_file.write(report_json + "\n")

    print(report_json if args.json else format_file_selection_report(report))
    return 0


def _expected_paths(items: list[dict[str, str]]) -> list[str]:
    return [item["path"] for item in items]


if __name__ == "__main__":
    raise SystemExit(main())
