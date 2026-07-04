import argparse
import json
from pathlib import Path
from typing import Any


SERVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN_PATH = SERVER_DIR / "evals" / "codebasecoach.golden.json"


def evaluate_analysis_result(result: dict[str, Any], golden: dict[str, Any]) -> dict[str, Any]:
    result = _unwrap_result(result)
    documents = result.get("documents") if isinstance(result.get("documents"), list) else []
    evaluation = result.get("result_evaluation") if isinstance(result.get("result_evaluation"), dict) else {}
    document_text = "\n".join(str(document.get("content", "")) for document in documents if isinstance(document, dict))
    referenced_paths = _valid_referenced_paths(evaluation)

    failures: list[str] = []
    failures.extend(_missing_terms("expected_files", golden.get("expected_files", []), document_text, referenced_paths))
    failures.extend(_missing_terms("expected_tech_stack", golden.get("expected_tech_stack", []), document_text, referenced_paths))
    failures.extend(_missing_terms("expected_modules", golden.get("expected_modules", []), document_text, referenced_paths))
    failures.extend(_threshold_failures(evaluation, golden))

    return {
        "passed": not failures,
        "failures": failures,
        "document_count": len(documents),
        "scores": {
            "textcitation_score": _number(evaluation, "textcitation_score"),
            "coverage_score": _number(evaluation, "coverage_score"),
            "hallucination_risk": _number(evaluation, "hallucination_risk"),
            "usefulness_score": _number(evaluation, "usefulness_score"),
            "interview_question_count": _number(evaluation, "interview_question_count"),
        },
    }


def format_eval_report(report: dict[str, Any]) -> str:
    lines = [
        f"passed: {str(report['passed']).lower()}",
        f"document_count: {report['document_count']}",
    ]
    for key, value in report["scores"].items():
        lines.append(f"{key}: {value}")
    failures = report.get("failures", [])
    if failures:
        lines.append("failures:")
        lines.extend(f"  - {failure}" for failure in failures)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate generated analysis result against golden expectations.")
    parser.add_argument("--result", type=Path, required=True, help="JSON file containing AnalyzeRepoResponse or job_completed.result.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH, help=f"Golden expectation JSON. Default: {DEFAULT_GOLDEN_PATH}")
    parser.add_argument("--json", action="store_true", help="Print raw JSON report.")
    args = parser.parse_args()

    result = _read_json(args.result)
    golden = _read_json(args.golden)
    report = evaluate_analysis_result(result, golden)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_eval_report(report))
    return 0 if report["passed"] else 1


def _unwrap_result(value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value.get("result"), dict):
        return value["result"]
    if isinstance(value.get("payload"), dict) and isinstance(value["payload"].get("result"), dict):
        return value["payload"]["result"]
    return value


def _valid_referenced_paths(evaluation: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for item in evaluation.get("document_evaluations", []):
        if not isinstance(item, dict):
            continue
        for path in item.get("valid_referenced_file_paths", []):
            if isinstance(path, str):
                paths.add(path)
    return paths


def _missing_terms(
    category: str,
    terms: Any,
    document_text: str,
    referenced_paths: set[str],
) -> list[str]:
    if not isinstance(terms, list):
        return []
    failures: list[str] = []
    normalized_text = document_text.lower()
    for term in terms:
        if not isinstance(term, str):
            continue
        if term in referenced_paths or term.lower() in normalized_text:
            continue
        failures.append(f"{category}: missing {term}")
    return failures


def _threshold_failures(evaluation: dict[str, Any], golden: dict[str, Any]) -> list[str]:
    checks = [
        ("min_textcitation_score", "textcitation_score", "at least"),
        ("min_coverage_score", "coverage_score", "at least"),
        ("min_usefulness_score", "usefulness_score", "at least"),
        ("min_interview_question_count", "interview_question_count", "at least"),
    ]
    failures: list[str] = []
    for golden_key, score_key, label in checks:
        expected = golden.get(golden_key)
        if isinstance(expected, int | float) and _number(evaluation, score_key) < expected:
            failures.append(f"{score_key}: expected {label} {expected}, got {_number(evaluation, score_key)}")

    max_risk = golden.get("max_hallucination_risk")
    if isinstance(max_risk, int | float) and _number(evaluation, "hallucination_risk") > max_risk:
        failures.append(f"hallucination_risk: expected at most {max_risk}, got {_number(evaluation, 'hallucination_risk')}")
    return failures


def _number(value: dict[str, Any], key: str) -> int | float:
    item = value.get(key)
    return item if isinstance(item, int | float) else 0


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
