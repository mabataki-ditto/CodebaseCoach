"""对比 metrics.jsonl 中串行 vs 并发的真实耗时。"""
import json
from pathlib import Path

metrics_path = Path("../../data/metrics.jsonl")
records = []
with open(metrics_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

# 过滤：real runs
real = [
    r for r in records
    if r.get("used_mock_ai") == False
    and r.get("status") == "success"
    and r.get("llm_call_count", 0) == 7
]

# 分组：scikit-learn 是并发数据，其他是串行
sklearn = [r for r in real if r.get("repo") == "scikit-learn"]
other = [r for r in real if r.get("repo") != "scikit-learn"]

# 串行数据要求 llm_total_duration_ms > 0
serial = [r for r in other if r.get("llm_total_duration_ms", 0) > 0]

print(f"=== 真实数据统计 ===\n")
print(f"串行有效记录(llm_total_duration_ms > 0): {len(serial)}")
print(f"scikit-learn 并发记录: {len(sklearn)}")
print(f"其他 repo 串行记录: {len(other)}\n")

if serial:
    avg_serial_llm = sum(r["llm_total_duration_ms"] for r in serial) / len(serial)
    avg_serial_total = sum(r["analysis_duration_ms"] for r in serial) / len(serial)
    avg_single = avg_serial_llm / 7
    print(f"=== 串行（{len(serial)} 个样本）===")
    print(f"  平均 llm_total_duration_ms: {avg_serial_llm:.0f}ms = {avg_serial_llm/1000:.1f}s")
    print(f"  平均单次 LLM 调用: {avg_single:.0f}ms = {avg_single/1000:.1f}s")
    print(f"  平均分析总耗时: {avg_serial_total:.0f}ms = {avg_serial_total/1000:.1f}s\n")

if len(sklearn) >= 1:
    sklearn_sorted = sorted(sklearn, key=lambda r: r["started_at"])
    for i, r in enumerate(sklearn_sorted):
        version = "串行" if i == 0 else "并发"
        print(f"=== {version} - scikit-learn ===")
        print(f"  started_at: {r['started_at']}")
        print(f"  llm_call_count: {r['llm_call_count']}")
        print(f"  llm_total_duration_ms: {r['llm_total_duration_ms']} = {r['llm_total_duration_ms']/1000:.1f}s")
        print(f"  analysis_duration_ms: {r['analysis_duration_ms']} = {r['analysis_duration_ms']/1000:.1f}s")
        # 分析总耗时拆解
        tool_time = r.get("total_tool_duration_ms", 0)
        print(f"  tool_duration_ms: {tool_time} = {tool_time/1000:.1f}s")
        print(f"  非工具耗时(llm+其他): {(r['analysis_duration_ms'] - tool_time)/1000:.1f}s")
        print()

if len(sklearn) >= 2:
    r1, r2 = sklearn_sorted
    # 分析总耗时对比
    analysis_speedup = r1["analysis_duration_ms"] / r2["analysis_duration_ms"]
    print(f"=== 加速比 ===\n")
    print(f"  串行 analysis_duration_ms: {r1['analysis_duration_ms']/1000:.1f}s")
    print(f"  并发 analysis_duration_ms: {r2['analysis_duration_ms']/1000:.1f}s")
    print(f"  分析总耗时加速比: {analysis_speedup:.1f}x")
    # 非工具耗时对比（主要是 LLM）
    r1_non_tool = r1["analysis_duration_ms"] - r1.get("total_tool_duration_ms", 0)
    r2_non_tool = r2["analysis_duration_ms"] - r2.get("total_tool_duration_ms", 0)
    if r1_non_tool > 0 and r2_non_tool > 0:
        llm_speedup = r1_non_tool / r2_non_tool
        print(f"  串行非工具耗时(llm+其他): {r1_non_tool/1000:.1f}s")
        print(f"  并发非工具耗时(llm+其他): {r2_non_tool/1000:.1f}s")
        print(f"  非工具耗时加速比: {llm_speedup:.1f}x")
    print(f"  理论加速比(4 workers): 3.5x")
