"""Run one repo analysis, save metrics to file."""
import json, sys, time
from pathlib import Path
import urllib.request

REPO_URL = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/axios/axios"
owner_repo = REPO_URL.replace("https://github.com/", "")
safe_name = owner_repo.replace("/", "_")
OUTPUT = Path(f"../../data/bench_{safe_name}.json")

body = json.dumps({"repo_url": REPO_URL}).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8000/api/agent/analyze",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

started = time.time()
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed_ms = int((time.time() - started) * 1000)
    metrics = data.get("metrics", {})
    eval_data = data.get("result_evaluation", {})
    quality = data.get("context_quality_report", {})

    result = {
        "repo": owner_repo,
        "status": "success",
        "total_files": metrics.get("total_files", 0),
        "ignored_dirs": metrics.get("ignored_dirs", 0),
        "candidate_core_files": metrics.get("candidate_core_files", 0),
        "selected_core_files": metrics.get("selected_core_files", 0),
        "raw_candidate_chars": metrics.get("raw_candidate_chars", 0),
        "final_context_chars": metrics.get("final_context_chars", 0),
        "context_compression_ratio": metrics.get("context_compression_ratio", 0),
        "generated_doc_count": metrics.get("generated_doc_count", 0),
        "interview_question_count": metrics.get("interview_question_count", 0),
        "agent_step_count": metrics.get("agent_step_count", 0),
        "agent_success_step_count": metrics.get("agent_success_step_count", 0),
        "agent_failed_step_count": metrics.get("agent_failed_step_count", 0),
        "agent_skipped_step_count": metrics.get("agent_skipped_step_count", 0),
        "tool_call_count": metrics.get("tool_call_count", 0),
        "tool_success_count": metrics.get("tool_success_count", 0),
        "tool_failed_count": metrics.get("tool_failed_count", 0),
        "analysis_duration_ms": metrics.get("analysis_duration_ms", 0),
        "llm_call_count": metrics.get("llm_call_count", 0),
        "llm_success_count": metrics.get("llm_success_count", 0),
        "llm_total_duration_ms": metrics.get("llm_total_duration_ms", 0),
        "textcitation_score": eval_data.get("textcitation_score", 0),
        "coverage_score": eval_data.get("coverage_score", 0),
        "hallucination_risk": eval_data.get("hallucination_risk", 0),
        "usefulness_score": eval_data.get("usefulness_score", 0),
        "wall_clock_ms": elapsed_ms,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK:{owner_repo}|dur={metrics['analysis_duration_ms']}|steps={metrics['agent_step_count']}|tools={metrics['tool_call_count']}|compress={metrics['context_compression_ratio']*100:.1f}%", flush=True)
except Exception as e:
    result = {"repo": owner_repo, "status": "failed", "error": str(e)}
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"FAIL:{owner_repo}|{e}", flush=True)