import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


SERVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = (SERVER_DIR / "../../data/codebasecoach.db").resolve()


def collect_jobs(db_path: Path, *, job_id: str | None, limit: int, include_calls: bool) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = _fetch_job_rows(connection, job_id=job_id, limit=limit)
        jobs = [_job_from_row(row) for row in rows]
        if include_calls:
            for job in jobs:
                job["llm_calls"] = _fetch_llm_calls(connection, job["id"])
        else:
            for job in jobs:
                job["llm_calls"] = []
        return jobs


def format_jobs(jobs: list[dict[str, Any]]) -> str:
    if not jobs:
        return "No analysis jobs found."

    blocks: list[str] = []
    for job in jobs:
        metrics = job["metrics"]
        lines = [
            f"job_id: {job['id']}",
            f"repo_url: {job['repo_url']}",
            f"status: {job['status']}",
            f"created_at: {job['created_at']}",
            f"completed_at: {job['completed_at'] or '-'}",
            f"total_files: {_metric(metrics, 'total_files')}",
            f"ignored_dirs: {_metric(metrics, 'ignored_dirs')}",
            f"selected_core_files: {_metric(metrics, 'selected_core_files')}",
            f"final_context_chars: {_metric(metrics, 'final_context_chars')}",
            f"context_compression_ratio: {_metric(metrics, 'context_compression_ratio')}",
            f"generated_doc_count: {_metric(metrics, 'generated_doc_count')}",
            f"interview_question_count: {_metric(metrics, 'interview_question_count')}",
            f"agent_step_count: {_metric(metrics, 'agent_step_count')}",
            f"tool_call_count: {_metric(metrics, 'tool_call_count')}",
            f"analysis_duration_ms: {_metric(metrics, 'analysis_duration_ms')}",
            f"llm_call_count: {_metric(metrics, 'llm_call_count')}",
            f"llm_input_tokens: {_metric(metrics, 'llm_input_tokens')}",
            f"llm_output_tokens: {_metric(metrics, 'llm_output_tokens')}",
            f"llm_total_tokens: {_metric(metrics, 'llm_total_tokens')}",
        ]
        calls = job.get("llm_calls", [])
        if calls:
            lines.append("llm_calls:")
            for call in calls:
                lines.append(
                    "  "
                    f"{call['prompt_type']} | {call['status']} | "
                    f"input={call['input_tokens'] or 0}, "
                    f"output={call['output_tokens'] or 0}, "
                    f"total={call['total_tokens'] or 0}, "
                    f"duration_ms={call['duration_ms']}, "
                    f"model={call['provider']}/{call['model']}"
                )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Query CodebaseCoach analysis metrics from SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help=f"SQLite DB path. Default: {DEFAULT_DB_PATH}")
    parser.add_argument("--job-id", help="Query one analysis job by id.")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent jobs to show when --job-id is omitted.")
    parser.add_argument("--calls", action="store_true", help="Show per-LLM-call token details.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON.")
    args = parser.parse_args()

    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    jobs = collect_jobs(db_path, job_id=args.job_id, limit=max(args.limit, 1), include_calls=args.calls)
    if args.json:
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
    else:
        print(format_jobs(jobs))
    return 0


def _fetch_job_rows(connection: sqlite3.Connection, *, job_id: str | None, limit: int) -> list[sqlite3.Row]:
    if job_id:
        return list(
            connection.execute(
                """
                select id, repo_url, status, created_at, completed_at, metrics_json
                from analysis_jobs
                where id = ?
                """,
                (job_id,),
            )
        )
    return list(
        connection.execute(
            """
            select id, repo_url, status, created_at, completed_at, metrics_json
            from analysis_jobs
            order by created_at desc
            limit ?
            """,
            (limit,),
        )
    )


def _fetch_llm_calls(connection: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select provider, model, prompt_type, duration_ms, status, input_tokens, output_tokens, total_tokens, created_at
        from llm_calls
        where job_id = ?
        order by created_at
        """,
        (job_id,),
    )
    return [dict(row) for row in rows]


def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "repo_url": row["repo_url"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "metrics": _parse_metrics(row["metrics_json"]),
    }


def _parse_metrics(raw_metrics: str | bytes | None) -> dict[str, Any]:
    if not raw_metrics:
        return {}
    try:
        value = json.loads(raw_metrics)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _metric(metrics: dict[str, Any], key: str) -> int | float:
    value = metrics.get(key)
    return value if isinstance(value, int | float) else 0


if __name__ == "__main__":
    raise SystemExit(main())
