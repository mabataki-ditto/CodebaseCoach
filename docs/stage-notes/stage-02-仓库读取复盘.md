# 阶段 2：仓库读取复盘

## 1. 本阶段目标

本阶段目标是完成 GitHub URL 解析和本地仓库读取能力：

- 实现 GitHub URL 解析。
- 实现 `POST /api/repo/parse` 接口。
- 使用 GitPython 将公开 GitHub 仓库 clone 到 `temp_repos/`。
- 实现 `POST /api/repo/scan` 仓库预分析接口。
- 生成基础目录树。
- 过滤 `.git`、`node_modules`、`dist`、`build`、`.venv`、`__pycache__` 等无关目录。
- 读取 `README.md`、`package.json`、`requirements.txt`、`pyproject.toml` 等基础文件摘要。
- 限制单文件读取大小。
- 定义相关 Pydantic schema。
- clone 失败时返回结构化错误。

本阶段不实现真实 AI 调用，不生成最终 Markdown 文档，不一次性读取全部仓库文件内容。

## 2. 实际完成内容

- 在 `apps/server/app/services/repo_parser.py` 实现 `parse_github_repo_url`，支持 `https://github.com/owner/repo` 和 `https://github.com/owner/repo.git`。
- 在 `apps/server/app/api/repo.py` 实现 `POST /api/repo/parse` 和 `POST /api/repo/scan`。
- 在 `apps/server/app/services/github_service.py` 使用 GitPython 执行浅克隆，目标目录为 `temp_repos/{owner}_{repo}_{timestamp}/`。
- 在 `apps/server/app/services/file_tree_service.py` 实现目录树生成、无关目录过滤和基础文件摘要读取。
- 在 `apps/server/app/schemas/repo.py` 定义请求、解析响应、扫描响应、文件树节点和基础文件摘要 schema。
- 在 `apps/server/app/core/errors.py` 增加 `AppError` 和统一错误响应构造。
- 在 `apps/server/app/main.py` 注册 repo router 和 `AppError` 异常处理器。
- 在 `apps/server/app/core/config.py` 增加 `TEMP_REPO_DIR`、`MAX_BASIC_FILE_BYTES`、`MAX_FILE_TREE_DEPTH`、`MAX_FILE_TREE_ENTRIES` 对应配置能力。
- 在 `apps/server/tests/test_repo_services.py` 增加 URL 解析、无效 URL、目录过滤、基础文件读取大小限制测试。
- 在 `apps/server/requirements.txt` 新增 `GitPython==3.1.44`。

## 3. 遇到的问题与解决方案

### 问题 1：如何让 URL 解析既满足阶段要求，又避免 SSRF 和路径污染？

#### S - Situation 背景

`/api/repo/parse` 和 `/api/repo/scan` 都接收用户传入的 `repo_url`。如果后端接受任意 URL，后续 clone 或网络访问可能被引导到非 GitHub 主机，甚至内部地址。

#### T - Task 任务

需要只支持阶段要求中的 GitHub 仓库 URL：`https://github.com/owner/repo` 和 `https://github.com/owner/repo.git`。无效 URL 必须返回 400 和结构化错误。

#### A - Action 行动

在 `repo_parser.py` 中使用 `urlparse` 解析 URL，只允许 `https` 协议和 `github.com` host；要求 path 只能有 owner/repo 两段；拒绝 query、fragment 和额外路径；对 owner 和 repo 做正则校验；将 `.git` 后缀归一化为 canonical URL。

#### R - Result 结果

合法 URL 可以稳定解析出 `owner`、`repo` 和规范化后的 `repo_url`。非 GitHub URL 会返回 `INVALID_GITHUB_URL`，HTTP 状态码为 400，不会进入 clone 流程。

#### 技术细节

- 解析函数：`apps/server/app/services/repo_parser.py`。
- 错误类型：`AppError(code="INVALID_GITHUB_URL", status_code=400)`。
- 接口：`POST /api/repo/parse`。
- 测试覆盖：`RepoParserTests.test_parse_https_github_repo_url`、`test_parse_trims_git_suffix`、`test_invalid_url_raises_app_error`。

#### 面试表达

我没有把用户传入的 URL 直接交给 Git clone，而是先在 API 边界做白名单解析。这里只允许 `https://github.com/owner/repo` 这一类地址，并拒绝 query、fragment 和多余路径。这样既满足产品阶段要求，也降低了 SSRF 和路径污染风险。

### 问题 2：为什么 `/api/repo/parse` 和 `/api/repo/scan` 要拆成两个接口？

#### S - Situation 背景

阶段要求同时包含 GitHub URL 解析和仓库 clone。解析是轻量操作，clone 是网络和磁盘 I/O 操作，耗时和失败概率都更高。

#### T - Task 任务

需要给前端提供仓库预分析能力，同时保留一个可以快速校验 owner/repo 的接口。

#### A - Action 行动

实现两个接口：`POST /api/repo/parse` 只做 URL 解析，不访问网络；`POST /api/repo/scan` 先复用解析逻辑，再执行浅克隆、目录树生成和基础文件读取。

#### R - Result 结果

前端可以先用 `parse` 做低成本校验和展示，也可以用 `scan` 执行真正的预分析。clone 失败不会影响 URL 解析接口。

#### 技术细节

- 路由文件：`apps/server/app/api/repo.py`。
- 请求模型：`RepoRequest`。
- 解析响应：`RepoParseResponse`。
- 扫描响应：`RepoScanResponse`，只返回前端需要的 `owner`、`repo`、`repo_url`、`file_tree`、`basic_files`，不暴露本地绝对路径。

#### 面试表达

我把 parse 和 scan 拆开，是因为它们的成本和失败模式不同。parse 是纯计算，可以快速返回；scan 要访问 GitHub 和写本地磁盘，应该单独表达。这样的 API 对前端更友好，也便于后续做进度展示和错误处理。

### 问题 3：如何读取基础文件而不一次性读取整个仓库？

#### S - Situation 背景

产品要求后端读取 README、package.json 等基础文件，但明确禁止一次性读取整个仓库，也要求限制单文件读取大小。

#### T - Task 任务

需要返回基础文件摘要，让前端能展示仓库预分析结果，同时避免读取过多内容或二进制文件。

#### A - Action 行动

在 `file_tree_service.py` 中只读取根目录下的 `README.md`、`package.json`、`requirements.txt`、`pyproject.toml`。读取时按 `MAX_BASIC_FILE_BYTES` 截断，检测空字节来跳过二进制内容，响应中返回 `content_preview`、`size` 和 `truncated`。

#### R - Result 结果

`modelcontextprotocol/typescript-sdk` 的扫描结果能返回 `package.json` 和 `README.md` 摘要；大文件会被截断并标记 `truncated=true`，不会完整读入内存。

#### 技术细节

- 服务函数：`read_basic_files(root, max_bytes=...)`。
- 默认大小限制：`MAX_BASIC_FILE_BYTES=20000`。
- 响应模型：`BasicFileSummary`。
- 测试覆盖：`FileTreeTests.test_read_basic_files_limits_content_size`。

#### 面试表达

我没有为了预分析读取所有文件，而是只读取根目录几个高价值基础文件。每个文件都按字节数限制读取，并返回摘要和是否截断。这样可以给前端提供足够上下文，同时避免把整个仓库塞进内存或后续模型上下文。

### 问题 4：如何保证目录树可用但不过度膨胀？

#### S - Situation 背景

真实 GitHub 仓库可能包含 `.git`、`node_modules`、`dist`、`build`、缓存目录和虚拟环境目录。如果目录树不做过滤，前端展示会很乱，后端扫描成本也会升高。

#### T - Task 任务

需要生成基础目录树，同时过滤阶段要求中的无关目录，并限制树的深度和节点数量。

#### A - Action 行动

在 `build_file_tree` 中统一过滤 `.git`、`node_modules`、`dist`、`build`、`coverage`、`.venv`、`venv`、`__pycache__`、`.next`、`.nuxt`、`.cache`、`.idea`、`.vscode`。同时加入 `MAX_FILE_TREE_DEPTH` 和 `MAX_FILE_TREE_ENTRIES` 配置，避免深层目录或超大仓库导致响应过大。

#### R - Result 结果

目录树会保留业务相关目录和文件，跳过无关运行产物。测试中的 `.git` 和 `node_modules` 不会出现在返回结果中。

#### 技术细节

- 服务函数：`build_file_tree(root, max_depth, max_entries)`。
- 默认深度：`MAX_FILE_TREE_DEPTH=4`。
- 默认节点数：`MAX_FILE_TREE_ENTRIES=1000`。
- 响应模型：`FileTreeNode`，包含 `name`、`path`、`type`、`children`。
- 测试覆盖：`FileTreeTests.test_build_file_tree_filters_runtime_directories`。

#### 面试表达

目录树不是越完整越好，预分析阶段更重要的是快速展示项目结构。我过滤掉依赖、构建产物、缓存和 Git 元数据，并限制深度与节点数。这样可以让响应更稳定，也让前端展示更聚焦。

### 问题 5：真实 clone 验证遇到 Git HTTPS 凭据错误时如何处理？

#### S - Situation 背景

在沙箱内直接 clone `https://github.com/octocat/Hello-World` 时，Git 返回 `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`。这不是业务代码逻辑错误，而是当前 Windows 沙箱环境的 Git HTTPS 凭据/网络限制。

#### T - Task 任务

阶段验收要求必须可以 clone 公开 GitHub 仓库，因此需要区分业务错误和环境限制，并完成真实 clone 验证。

#### A - Action 行动

先确认服务层会把 GitPython 的 `GitCommandError` 转成结构化 `REPO_CLONE_FAILED`，保证服务不崩溃。随后按权限流程在沙箱外重试同一 clone 验证，确认公开仓库可以 clone 到 `temp_repos/`。最后通过 `/api/repo/scan` 对用户示例仓库 `modelcontextprotocol/typescript-sdk` 进行接口级验证。

#### R - Result 结果

沙箱内 clone 失败时返回结构化 502 错误，不会导致服务崩溃；沙箱外 clone 验证成功。`/api/repo/scan` 对用户示例仓库返回 200，并返回目录树和 `package.json`、`README.md` 基础文件摘要。

#### 技术细节

- clone 服务：`apps/server/app/services/github_service.py`。
- clone 失败错误码：`REPO_CLONE_FAILED`。
- 成功 clone 目标：`temp_repos/{owner}_{repo}_{timestamp}/`。
- 接口验证仓库：`https://github.com/modelcontextprotocol/typescript-sdk`。
- 验证结果包含：`tree=27`，`basic_files=["package.json", "README.md"]`。

#### 面试表达

我把 clone 失败当成一个可预期的外部系统错误处理，而不是让服务崩溃。GitPython 抛出的异常会被转换成结构化错误，前端可以展示失败原因。实际网络环境放开后，同一套代码可以 clone 公共仓库并返回预分析结果。

## 4. 技术取舍

- 使用 GitPython 而不是 GitHub REST API：GitPython 能获取真实仓库文件结构，更贴近后续本地扫描、核心文件筛选和文档生成流程。
- 使用浅克隆 `depth=1`：减少网络和磁盘成本；代价是不保留完整提交历史，但本项目当前只需要当前工作区文件。
- `parse` 和 `scan` 拆分：解析接口稳定快速，扫描接口承担网络与磁盘 I/O，错误边界更清晰。
- 只读取基础文件摘要：满足预分析需要，同时避免一次性读取所有文件。
- 返回结构化错误：无效 URL 返回 400，clone 失败返回 502，前端不会因为异常栈而崩溃。

## 5. 面试可讲点

- 如何设计一个安全的 GitHub URL 解析接口？
- 为什么仓库扫描要先浅克隆到本地，而不是直接调用 GitHub API？
- 如何避免读取整个仓库导致内存或 token 压力？
- clone 失败、无效 URL 这类错误如何结构化返回给前端？
- 为什么目录树要过滤依赖和构建产物？

## 6. 相关 ADR

- `docs/adr/005-为什么使用GitPython进行仓库读取.md`
- `docs/adr/006-仓库预分析接口边界.md`
