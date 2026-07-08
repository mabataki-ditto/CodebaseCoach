import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_DIR.parents[1]
sys.path.insert(0, str(SERVER_DIR))

from scripts.eval_generated_result import DEFAULT_GOLDEN_PATH, evaluate_analysis_result  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "prompt-evals"
SCORES = (
    "textcitation_score",
    "coverage_score",
    "hallucination_risk",
    "usefulness_score",
    "interview_question_count",
)


def build_report(
    *,
    baseline_result: dict[str, Any] | None,
    current_result: dict[str, Any],
    golden: dict[str, Any],
    baseline_path: Path,
    current_path: Path,
    baseline_created: bool,
) -> dict[str, Any]:
    current_eval = evaluate_analysis_result(current_result, golden)
    baseline_eval = evaluate_analysis_result(baseline_result, golden) if baseline_result else None

    return {
        "baseline_created": baseline_created,
        "baseline_path": str(baseline_path),
        "current_path": str(current_path),
        "golden_passed": current_eval["passed"],
        "current_eval": current_eval,
        "baseline_eval": baseline_eval,
        "score_changes": _score_changes(
            baseline_eval["scores"] if baseline_eval else None,
            current_eval["scores"],
        ),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"baseline_created: {str(report['baseline_created']).lower()}",
        f"golden_passed: {str(report['golden_passed']).lower()}",
        f"baseline_path: {report['baseline_path']}",
        f"current_path: {report['current_path']}",
    ]

    current_eval = report["current_eval"]
    lines.append("")
    lines.append("current scores:")
    for key, value in current_eval["scores"].items():
        lines.append(f"  {key}: {value}")

    if report["score_changes"]:
        lines.append("")
        lines.append("score changes:")
        for change in report["score_changes"]:
            suffix = f", {change['direction']}" if change["direction"] else ""
            lines.append(
                f"  {change['name']}: {change['before']} -> {change['after']} ({_format_delta(change['delta'])}{suffix})"
            )

    failures = current_eval.get("failures", [])
    if failures:
        lines.append("")
        lines.append("failures:")
        lines.extend(f"  - {failure}" for failure in failures)

    return "\n".join(lines)


def result_paths(output_dir: Path, repo_url: str, timestamp: datetime) -> tuple[Path, Path]:
    slug = _repo_slug(repo_url)
    stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    baseline_path = output_dir / "baselines" / f"{slug}.json"
    current_path = output_dir / "runs" / f"{slug}_{stamp}.json"
    return baseline_path, current_path


def analyze_repo(base_url: str, repo_url: str, timeout: int) -> dict[str, Any]:
    api_url = f"{base_url.rstrip('/')}/api/agent/analyze"
    body = json.dumps({"repo_url": repo_url}).encode("utf-8")
    request = Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Analyze request failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Analyze request failed: {exc.reason}") from exc

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit("Analyze response was not valid JSON.") from exc
    if not isinstance(value, dict):
        raise SystemExit("Analyze response JSON root must be an object.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run prompt regression eval against a real analysis result.")
    parser.add_argument("--repo-url", required=True, help="Repository URL to analyze.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH, help="Golden expectation JSON.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for baseline and run JSON files.")
    parser.add_argument("--timeout", type=int, default=600, help="Analyze request timeout in seconds.")
    parser.add_argument("--refresh-baseline", action="store_true", help="Replace the stored baseline with the current result.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON report.")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    baseline_path, current_path = result_paths(output_dir, args.repo_url, datetime.now(UTC))
    golden = _read_json(args.golden)
    previous_baseline = None if args.refresh_baseline else _read_optional_json(baseline_path)

    current_result = analyze_repo(args.base_url, args.repo_url, args.timeout)
    _write_json(current_path, current_result)

    baseline_created = previous_baseline is None or args.refresh_baseline
    if baseline_created:
        _write_json(baseline_path, current_result)
        baseline_result = None
    else:
        baseline_result = previous_baseline

    report = build_report(
        baseline_result=baseline_result,
        current_result=current_result,
        golden=golden,
        baseline_path=baseline_path,
        current_path=current_path,
        baseline_created=baseline_created,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report["golden_passed"] else 1


def _score_changes(
    before_scores: dict[str, Any] | None,
    after_scores: dict[str, Any],
) -> list[dict[str, Any]]:
    if before_scores is None:
        return []

    changes: list[dict[str, Any]] = []
    for name in SCORES:
        before = _number(before_scores, name)
        after = _number(after_scores, name)
        delta = round(after - before, 4)
        changes.append(
            {
                "name": name,
                "before": before,
                "after": after,
                "delta": delta,
                "direction": _direction(name, delta),
            }
        )
    return changes


def _direction(name: str, delta: int | float) -> str:
    if delta == 0:
        return "unchanged"
    if name == "hallucination_risk":
        return "worse" if delta > 0 else "better"
    return "better" if delta > 0 else "worse"


def _repo_slug(repo_url: str) -> str:
    value = repo_url.removesuffix(".git").rstrip("/")
    parts = [part for part in value.split("/") if part]
    if len(parts) >= 2:
        raw = f"{parts[-2]}_{parts[-1]}"
    else:
        raw = value
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_") or "repo"


def _format_delta(value: int | float) -> str:
    return f"+{value}" if value > 0 else str(value)


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


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
