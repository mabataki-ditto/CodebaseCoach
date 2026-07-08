"""Run 10 repo analyses and collect metrics."""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "http://localhost:8000"
REPOS = [
    "https://github.com/sindresorhus/awesome",
    "https://github.com/axios/axios",
    "https://github.com/pallets/flask",
    "https://github.com/vuejs/pinia",
    "https://github.com/prettier/prettier",
    "https://github.com/tiangolo/sqlmodel",
    "https://github.com/fastify/fastify",
    "https://github.com/pytest-dev/pytest",
    "https://github.com/python-poetry/poetry",
    "https://github.com/expressjs/express",
]

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = []

for repo_url in REPOS:
    owner_repo = repo_url.replace("https://github.com/", "")
    print(f"\n=== Analyzing: {owner_repo} ===", flush=True)

    body = json.dumps({"repo_url": repo_url}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/agent/analyze",
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
            "generated_doc_total_chars": metrics.get("generated_doc_total_chars", 0),
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
            "compression_ratio_q": quality.get("compression_ratio", 0),
            "wall_clock_ms": elapsed_ms,
        }

        ratio_pct = round(result["context_compression_ratio"] * 100, 1)
        print(f"  OK | dur={result['analysis_duration_ms']}ms | steps={result['agent_step_count']} | "
              f"tools={result['tool_call_count']} | files={result['total_files']} | "
              f"core={result['selected_core_files']} | compress={ratio_pct}%", flush=True)

    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        result = {"repo": owner_repo, "status": "failed", "error": str(e)}

    results.append(result)

# Save all results
out_path = OUTPUT_DIR / "benchmark_results.json"
out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nResults saved to {out_path}", flush=True)

# Compute averages
successful = [r for r in results if r["status"] == "success"]
failed = [r for r in results if r["status"] != "success"]

print(f"\n{'='*50}")
print(f"Total: {len(results)} | Success: {len(successful)} | Failed: {len(failed)}")
print(f"{'='*50}")

if successful:
    def avg(key):
        vals = [r[key] for r in successful]
        return sum(vals) / len(vals)

    print(f"\n=== AVERAGES (n={len(successful)}) ===")
    print(f"  analysis_duration_ms       : {avg('analysis_duration_ms'):.0f}")
    print(f"  agent_step_count           : {avg('agent_step_count'):.1f}")
    print(f"  tool_call_count            : {avg('tool_call_count'):.1f}")
    print(f"  context_compression_ratio  : {avg('context_compression_ratio') * 100:.1f}%")
    print(f"  total_files                : {avg('total_files'):.0f}")
    print(f"  selected_core_files        : {avg('selected_core_files'):.1f}")
    print(f"  interview_question_count   : {avg('interview_question_count'):.1f}")
    print(f"  llm_call_count             : {avg('llm_call_count'):.1f}")
    print(f"  textcitation_score         : {avg('textcitation_score') * 100:.1f}%")
    print(f"  coverage_score             : {avg('coverage_score') * 100:.1f}%")
    print(f"  hallucination_risk         : {avg('hallucination_risk') * 100:.1f}%")
    print(f"  usefulness_score           : {avg('usefulness_score') * 100:.1f}%")
    print(f"  wall_clock_ms              : {avg('wall_clock_ms'):.0f}")

if failed:
    print(f"\n=== FAILED ===")
    for r in failed:
        print(f"  {r['repo']}: {r.get('error', 'unknown')}")

print("\nDone.", flush=True)