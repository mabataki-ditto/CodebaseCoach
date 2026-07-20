<template>
  <n-layout class="workspace-page" embedded>
    <section class="workspace-toolbar">
      <div class="workspace-title">
        <p class="eyebrow">AI Analysis</p>
        <h1>分析工作台</h1>
        <p>输入 GitHub 仓库地址后，由后端完成仓库读取、核心文件筛选和真实 LLM 文档生成。</p>
      </div>

      <n-space class="workspace-actions" align="center" :wrap="true">
        <n-tag :type="analysisModeTagType">{{ analysisModeLabel }}</n-tag>
        <n-tag :type="repoMeta.statusType">{{ repoMeta.status }}</n-tag>
        <n-button secondary :disabled="!analysisResult || isLoading" @click="reanalyzeCurrentRepo">
          重新分析当前仓库
        </n-button>
        <n-button secondary :disabled="!analysisResult && !inputError && !displayDocuments.length" @click="clearCurrentAnalysis">
          清理当前结果
        </n-button>
        <n-button type="primary" :loading="isLoading" @click="runAnalysis">
          开始分析
        </n-button>
      </n-space>
    </section>

    <n-card class="workspace-card repo-card" :bordered="false">
      <div class="repo-input-row">
        <n-input
          v-model:value="repoInput"
          size="large"
          clearable
          placeholder="https://github.com/modelcontextprotocol/typescript-sdk"
          aria-label="GitHub 仓库地址"
          @keyup.enter="runAnalysis"
        />
        <n-button size="large" type="primary" :loading="isLoading" :disabled="isLoading" @click="runAnalysis">
          运行分析
        </n-button>
        <n-button v-if="isLoading" size="large" secondary type="error" @click="stopAnalysis">
          停止分析
        </n-button>
      </div>

      <n-alert v-if="inputError" type="error" :show-icon="false" class="workspace-alert">
        {{ inputError }}
      </n-alert>

      <n-alert v-if="isLoading" type="info" :show-icon="false" class="workspace-alert">
        正在分析：{{ streamStatusText || '等待后端事件...' }}
      </n-alert>

      <div class="repo-summary">
        <div>
          <span class="meta-label">仓库</span>
          <strong>{{ repoMeta.owner }}/{{ repoMeta.repo }}</strong>
        </div>
        <div>
          <span class="meta-label">核心文件</span>
          <strong>{{ displayCoreFiles.length }} 个</strong>
        </div>
      </div>
    </n-card>

    <section class="workspace-grid">
      <aside class="workspace-column left-column">
        <n-card title="仓库文件树" class="workspace-card" :bordered="false">
          <n-scrollbar class="panel-scroll tree-scroll">
            <n-tree v-if="fileTreeData.length" :data="fileTreeData" block-line default-expand-all />
            <n-empty v-else description="运行分析后显示后端返回的目录树" />
          </n-scrollbar>
        </n-card>

        <n-card title="核心文件" class="workspace-card" :bordered="false">
          <n-scrollbar class="panel-scroll core-file-scroll">
            <div v-if="displayCoreFiles.length" class="core-file-list">
              <article v-for="file in displayCoreFiles" :key="file.path" class="core-file-item">
                <div class="core-file-heading">
                  <strong>{{ file.path }}</strong>
                  <n-tag size="small">{{ file.file_type }}</n-tag>
                </div>
                <p>{{ file.reason }}</p>
                <n-space size="small">
                  <n-tag size="small" :type="file.read_status === 'read' ? 'success' : 'default'">
                    {{ file.read_status === 'read' ? '已读取' : file.read_status }}
                  </n-tag>
                  <n-tag v-if="file.used_for_context" size="small" type="info">用于 AI 上下文</n-tag>
                  <n-tag v-if="file.truncated" size="small" type="warning">已截断</n-tag>
                  <n-tag size="small">{{ formatBytes(file.size) }}</n-tag>
                </n-space>
              </article>
            </div>
            <n-empty v-else description="运行分析后显示后端筛选结果" />
          </n-scrollbar>
        </n-card>
      </aside>

      <aside class="workspace-column right-column">
        <n-card title="Markdown 文档预览" class="workspace-card preview-card" :bordered="false">
          <n-scrollbar class="panel-scroll preview-scroll">
            <n-tabs v-if="displayDocuments.length" v-model:value="selectedDocPath" type="line" animated>
              <n-tab-pane
                v-for="document in displayDocuments"
                :key="document.path"
                :name="document.path"
                :tab="document.title"
              >
                <div class="doc-meta">
                  <n-tag size="small" :type="analysisModeTagType">{{ analysisModeLabel }}</n-tag>
                  <span>{{ document.path }}</span>
                </div>
                <article class="markdown-preview rich-preview" v-html="renderMarkdown(document.content)" />
              </n-tab-pane>
            </n-tabs>
            <n-alert v-else type="info" :show-icon="false">
              运行分析后，这里会逐篇显示后端生成并保存到 generated_docs/ 的 Markdown 文档。
            </n-alert>
          </n-scrollbar>
        </n-card>
      </aside>
    </section>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import type { TreeOption } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import { AnalysisRequestError, cancelAnalysisJob, createAnalysisJob, createAnalysisJobEventSource } from '../api/analysis'
import { useAppStore } from '../stores/app'
import type {
  AnalysisEvent,
  AnalysisEventType,
  AnalyzeRepoResponse,
  CoreFileSummary,
  FileTreeNode,
  GeneratedDocument,
} from '../types/analysis'

type TagType = 'default' | 'success' | 'error' | 'warning' | 'info'

const analysisEventTypes: AnalysisEventType[] = [
  'job_started',
  'stage_started',
  'stage_completed',
  'stage_failed',
  'metrics_updated',
  'document_generated',
  'job_completed',
  'job_failed',
  'job_cancelled',
]

const route = useRoute()
const message = useMessage()
const appStore = useAppStore()
const defaultRepoUrl = 'https://github.com/modelcontextprotocol/typescript-sdk'
const eventSource = ref<EventSource | null>(null)
const stopRequested = ref(false)

if (!appStore.workspaceRepoInput) {
  appStore.workspaceRepoInput = String(route.query.repo ?? defaultRepoUrl)
}

const repoInput = computed({
  get: () => appStore.workspaceRepoInput,
  set: (value: string) => {
    appStore.workspaceRepoInput = value
  },
})
const inputError = computed({
  get: () => appStore.workspaceInputError,
  set: (value: string) => {
    appStore.workspaceInputError = value
  },
})
const analysisResult = computed<AnalyzeRepoResponse | null>(() => appStore.workspaceAnalysisResult)
const isLoading = computed(() => appStore.workspaceIsAnalyzing)
const selectedDocPath = computed({
  get: () => appStore.workspaceSelectedDocPath,
  set: (value: string | null) => {
    appStore.workspaceSelectedDocPath = value
  },
})

const streamStatusText = computed(() => appStore.workspaceStreamStatusText)
const displayFileTree = computed(() => analysisResult.value?.file_tree ?? appStore.workspaceStreamFileTree)
const displayCoreFiles = computed(() => analysisResult.value?.core_files ?? appStore.workspaceStreamCoreFiles)
const displayDocuments = computed(() => analysisResult.value?.documents ?? appStore.workspaceStreamDocuments)
const currentMockMode = computed(() => analysisResult.value?.mock_mode ?? appStore.workspaceStreamMockMode ?? false)

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(code: string, language: string): string {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value
    }
    return escapeHtml(code)
  },
})

const repoMeta = computed(() => {
  const parsed = parseRepoUrl(repoInput.value)
  const failed = Boolean(inputError.value)

  if (analysisResult.value) {
    return {
      owner: analysisResult.value.owner,
      repo: analysisResult.value.repo,
      status: failed ? '分析失败' : '真实 AI 分析完成',
      statusType: (failed ? 'error' : 'success') as TagType,
    }
  }

  return {
    owner: parsed?.owner ?? 'owner',
    repo: parsed?.repo ?? 'repo',
    status: failed ? '分析失败' : isLoading.value ? '分析中' : '等待分析',
    statusType: (failed ? 'error' : isLoading.value ? 'info' : 'default') as TagType,
  }
})

const fileTreeData = computed<TreeOption[]>(() => {
  if (!displayFileTree.value.length) {
    return []
  }

  return [
    {
      label: repoMeta.value.repo,
      key: 'root',
      children: toTreeOptions(displayFileTree.value),
    },
  ]
})

const analysisModeLabel = computed(() => (currentMockMode.value ? 'mock' : '真实 AI'))
const analysisModeTagType = computed<TagType>(() => (currentMockMode.value ? 'warning' : 'success'))

async function runAnalysis() {
  const parsed = parseRepoUrl(repoInput.value)
  if (!parsed) {
    inputError.value = '请输入有效的 GitHub 仓库地址，例如 https://github.com/owner/repo'
    return
  }

  closeEventSource()
  appStore.resetWorkspaceStreaming()
  inputError.value = ''
  appStore.workspaceAnalysisResult = null
  appStore.workspaceFailureSteps = []
  appStore.workspaceFailureToolLogs = []
  appStore.workspaceSelectedDocPath = null
  appStore.workspaceIsAnalyzing = true
  stopRequested.value = false
  appStore.workspaceStreamStatusText = '创建后端分析任务'

  try {
    const job = await createAnalysisJob(appStore.backendBaseUrl, parsed.url)
    appStore.workspaceCurrentJobId = job.job_id
    appStore.workspaceStreamStatusText = '后端任务已创建，等待事件流'
    openEventStream(job.job_id, appStore.workspaceLastEventSequence)
  } catch (error) {
    appStore.workspaceIsAnalyzing = false
    handleAnalysisError(error)
  }
}

async function stopAnalysis() {
  stopRequested.value = true
  const jobId = appStore.workspaceCurrentJobId
  closeEventSource()
  appStore.workspaceCurrentJobId = null
  appStore.workspaceIsAnalyzing = false
  appStore.workspaceStreamStatusText = '已请求停止分析'

  if (!jobId) {
    return
  }

  try {
    await cancelAnalysisJob(appStore.backendBaseUrl, jobId)
    message.warning('已请求后端停止分析')
  } catch (error) {
    handleAnalysisError(error)
  }
}

async function reanalyzeCurrentRepo() {
  if (analysisResult.value) {
    repoInput.value = analysisResult.value.repo_url
  }
  await runAnalysis()
}

function clearCurrentAnalysis() {
  void stopAnalysis()
  appStore.clearWorkspaceAnalysis()
}

function openEventStream(jobId: string, after = 0) {
  closeEventSource()
  const source = createAnalysisJobEventSource(appStore.backendBaseUrl, jobId, after)
  eventSource.value = source

  for (const eventType of analysisEventTypes) {
    source.addEventListener(eventType, (event) => {
      handleSseEvent(event as MessageEvent<string>)
    })
  }

  source.onerror = () => {
    if (stopRequested.value || !isLoading.value) {
      return
    }
    closeEventSource()
    appStore.workspaceCurrentJobId = null
    appStore.workspaceIsAnalyzing = false
    const text = '分析事件连接中断，请查看后端终端日志'
    inputError.value = text
    message.error(text)
  }
}

function handleSseEvent(rawEvent: MessageEvent<string>) {
  const event = JSON.parse(rawEvent.data) as AnalysisEvent
  const payload = event.payload
  appStore.workspaceLastEventSequence = event.sequence

  if (event.type === 'job_started') {
    appStore.workspaceStreamMockMode = payload.mock_mode === true
    const recoveryMode = payload.recovery_mode
    appStore.workspaceStreamStatusText = recoveryMode === 'rebuild_repository'
      ? '临时仓库已被清理，正在重新克隆后继续任务'
      : recoveryMode === 'full_restart'
        ? '仓库版本发生变化，正在重新生成文档以保证一致性'
        : payload.resumed === true
          ? '正在从最近的运行存档继续任务'
          : '任务开始'
    return
  }

  if (event.type === 'stage_started') {
    appStore.workspaceStreamStatusText = payloadText(payload, 'title', '执行分析阶段')
    return
  }

  if (event.type === 'stage_completed') {
    appStore.workspaceStreamStatusText = payloadText(payload, 'title', '阶段完成')
    if (payload.key === 'repo_loaded') {
      appStore.workspaceStreamFileTree = Array.isArray(payload.file_tree) ? (payload.file_tree as FileTreeNode[]) : []
      appStore.workspaceStreamCoreFiles = Array.isArray(payload.core_files) ? (payload.core_files as CoreFileSummary[]) : []
    }
    return
  }

  if (event.type === 'stage_failed') {
    appStore.workspaceStreamStatusText = `阶段失败：${payloadText(payload, 'title', '未知阶段')}`
    return
  }

  if (event.type === 'document_generated') {
    const document = payload.document as GeneratedDocument | undefined
    if (document?.path) {
      appStore.workspaceStreamDocuments = [
        ...appStore.workspaceStreamDocuments.filter((item) => item.path !== document.path),
        document,
      ]
      if (!selectedDocPath.value) {
        selectedDocPath.value = document.path
      }
    }
    appStore.workspaceStreamStatusText = `已生成 ${payload.index ?? appStore.workspaceStreamDocuments.length}/${payload.total ?? '?'} 篇 Markdown`
    return
  }

  if (event.type === 'job_completed') {
    const result = payload.result as AnalyzeRepoResponse
    appStore.setWorkspaceAnalysisResult(result)
    appStore.workspaceStreamStatusText = '分析完成'
    message.success('分析完成，Markdown 已逐篇生成')
    finishEventStream()
    return
  }

  if (event.type === 'job_failed') {
    const text = `${payloadText(payload, 'message', '分析失败')}${payload.detail ? `：${payload.detail}` : ''}`
    inputError.value = text
    message.error(text)
    finishEventStream()
    return
  }

  if (event.type === 'job_cancelled') {
    appStore.workspaceStreamStatusText = payloadText(payload, 'message', '分析已停止')
    message.warning('分析已停止')
    finishEventStream()
  }
}

function finishEventStream() {
  closeEventSource()
  appStore.workspaceCurrentJobId = null
  appStore.workspaceIsAnalyzing = false
}

function closeEventSource() {
  eventSource.value?.close()
  eventSource.value = null
}

function handleAnalysisError(error: unknown) {
  let agentSteps = appStore.workspaceFailureSteps
  let toolLogs = appStore.workspaceFailureToolLogs
  if (error instanceof AnalysisRequestError) {
    agentSteps = error.agentSteps
    toolLogs = error.toolLogs
  }
  const messageText = error instanceof Error ? error.message : '分析失败'
  appStore.setWorkspaceFailure(messageText, agentSteps, toolLogs)
  message.error(messageText)
}

onMounted(() => {
  if (appStore.workspaceIsAnalyzing && appStore.workspaceCurrentJobId) {
    stopRequested.value = false
    openEventStream(appStore.workspaceCurrentJobId, appStore.workspaceLastEventSequence)
  }
})

onBeforeUnmount(() => {
  closeEventSource()
})

function payloadText(payload: Record<string, unknown>, key: string, fallback: string): string {
  const value = payload[key]
  return typeof value === 'string' && value ? value : fallback
}

function parseRepoUrl(rawUrl: string): { owner: string; repo: string; url: string } | null {
  const normalized = normalizeRepoInput(rawUrl)
  const match = normalized.match(/^https:\/\/github\.com\/([A-Za-z0-9-]+)\/([A-Za-z0-9._-]+?)(?:\.git)?$/)
  if (!match) {
    return null
  }

  const [, owner, repo] = match
  return {
    owner,
    repo,
    url: `https://github.com/${owner}/${repo}`,
  }
}

function normalizeRepoInput(rawUrl: string): string {
  const value = rawUrl.trim()
  const markdownMatch = value.match(/^\[[^\]]+\]\((https:\/\/github\.com\/[^)\s]+)\)$/)
  if (markdownMatch) {
    return markdownMatch[1]
  }

  const shorthandMatch = value.match(/^([A-Za-z0-9-]+\/[A-Za-z0-9._-]+(?:\.git)?)$/)
  if (shorthandMatch) {
    return `https://github.com/${shorthandMatch[1]}`
  }

  return value
}

function toTreeOptions(nodes: FileTreeNode[]): TreeOption[] {
  return nodes.map((node) => ({
    label: node.type === 'directory' ? `${node.name}/` : node.name,
    key: node.path || node.name,
    children: node.children.length ? toTreeOptions(node.children) : undefined,
  }))
}

function renderMarkdown(content: string): string {
  return markdown.render(content)
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  return `${(bytes / 1024).toFixed(1)} KB`
}
</script>
