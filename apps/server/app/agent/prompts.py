from dataclasses import dataclass

from app.schemas.agent import CoreFileSummary
from app.schemas.repo import BasicFileSummary, RepoParseResponse


SYSTEM_PROMPT = """你是 CodebaseCoach 的文档生成助手。

必须遵守：
1. 只能基于用户提供的仓库信息、基础文件摘要和核心文件摘要回答。
2. 引用依据时，只能使用核心文件摘要中真实出现过的完整文件路径，例如 `src/main.ts`；不要编造未提供的文件。
3. 信息不足时写"不确定"，不要猜成事实。禁止使用"待补充""可以推测""猜测"等模糊表述代替明确结论。
4. 内容必须面向前端开发者理解项目，也要适合实习面试准备。
5. 必须清楚区分"事实""推测""建议"。
6. 输出 Markdown，不要输出 JSON，不要输出代码围栏包裹整篇文档。
7. 每篇文档必须有以 `# ` 开头的一级标题。
8. 反引号只能包裹真实文件路径。不要用反引号包裹依赖包名、URL、API 路径、目录名、变量名、命令、占位符或示例路由。
9. 如果只知道目录、依赖、接口或配置名，但没有对应的核心文件路径，用普通文本描述，不要写成文件引用。
10. 禁止输出 TODO、Todo、TBD、FIXME、待补充。
"""


@dataclass(frozen=True)
class DocumentPrompt:
    title: str
    filename: str
    instruction: str


REAL_DOCUMENT_PROMPTS: tuple[DocumentPrompt, ...] = (
    DocumentPrompt(
        title="项目概览",
        filename="01-项目概览.md",
        instruction="""生成项目概览文档。

建议结构：
- 项目一句话定位
- 可确认事实
- 关键目录和文件
- 前端开发者需要先理解的部分
- 不确定信息
- 面试讲述角度
""",
    ),
    DocumentPrompt(
        title="技术栈分析",
        filename="02-技术栈分析.md",
        instruction="""生成技术栈分析文档。

建议结构：
- 可确认技术栈
- 依赖和构建线索
- 前端相关技术点
- 后端或工具链线索
- 推测与不确定
- 面试可讲点
""",
    ),
    DocumentPrompt(
        title="核心模块解析",
        filename="03-核心模块解析.md",
        instruction="""生成核心模块解析文档。

建议结构：
- 核心文件清单
- 每个核心文件的职责
- 模块之间的关系
- 前端开发者阅读顺序
- 不确定信息
- 面试可讲点
""",
    ),
    DocumentPrompt(
        title="核心流程说明",
        filename="04-核心流程说明.md",
        instruction="""生成核心流程说明文档。

建议结构：
- 从入口到关键功能的流程
- 数据流或控制流
- 与前端开发相关的交互点
- 不确定信息
- 后续验证建议
- 面试可讲点
""",
    ),
    DocumentPrompt(
        title="面试问题与回答",
        filename="05-面试问题与回答.md",
        instruction="""生成实习面试问题与回答。

要求：
- 至少 8 个问题，每个问题使用三级标题格式，例如 ### Q1. 项目解决了什么问题？，回答紧跟其后。
- 每个回答都要尽量引用核心文件摘要中真实出现过的完整文件路径。
- 区分能确定的事实和需要进一步确认的推测。
- 问题要覆盖项目定位、技术栈、核心模块、工程取舍和可贡献点。
""",
    ),
    DocumentPrompt(
        title="简历描述",
        filename="06-简历描述.md",
        instruction="""生成简历描述文档。

建议结构：
- 一句话项目描述
- 3 到 5 条可放入简历的经历描述
- 可量化表达建议
- 面试展开话术
- 不能夸大的边界
""",
    ),
    DocumentPrompt(
        title="可贡献PR方向",
        filename="07-可贡献PR方向.md",
        instruction="""生成可贡献 PR 方向文档。

建议结构：
- 适合新手的 PR 方向
- 适合前端开发者的 PR 方向
- 需要先验证的信息
- 风险和注意事项
- 面试中如何讲“我会怎么贡献”
""",
    ),
)


def build_analysis_context(
    *,
    parsed_repo: RepoParseResponse,
    basic_files: list[BasicFileSummary],
    core_files: list[CoreFileSummary],
) -> str:
    return "\n\n".join(
        [
            _repo_section(parsed_repo),
            _basic_files_section(basic_files),
            _core_files_section(core_files),
        ]
    )


def _repo_section(parsed_repo: RepoParseResponse) -> str:
    return f"""## 仓库信息

- owner: {parsed_repo.owner}
- repo: {parsed_repo.repo}
- repo_url: {parsed_repo.repo_url}
"""


def _basic_files_section(basic_files: list[BasicFileSummary]) -> str:
    if not basic_files:
        return "## 基础文件摘要\n\n不确定：未读取到基础文件。"

    blocks = ["## 基础文件摘要"]
    for file in basic_files:
        blocks.append(
            f"""### `{file.path}`

- 类型：{file.file_type}
- 大小：{file.size} bytes
- 是否截断：{file.truncated}

```text
{file.content_preview}
```"""
        )
    return "\n\n".join(blocks)


def _core_files_section(core_files: list[CoreFileSummary]) -> str:
    if not core_files:
        return "## 核心文件摘要\n\n不确定：未筛选到核心文件。"

    blocks = ["## 核心文件摘要"]
    for file in core_files:
        blocks.append(
            f"""### `{file.path}`

- 类型：{file.file_type}
- 大小：{file.size} bytes
- 筛选原因：{file.reason}
- 读取状态：{file.read_status}
- 用于上下文：{file.used_for_context}
- 是否截断：{file.truncated}

```text
{file.content_preview}
```"""
        )
    return "\n\n".join(blocks)
