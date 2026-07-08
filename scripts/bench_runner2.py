"""Batch benchmark - run 10 repos, save results incrementally."""
import json, time, sys, traceback
from pathlib import Path
import requests

BASE_URL = "http://localhost:8000"
# Smaller repos for faster runs
REPOS = [
    "https://github.com/sindresorhus/awesome",
    "https://github.com/axios/axios",
    "https://github.com/pallets/flask",
    "https://github.com/vuejs/pinia",
    "https://github.com/tiangolo/sqlmodel",
    "https://github.com/fastify/fastify",
    "https://github.com/pytest-dev/pytest",
    "https://github.com/python-poetry/poetry",
    "https://github.com/expressjs/express",
    "https://github.com/prettier/prettier",
]

OUTPUT_DIR = Path("../../data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "bench_log.txt"

def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

results = []

for i, repo_url in enumerate(REPOS):
    owner_repo = repo_url.replace("https://github.com/", "")
    safe_name = owner_repo.replace("/", "_")
    out_path = OUTPUT_DIR / f"bench_{safe_name}.json"
    
    log(f"\n[{i+1}/10] {owner_repo}")
    
    try:
        started = time.time()
        resp = requests.post(
            f"{BASE_URL}/api/agent/analyze",
            json={"repo_url": repo_url},
            timeout=300,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        
        if resp.status_code != 200:
            err = resp.text[:500]
            result = {"repo": owner_repo, "status": "failed", "error": f"HTTP {resp.status_code}: {err}"}
            log(f"  FAIL: HTTP {resp.status_code}")
        else:
            data = resp.json()
            metrics = data.get("metrics", {})
            eval_data = data.get("result_evaluation", {})
            
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
            ratio_pct = round(result["context_compression_ratio"] * 100, 1)
            log(f"  OK | dur={result['analysis_duration_ms']}ms | steps={result['agent_step_count']} | "
                f"tools={result['tool_call_count']} | files={result['total_files']} | "
                f"core={result['selected_core_files']} | compress={ratio_pct}%")
        
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        
    except Exception as e:
        result = {"repo": owner_repo, "status": "failed", "error": str(e)}
        log(f"  FAIL: {e}")
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    
    results.append(result)

# Compute averages
successful = [r for r in results if r["status"] == "success"]
failed = [r for r in results if r["status"] != "success"]

log(f"\n{'='*60}")
log(f"SUMMARY: Total={len(results)} | Success={len(successful)} | Failed={len(failed)}")
log(f"{'='*60}")

if successful:
    def avg(key):
        vals = [r[key] for r in successful]
        return sum(vals) / len(vals)
    
    log(f"\n=== AVERAGES (n={len(successful)}) ===")
    log(f"  analysis_duration_ms       : {avg('analysis_duration_ms'):.0f}")
    log(f"  agent_step_count           : {avg('agent_step_count'):.1f}")
    log(f"  tool_call_count            : {avg('tool_call_count'):.1f}")
    log(f"  context_compression_ratio  : {avg('context_compression_ratio') * 100:.1f}%")
    log(f"  total_files                : {avg('total_files'):.0f}")
    log(f"  selected_core_files        : {avg('selected_core_files'):.1f}")
    log(f"  interview_question_count   : {avg('interview_question_count'):.1f}")
    log(f"  llm_call_count             : {avg('llm_call_count'):.1f}")
    log(f"  textcitation_score         : {avg('textcitation_score') * 100:.1f}%")
    log(f"  coverage_score             : {avg('coverage_score') * 100:.1f}%")
    log(f"  hallucination_risk         : {avg('hallucination_risk') * 100:.1f}%")
    log(f"  usefulness_score           : {avg('usefulness_score') * 100:.1f}%")

# Save all results
all_path = OUTPUT_DIR / "benchmark_results.json"
all_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
log(f"\nAll results saved to {all_path}")
log("Done.")