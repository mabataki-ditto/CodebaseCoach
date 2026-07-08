"""Loop: restart server, run one repo, collect result, repeat."""
import json, time, subprocess, signal, sys
from pathlib import Path
import requests

BASE_URL = "http://localhost:8000"
SERVER_DIR = Path(".")
OUTPUT_DIR = Path("../../data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Skip repos we already have
REPOS = [
    # "https://github.com/sindresorhus/awesome",  # already done
    # "https://github.com/axios/axios",            # already done
    "https://github.com/pallets/flask",
    "https://github.com/vuejs/pinia",
    "https://github.com/tiangolo/sqlmodel",
    "https://github.com/fastify/fastify",
    "https://github.com/pytest-dev/pytest",
    "https://github.com/python-poetry/poetry",
    "https://github.com/expressjs/express",
    "https://github.com/prettier/prettier",
]

def start_server():
    """Start uvicorn server, wait for it to be ready."""
    # Kill any existing server on port 8000
    try:
        subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq *uvicorn*"], 
                       capture_output=True, timeout=5)
    except:
        pass
    time.sleep(1)
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(SERVER_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    # Wait for server to be ready
    for i in range(30):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                print(f"  Server ready (pid={proc.pid})", flush=True)
                return proc
        except:
            pass
        time.sleep(1)
    
    proc.kill()
    raise RuntimeError("Server failed to start")

def stop_server(proc):
    """Stop the server gracefully."""
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except:
        try:
            proc.kill()
        except:
            pass

def run_analysis(repo_url):
    """Run a single analysis, return result dict."""
    resp = requests.post(
        f"{BASE_URL}/api/agent/analyze",
        json={"repo_url": repo_url},
        timeout=300,
    )
    if resp.status_code != 200:
        return {"status": "failed", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    
    data = resp.json()
    metrics = data.get("metrics", {})
    eval_data = data.get("result_evaluation", {})
    
    return {
        "repo": repo_url.replace("https://github.com/", ""),
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
        "tool_call_count": metrics.get("tool_call_count", 0),
        "analysis_duration_ms": metrics.get("analysis_duration_ms", 0),
        "llm_call_count": metrics.get("llm_call_count", 0),
        "llm_success_count": metrics.get("llm_success_count", 0),
        "llm_total_duration_ms": metrics.get("llm_total_duration_ms", 0),
        "textcitation_score": eval_data.get("textcitation_score", 0),
        "coverage_score": eval_data.get("coverage_score", 0),
        "hallucination_risk": eval_data.get("hallucination_risk", 0),
        "usefulness_score": eval_data.get("usefulness_score", 0),
    }

results = []

for i, repo_url in enumerate(REPOS):
    owner_repo = repo_url.replace("https://github.com/", "")
    safe_name = owner_repo.replace("/", "_")
    out_path = OUTPUT_DIR / f"bench_{safe_name}.json"
    
    print(f"\n[{i+1}/8] {owner_repo}", flush=True)
    
    server = None
    try:
        server = start_server()
        
        started = time.time()
        result = run_analysis(repo_url)
        elapsed = int((time.time() - started) * 1000)
        result["wall_clock_ms"] = elapsed
        
        if result["status"] == "success":
            ratio = round(result["context_compression_ratio"] * 100, 1)
            print(f"  OK | dur={result['analysis_duration_ms']}ms | steps={result['agent_step_count']} | "
                  f"tools={result['tool_call_count']} | files={result['total_files']} | "
                  f"core={result['selected_core_files']} | compress={ratio}%", flush=True)
        else:
            print(f"  FAIL: {result['error']}", flush=True)
        
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(result)
        
    except Exception as e:
        result = {"repo": owner_repo, "status": "failed", "error": str(e)}
        print(f"  FAIL: {e}", flush=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(result)
    finally:
        if server:
            stop_server(server)
        time.sleep(2)

# Load previous results and combine
print(f"\n{'='*60}", flush=True)
all_results = []

# Load awesome
aw = OUTPUT_DIR / "bench_sindresorhus_awesome.json"
if aw.exists():
    all_results.append(json.loads(aw.read_text(encoding="utf-8")))

# Load axios
ax = OUTPUT_DIR / "bench_axios_axios.json"
if ax.exists():
    all_results.append(json.loads(ax.read_text(encoding="utf-8")))

all_results.extend(results)

successful = [r for r in all_results if r["status"] == "success"]
failed = [r for r in all_results if r["status"] != "success"]

print(f"Total: {len(all_results)} | Success: {len(successful)} | Failed: {len(failed)}", flush=True)

if successful:
    def avg(key):
        return sum(r[key] for r in successful) / len(successful)
    
    print(f"\n=== AVERAGES (n={len(successful)}) ===", flush=True)
    print(f"  analysis_duration_ms       : {avg('analysis_duration_ms'):.0f}", flush=True)
    print(f"  agent_step_count           : {avg('agent_step_count'):.1f}", flush=True)
    print(f"  tool_call_count            : {avg('tool_call_count'):.1f}", flush=True)
    print(f"  context_compression_ratio  : {avg('context_compression_ratio') * 100:.1f}%", flush=True)
    print(f"  total_files                : {avg('total_files'):.0f}", flush=True)
    print(f"  selected_core_files        : {avg('selected_core_files'):.1f}", flush=True)
    print(f"  interview_question_count   : {avg('interview_question_count'):.1f}", flush=True)
    print(f"  llm_call_count             : {avg('llm_call_count'):.1f}", flush=True)
    print(f"  textcitation_score         : {avg('textcitation_score') * 100:.1f}%", flush=True)
    print(f"  coverage_score             : {avg('coverage_score') * 100:.1f}%", flush=True)
    print(f"  hallucination_risk         : {avg('hallucination_risk') * 100:.1f}%", flush=True)
    print(f"  usefulness_score           : {avg('usefulness_score') * 100:.1f}%", flush=True)

# Save combined
all_path = OUTPUT_DIR / "benchmark_all.json"
all_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nAll results saved to {all_path}", flush=True)

if failed:
    print(f"\n=== FAILED ===", flush=True)
    for r in failed:
        print(f"  {r['repo']}: {r.get('error', 'unknown')}", flush=True)

print("\nDone.", flush=True)