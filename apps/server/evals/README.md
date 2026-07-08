# Prompt 回归评测

修改 `apps/server/app/agent/prompts.py` 或 workflow 中与 prompt 相关的代码后，使用此流程进行回归测试。

脚本会通过后端 API 执行一次真实分析，保存结果 JSON，与缓存的基线对比，并检查当前结果是否满足 `codebasecoach.golden.json` 的标准。

## 先启动后端

```powershell
cd apps/server
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

## 首次运行：创建基线

在仓库根目录执行：

```powershell
& apps/server/.venv/Scripts/python.exe apps/server/scripts/prompt_regression_eval.py --repo-url https://github.com/owner/repo
```

首次运行会创建：

```text
data/prompt-evals/baselines/owner_repo.json
```

## 修改 prompt 后

再次执行相同命令：

```powershell
& apps/server/.venv/Scripts/python.exe apps/server/scripts/prompt_regression_eval.py --repo-url https://github.com/owner/repo
```

脚本会将新结果保存到：

```text
data/prompt-evals/runs/
```

并输出分数变化，例如：

```text
分数变化：
  textcitation_score: 0.95 -> 0.88 (-0.07，变差)
  coverage_score: 0.8 -> 0.75 (-0.05，变差)
  hallucination_risk: 0.05 -> 0.12 (+0.07，变差)
  usefulness_score: 0.9 -> 0.86 (-0.04，变差)
  interview_question_count: 8 -> 8 (0，不变)
```

`hallucination_risk` 越低越好，上升视为变差。

## 刷新基线

当当前 prompt 被确认为新版本后：

```powershell
& apps/server/.venv/Scripts/python.exe apps/server/scripts/prompt_regression_eval.py --repo-url https://github.com/owner/repo --refresh-baseline
```

## 机器可读输出

```powershell
& apps/server/.venv/Scripts/python.exe apps/server/scripts/prompt_regression_eval.py --repo-url https://github.com/owner/repo --json
```

命令退出码：通过 golden 检查时返回 `0`，失败时返回 `1`。