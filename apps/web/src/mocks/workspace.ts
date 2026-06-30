export const mockFileTree = [
  {
    label: 'typescript-sdk',
    key: 'root',
    children: [
      { label: 'README.md', key: 'README.md' },
      { label: 'package.json', key: 'package.json' },
      { label: 'tsconfig.json', key: 'tsconfig.json' },
      {
        label: 'src',
        key: 'src',
        children: [
          { label: 'client/index.ts', key: 'src/client/index.ts' },
          { label: 'server/index.ts', key: 'src/server/index.ts' },
          { label: 'shared/protocol.ts', key: 'src/shared/protocol.ts' },
          { label: 'types.ts', key: 'src/types.ts' },
        ],
      },
      {
        label: 'examples',
        key: 'examples',
        children: [
          { label: 'simple-client.ts', key: 'examples/simple-client.ts' },
          { label: 'simple-server.ts', key: 'examples/simple-server.ts' },
        ],
      },
      {
        label: 'test',
        key: 'test',
        children: [{ label: 'protocol.test.ts', key: 'test/protocol.test.ts' }],
      },
    ],
  },
]

export const mockCoreFiles = [
  {
    path: 'README.md',
    type: 'Markdown',
    reason: '项目入口说明，适合提取定位、安装方式和使用示例。',
    status: '已读取',
    usedForContext: true,
  },
  {
    path: 'package.json',
    type: 'Package',
    reason: '识别脚本、依赖和包发布信息，是判断技术栈的基础文件。',
    status: '已读取',
    usedForContext: true,
  },
  {
    path: 'src/client/index.ts',
    type: 'TypeScript',
    reason: '客户端 API 入口，适合分析外部调用方式和核心抽象。',
    status: '待精读',
    usedForContext: true,
  },
  {
    path: 'src/server/index.ts',
    type: 'TypeScript',
    reason: '服务端能力入口，适合分析协议处理和工具暴露方式。',
    status: '待精读',
    usedForContext: true,
  },
]

export const mockAgentSteps = [
  {
    title: '解析仓库地址',
    description: '从 GitHub URL 中识别 owner/repo，并规范化 .git 后缀。',
  },
  {
    title: '克隆公开仓库',
    description: '使用浅克隆获取当前工作区文件，不读取提交历史。',
  },
  {
    title: '生成目录树',
    description: '过滤依赖、构建产物、缓存目录和 Git 元数据。',
  },
  {
    title: '读取基础文件',
    description: '读取 README.md、package.json 等基础文件摘要。',
  },
  {
    title: '筛选核心文件',
    description: '下一阶段将基于规则选择核心文件并限制内容长度。',
  },
]

export const mockToolLogs = [
  {
    title: 'parse_github_repo_url',
    content: '输入 https://github.com/modelcontextprotocol/typescript-sdk，输出 owner/repo。',
    time: '09:30:12',
    type: 'success' as const,
  },
  {
    title: 'clone_repository',
    content: '浅克隆到 temp_repos/modelcontextprotocol_typescript-sdk_timestamp。',
    time: '09:30:16',
    type: 'success' as const,
  },
  {
    title: 'build_file_tree',
    content: '返回 27 个顶层/核心节点，过滤 node_modules、dist、.git。',
    time: '09:30:17',
    type: 'info' as const,
  },
  {
    title: 'read_basic_files',
    content: '读取 package.json 和 README.md 摘要，未触发截断。',
    time: '09:30:18',
    type: 'success' as const,
  },
]

export const mockMarkdownSections = {
  title: 'typescript-sdk 项目预览',
  summary:
    '这是一个基于 mock 数据的仓库学习预览，展示后续 AI 文档生成前的工作台形态。',
  facts: [
    '仓库入口文件显示项目以 TypeScript 为主。',
    'package.json 暴露了构建、测试和发布脚本。',
    'README.md 提供了客户端和服务端的基础使用示例。',
  ],
  nextSteps: [
    '继续筛选核心文件并限制单文件读取长度。',
    '构建 AI 分析上下文前，需要标记每个文件的选择理由。',
    '真实文档生成将在后续阶段接入，不属于当前 UI 阶段。',
  ],
}
