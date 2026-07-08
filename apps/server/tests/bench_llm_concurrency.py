"""LLM 并发调用基准测试：用 metrics.jsonl 真实数据模拟延迟，对比串行 vs 并发耗时。"""
import json
import time
from pathlib import Path
from app.agent.prompts import DocumentPrompt
from app.services.llm_service import generate_markdown_documents
import app.services.llm_service as llm_service

# ---- 从 metrics.jsonl 提取真实 LLM 单次调用平均耗时 ----
metrics_path = Path("../../data/metrics.jsonl")
records = []
with open(metrics_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

real = [
    r for r in records
    if r.get("used_mock_ai") == False
    and r.get("status") == "success"
    and r.get("llm_total_duration_ms", 0) > 0
    and r.get("llm_call_count", 0) == 7
]
single_durations = [r["llm_total_duration_ms"] / r["llm_call_count"] for r in real]
avg_single_ms = sum(single_durations) / len(single_durations)
avg_single_s = avg_single_ms / 1000

output = []
output.append(f"=== 真实数据统计 ===")
output.append(f"有效记录数: {len(real)}")
output.append(f"LLM 总调用次数: {sum(r['llm_call_count'] for r in real)}")
output.append(f"LLM 总耗时: {sum(r['llm_total_duration_ms'] for r in real) / 1000:.1f}s")
output.append(f"平均单次 LLM 调用: {avg_single_ms:.0f}ms ({avg_single_s:.1f}s)")
output.append(f"范围: {min(single_durations):.0f}ms - {max(single_durations):.0f}ms")
output.append("")

# ---- 用真实平均延迟跑基准测试 ----
DOC_COUNT = 7
prompts = [
    DocumentPrompt(title=f"文档{i}", filename=f"{i:02d}.md", instruction=f"prompt{i}")
    for i in range(1, DOC_COUNT + 1)
]

original = llm_service._generate_single_document
call_times = []


def fake_generate(*, client, prompt, context, model, api_key):
    t0 = time.perf_counter()
    time.sleep(avg_single_s)
    call_times.append(time.perf_counter() - t0)
    return (f"content of {prompt}", (100, 50, 150), int(avg_single_s * 1000))


llm_service._generate_single_document = fake_generate

class _FakeOpenAI:
    def __call__(self, **kwargs):
        return None

llm_service.OpenAI = _FakeOpenAI()

try:
    t0 = time.perf_counter()
    result = generate_markdown_documents(
        document_prompts=prompts,
        context="test context",
        api_key="test-key",
        model="test-model",
    )
    elapsed = time.perf_counter() - t0
finally:
    llm_service._generate_single_document = original
    llm_service.OpenAI = None

serial_estimate = DOC_COUNT * avg_single_s
speedup = serial_estimate / elapsed

output.append(f"=== 并发基准测试 ===")
output.append(f"文档数: {DOC_COUNT}")
output.append(f"模拟单次延迟: {avg_single_ms:.0f}ms (基于真实数据)")
output.append(f"并发总耗时: {elapsed:.1f}s")
output.append(f"串行预估耗时: {serial_estimate:.1f}s")
output.append(f"加速比: {speedup:.1f}x")
output.append(f"各线程耗时: {[f'{t:.1f}s' for t in call_times]}")
output.append(f"生成文档数: {len(result)}")
assert len(result) == DOC_COUNT, "文档数不匹配!"
assert speedup > 1.5, f"加速比 {speedup:.1f}x 低于预期 1.5x"
output.append("测试通过!")

# 写入文件
result_text = "\n".join(output)
with open("tests/bench_result.txt", "w", encoding="utf-8") as f:
    f.write(result_text)
print(result_text)