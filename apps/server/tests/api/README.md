# 接口自动化测试

这套测试通过 `requests` 访问已经启动的 FastAPI/Uvicorn 服务，覆盖真实 HTTP 端口；它与现有的 FastAPI `TestClient` 测试并存，不替代后者。

## 目录职责

```text
tests/api/
├── clients/       # 通用请求封装和按业务域划分的接口 Client
├── cases/         # YAML 数据驱动用例
├── utils/         # YAML 加载与结构校验
├── conftest.py    # base URL、超时和 Client fixtures（无 token）
└── test_*_api.py  # 断言与 Allure 用例信息
```

`api` 是真实端口测试，`external` 会访问 GitHub，`llm` 会调用真实大模型并可能产生费用。默认 CI 只执行 `api and not external and not llm`。

## 本地运行

在 `apps/server` 目录安装开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.api-test.example .env.api-test
```

终端一启动 FastAPI 服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端二运行默认接口用例并生成 Allure 原始结果：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api --run-api -m "api and not external and not llm" --alluredir=tests/reports/allure-results
```

如需访问 GitHub，再显式执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api --run-api -m "api and external and not llm" --alluredir=tests/reports/allure-results
```

真实大模型分析必须由服务端提供有效的 `LLM_*` 配置，并会访问 GitHub、产生模型费用。确认后再显式执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api --run-api -m "api and llm" --alluredir=tests/reports/allure-results
```

安装 Allure Commandline 后，可查看报告：

```powershell
allure serve tests/reports/allure-results
```

`allure-pytest` 负责生成原始结果，Allure Commandline 负责渲染和打开可视化报告。请求方法、路径、参数、响应状态和响应正文会进入 `tests/reports/api-tests.log` 或 Allure 附件；流式响应正文不会被请求封装提前消费。

## 新增用例

1. 在 `cases/` 对应 YAML 中新增带唯一 `id` 的数据。
2. 只在接口路径或参数不同的情况下扩展 `clients/`。
3. 在 `test_*_api.py` 中保留业务断言，不把断言写进请求封装。

接口测试不带 `--run-api` 时会跳过，以免误连本机或测试环境。`API_BASE_URL` 可直接指向 Nginx、网关或已部署环境，因此同一套测试也能覆盖反向代理和部署路由配置。
