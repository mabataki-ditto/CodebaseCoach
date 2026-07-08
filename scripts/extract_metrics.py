"""Extract metrics from existing metrics.jsonl for 10 unique repos, compute averages."""
import json
from pathlib import Path
from datetime import datetime

METRICS_PATH = Path("../../data/metrics.jsonl")
OUTPUT = Path("../../data/benchmark_summary.json")

records = []
with open(METRICS_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

# Filter: only real (non-mock) successful runs, current version only (10 steps)
real = [r for r in records if r.get("used_mock_ai") == False and r.get("status") == "success" and r.get("agent_step_count", 0) >= 10]

print(f"Total records: {len(records)}")
print(f"Real (non-mock) successful: {len(real)}")

# Group by repo, take the first run
seen = {}
unique = []
for r in real:
    key = f"{r['owner']}/{r['repo']}"
    if key not in seen:
        seen[key] = r
        unique.append(r)

print(f"Unique repos: {len(unique)}")
print(f"Repos: {[f'{r['owner']}/{r['repo']}' for r in unique]}")

# Take first 10
subset = unique[:10]

results = []
for r in subset:
    duration = r.get("analysis_duration_ms", r.get("duration_ms", 0))
    total_files = r.get("total_files", 0)
    # total_files was added later; use candidate_core_files as fallback
    if total_files == 0:
        total_files = r.get("candidate_core_files", 0)
    result = {
        "repo": f"{r['owner']}/{r['repo']}",
        "started_at": r.get("started_at", ""),
        "total_files": total_files,
        "ignored_dirs": r.get("ignored_dirs", 0),
        "candidate_core_files": r.get("candidate_core_files", 0),
        "selected_core_files": r.get("selected_core_files", 0),
        "raw_candidate_chars": r.get("raw_candidate_chars", 0),
        "final_context_chars": r.get("final_context_chars", 0),
        "context_compression_ratio": r.get("context_compression_ratio", 0),
        "generated_doc_count": r.get("generated_doc_count", 0),
        "interview_question_count": r.get("interview_question_count", 0),
        "agent_step_count": r.get("agent_step_count", 0),
        "tool_call_count": r.get("tool_call_count", 0),
        "analysis_duration_ms": duration,
        "llm_call_count": r.get("llm_call_count", 0),
        "llm_total_duration_ms": r.get("llm_total_duration_ms", 0),
        "context_compression_pct": round(r.get("context_compression_ratio", 0) * 100, 1),
        "raw_context_kb": round(r.get("raw_candidate_chars", 0) / 1024, 1),
        "final_context_kb": round(r.get("final_context_chars", 0) / 1024, 1),
    }
    results.append(result)

print(f"\n{'='*80}")
print(f"{'Repo':<35} {'Files':>6} {'Core':>5} {'Steps':>6} {'Tools':>6} {'Dur(s)':>7} {'Compress':>8} {'Raw(KB)':>8} {'Final(KB)':>9} {'Interview':>9}")
print(f"{'-'*80}")

for r in results:
    dur_s = r["analysis_duration_ms"] / 1000
    print(f"{r['repo']:<35} {r['total_files']:>6} {r['selected_core_files']:>5} {r['agent_step_count']:>6} "
          f"{r['tool_call_count']:>6} {dur_s:>7.1f} {r['context_compression_pct']:>7.1f}% "
          f"{r['raw_context_kb']:>8.1f} {r['final_context_kb']:>9.1f} {r['interview_question_count']:>9}")

print(f"{'='*80}")

# Averages
n = len(results)
print(f"\n=== AVERAGES (n={n}) ===")
print(f"  analysis_duration_ms       : {sum(r['analysis_duration_ms'] for r in results) / n:.0f}")
print(f"  analysis_duration_s        : {sum(r['analysis_duration_ms'] for r in results) / n / 1000:.1f}")
print(f"  agent_step_count           : {sum(r['agent_step_count'] for r in results) / n:.1f}")
print(f"  tool_call_count            : {sum(r['tool_call_count'] for r in results) / n:.1f}")
print(f"  context_compression_ratio  : {sum(r['context_compression_ratio'] for r in results) / n * 100:.1f}%")
print(f"  total_files                : {sum(r['total_files'] for r in results) / n:.0f}")
print(f"  selected_core_files        : {sum(r['selected_core_files'] for r in results) / n:.1f}")
print(f"  interview_question_count   : {sum(r['interview_question_count'] for r in results) / n:.1f}")
print(f"  llm_call_count             : {sum(r['llm_call_count'] for r in results) / n:.1f}")
print(f"  raw_context_kb             : {sum(r['raw_context_kb'] for r in results) / n:.1f}")
print(f"  final_context_kb           : {sum(r['final_context_kb'] for r in results) / n:.1f}")

# Save
OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nSaved to {OUTPUT}")