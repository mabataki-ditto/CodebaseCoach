import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.query_metrics import collect_jobs, format_jobs


class QueryMetricsScriptTests(unittest.TestCase):
    def test_collect_jobs_reads_metrics_and_llm_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "metrics.db"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    create table analysis_jobs (
                        id text primary key,
                        repo_url text not null,
                        status text not null,
                        created_at text not null,
                        completed_at text,
                        metrics_json text
                    )
                    """
                )
                connection.execute(
                    """
                    create table llm_calls (
                        job_id text not null,
                        provider text not null,
                        model text not null,
                        prompt_type text not null,
                        duration_ms integer not null,
                        status text not null,
                        input_tokens integer,
                        output_tokens integer,
                        total_tokens integer,
                        created_at text not null
                    )
                    """
                )
                connection.execute(
                    """
                    insert into analysis_jobs
                    (id, repo_url, status, created_at, completed_at, metrics_json)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "job-1",
                        "https://github.com/owner/repo",
                        "success",
                        "2026-07-02T00:00:00+00:00",
                        "2026-07-02T00:01:00+00:00",
                        json.dumps(
                            {
                                "llm_input_tokens": 12,
                                "llm_output_tokens": 8,
                                "llm_total_tokens": 20,
                                "llm_call_count": 1,
                                "total_files": 100,
                                "ignored_dirs": 5,
                                "selected_core_files": 12,
                                "final_context_chars": 34567,
                                "context_compression_ratio": 0.42,
                                "generated_doc_count": 7,
                                "interview_question_count": 9,
                                "agent_step_count": 3,
                                "tool_call_count": 4,
                                "analysis_duration_ms": 12345,
                            }
                        ),
                    ),
                )
                connection.execute(
                    """
                    insert into llm_calls
                    (job_id, provider, model, prompt_type, duration_ms, status, input_tokens, output_tokens, total_tokens, created_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "job-1",
                        "openai",
                        "gpt-test",
                        "overview",
                        123,
                        "success",
                        12,
                        8,
                        20,
                        "2026-07-02T00:00:10+00:00",
                    ),
                )
                connection.commit()

            jobs = collect_jobs(db_path, job_id="job-1", limit=5, include_calls=True)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["metrics"]["llm_total_tokens"], 20)
        self.assertEqual(jobs[0]["llm_calls"][0]["prompt_type"], "overview")
        self.assertEqual(jobs[0]["llm_calls"][0]["total_tokens"], 20)

    def test_format_jobs_outputs_token_summary(self) -> None:
        output = format_jobs(
            [
                {
                    "id": "job-1",
                    "repo_url": "https://github.com/owner/repo",
                    "status": "success",
                    "created_at": "2026-07-02T00:00:00+00:00",
                    "completed_at": "2026-07-02T00:01:00+00:00",
                    "metrics": {
                        "llm_input_tokens": 12,
                        "llm_output_tokens": 8,
                        "llm_total_tokens": 20,
                        "llm_call_count": 1,
                        "total_files": 100,
                        "ignored_dirs": 5,
                        "selected_core_files": 12,
                        "final_context_chars": 34567,
                        "context_compression_ratio": 0.42,
                        "generated_doc_count": 7,
                        "interview_question_count": 9,
                        "agent_step_count": 3,
                        "tool_call_count": 4,
                        "analysis_duration_ms": 12345,
                    },
                    "llm_calls": [],
                }
            ]
        )

        self.assertIn("job-1", output)
        self.assertIn("llm_total_tokens: 20", output)
        self.assertIn("llm_input_tokens: 12", output)
        self.assertIn("total_files: 100", output)
        self.assertIn("ignored_dirs: 5", output)
        self.assertIn("selected_core_files: 12", output)
        self.assertIn("final_context_chars: 34567", output)
        self.assertIn("context_compression_ratio: 0.42", output)
        self.assertIn("generated_doc_count: 7", output)
        self.assertIn("interview_question_count: 9", output)
        self.assertIn("tool_call_count: 4", output)
        self.assertIn("analysis_duration_ms: 12345", output)


if __name__ == "__main__":
    unittest.main()
