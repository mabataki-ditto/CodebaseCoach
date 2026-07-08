"""Test a single analysis and dump full response."""
import json
import sys
import traceback
import urllib.request
from pathlib import Path

REPO_URL = "https://github.com/axios/axios"
OUTPUT = Path("data/test_one_result.json")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

body = json.dumps({"repo_url": REPO_URL}).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8000/api/agent/analyze",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

print(f"Requesting analysis for {REPO_URL}...", flush=True)
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    OUTPUT.write_text(raw, encoding="utf-8")
    print(f"Success! Response saved to {OUTPUT}", flush=True)
    print(f"Has metrics: {'metrics' in data}", flush=True)
    if "metrics" in data:
        m = data["metrics"]
        print(f"  steps={m.get('agent_step_count')}, tools={m.get('tool_call_count')}, "
              f"duration={m.get('analysis_duration_ms')}ms, compress={m.get('context_compression_ratio', 0)*100:.1f}%", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
    # Try to read error response
    if hasattr(e, 'read'):
        try:
            err_body = e.read().decode("utf-8")
            print(f"Error body: {err_body[:500]}", flush=True)
        except:
            pass
    sys.exit(1)