<template>
  <n-layout class="workspace-page" embedded>
    <section class="workspace-toolbar">
      <div class="workspace-title">
        <p class="eyebrow">AI Analysis</p>
        <h1>分析工作台</h1>
        <p>输入 GitHub 仓库地址后，由 FastAPI 完成仓库读取、核心文件筛选和 Markdown 文档生成。</p>
      </div>

      <n-space class="workspace-actions" align="center" :wrap="true">
        <n-tag :type="analysisModeTagType">{{ analysisModeLabel }}</n-tag>
        <n-tag type="info">OpenAI 仅由后端调用</n-tag>
        <n-button secondary @click="resetWorkspace">重置</n-button>
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
        <n-button size="large" type="primary" :loading="isLoading" @click="runAnalysis">
          运行分析
        </n-button>
      </div>

      <n-alert v-if="inputError" type="warning" :show-icon="false" class="workspace-alert">
        {{ inputError }}
      </n-alert>

      <div class="repo-summary">
        <div>
          <span class="meta-label">仓库</span>
          <strong>{{ repoMeta.owner }}/{{ repoMeta.repo }}</strong>
        </div>
        <div>
          <span class="meta-label">默认分支</span>
          <strong>{{ repoMeta.branch }}</strong>
        </div>
        <div>
          <span class="meta-label">分析状态</span>
          <n-tag :type="repoMeta.statusType">{{ repoMeta.status }}</n-tag>
        </div>
        <div>
          <span class="meta-label">核心文件</span>
          <strong>{{ analysisResult?.core_files.length ?? 0 }} 个</strong>
        </div>
      </div>
    </n-card>

    <n-spin :show="isLoading">
      <section class="workspace-grid">
        <aside class="workspace-column left-column">
          <n-card title="仓库文件树" class="workspace-card" :bordered="false">
            <n-scrollbar class="panel-scroll tree-scroll">
              <n-tree v-if="fileTreeData.length" :data="fileTreeData" block-line default-expand-all />
              <n-empty v-else description="运行分析后显示真实目录树" />
            </n-scrollbar>
          </n-card>

          <n-card title="核心文件" class="workspace-card" :bordered="false">
            <n-scrollbar class="panel-scroll core-file-scroll">
              <div v-if="analysisResult?.core_files.length" class="core-file-list">
                <article v-for="file in analysisResult.core_files" :key="file.path" class="core-file-item">
                  <div class="core-file-heading">
                    <strong>{{ file.path }}</strong>
                    <n-tag size="small">{{ file.file_type }}</n-tag>
                  </div>
                  <p>{{ file.reason }}</p>
                  <n-space size="small">
                    <n-tag size="small" type="success">{{ file.read_status === 'read' ? '已读取' : file.read_status }}</n-tag>
                    <n-tag v-if="file.used_for_context" size="small" type="info">用于上下文</n-tag>
                    <n-tag v-if="file.truncated" size="small" type="warning">已截断</n-tag>
                    <n-tag size="small">{{ formatBytes(file.size) }}</n-tag>
                  </n-space>
                </article>
              </div>
              <n-empty v-else description="运行分析后显示后端筛选结果" />
            </n-scrollbar>
          </n-card>
        </aside>

        <section class="workspace-column center-column">
          <n-card title="Agent 执行步骤" class="workspace-card" :bordered="false">
            <n-steps v-if="analysisResult?.agent_steps.length" vertical :current="agentCurrent" :status="agentStatus">
              <n-step
                v-for="step in analysisResult.agent_steps"
                :key="`${step.title}-${step.started_at}`"
                :title="step.title"
                :description="formatStepDescription(step)"
              />
            </n-steps>
            <n-empty v-else description="运行分析后显示步骤记录" />
          </n-card>

          <n-card title="工具调用日志" class="workspace-card" :bordered="false">
            <n-scrollbar class="panel-scroll tool-log-scroll">
              <n-timeline v-if="analysisResult?.tool_logs.length">
                <n-timeline-item
                  v-for="log in analysisResult.tool_logs"
                  :key="`${log.tool_name}-${log.created_at}`"
                  :type="timelineType(log.status)"
                  :title="log.tool_name"
                  :content="formatToolLog(log)"
                  :time="formatTime(log.created_at)"
                />
              </n-timeline>
              <n-empty v-else description="运行分析后显示工具调用" />
            </n-scrollbar>
          </n-card>
        </section>

        <aside class="workspace-column right-column">
          <n-card title="Markdown 文档预览" class="workspace-card preview-card" :bordered="false">
            <n-scrollbar class="panel-scroll preview-scroll">
              <n-tabs v-if="analysisResult?.documents.length" v-model:value="selectedDocPath" type="line" animated>
                <n-tab-pane
                  v-for="document in analysisResult.documents"
                  :key="document.path"
                  :name="document.path"
                  :tab="document.title"
                >
                  <div class="doc-meta">
                    <n-tag size="small" :type="analysisResult.mock_mode ? 'warning' : 'success'">
                      {{ analysisResult.mock_mode ? 'mock' : '真实 AI' }}
                    </n-tag>
                    <span>{{ document.path }}</span>
                  </div>
                  <article class="markdown-preview rich-preview" v-html="renderMarkdown(document.content)" />
                </n-tab-pane>
              </n-tabs>
              <n-alert v-else type="info" :show-icon="false">
                运行分析后，这里会展示后端生成并保存到 generated_docs/ 的 Markdown 文档。
              </n-alert>
            </n-scrollbar>
          </n-card>
        </aside>
      </section>
    </n-spin>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import type { TreeOption } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import { analyzeRepo } from '../api/analysis'
import { useAppStore } from '../stores/app'
import type { AgentStep, AnalyzeRepoResponse, FileTreeNode, ToolCallLog } from '../types/analysis'

const route = useRoute()
const message = useMessage()
const appStore = useAppStore()
const defaultRepoUrl = 'https://github.com/modelcontextprotocol/typescript-sdk'
const repoInput = ref(String(route.query.repo ?? defaultRepoUrl))
const inputError = ref('')
const isLoading = ref(false)
const analysisResult = ref<AnalyzeRepoResponse | null>(null)
const selectedDocPath = ref<string | null>(null)

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
  if (analysisResult.value) {
    const mode = analysisResult.value.mock_mode ? 'Mock' : '真实 AI'
    return {
      owner: analysisResult.value.owner,
      repo: analysisResult.value.repo,
      branch: '不确定',
      status: `${mode} 分析完成`,
      statusType: 'success' as const,
    }
  }

  const parsed = parseRepoUrl(repoInput.value)
  return {
    owner: parsed?.owner ?? 'owner',
    repo: parsed?.repo ?? 'repo',
    branch: '不确定',
    status: isLoading.value ? '分析中' : '等待分析',
    statusType: (isLoading.value ? 'info' : 'default') as 'info' | 'default',
  }
})

const fileTreeData = computed<TreeOption[]>(() => {
  if (!analysisResult.value) {
    return []
  }

  return [
    {
      label: analysisResult.value.repo,
      key: 'root',
      children: toTreeOptions(analysisResult.value.file_tree),
    },
  ]
})

const agentCurrent = computed(() => analysisResult.value?.agent_steps.length ?? 0)
const agentStatus = computed(() => {
  const hasFailedStep = analysisResult.value?.agent_steps.some((step) => step.status === 'failed')
  return hasFailedStep ? 'error' : 'finish'
})

const analysisModeLabel = computed(() => {
  if (!analysisResult.value) {
    return '自动模式'
  }
  return analysisResult.value.mock_mode ? 'mock 回退' : '真实 AI'
})

const analysisModeTagType = computed(() => (analysisResult.value?.mock_mode === false ? 'success' : 'warning'))

async function runAnalysis() {
  const parsed = parseRepoUrl(repoInput.value)
  if (!parsed) {
    inputError.value = '请输入有效的 GitHub 仓库地址，例如 https://github.com/owner/repo'
    return
  }

  inputError.value = ''
  isLoading.value = true

  try {
    const result = await analyzeRepo(appStore.backendBaseUrl, parsed.url)
    analysisResult.value = result
    selectedDocPath.value = result.documents[0]?.path ?? null
    const mode = result.mock_mode ? 'mock 回退' : '真实 AI'
    message.success(`${mode} 分析完成，Markdown 已保存到 generated_docs/`)
  } catch (error) {
    const messageText = error instanceof Error ? error.message : '分析失败'
    inputError.value = messageText
    message.error(messageText)
  } finally {
    isLoading.value = false
  }
}

function resetWorkspace() {
  repoInput.value = defaultRepoUrl
  inputError.value = ''
  analysisResult.value = null
  selectedDocPath.value = null
}

function parseRepoUrl(rawUrl: string): { owner: string; repo: string; url: string } | null {
  const match = rawUrl.trim().match(/^https:\/\/github\.com\/([A-Za-z0-9-]+)\/([A-Za-z0-9._-]+?)(?:\.git)?$/)
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

function toTreeOptions(nodes: FileTreeNode[]): TreeOption[] {
  return nodes.map((node) => ({
    label: node.type === 'directory' ? `${node.name}/` : node.name,
    key: node.path || node.name,
    children: node.children.length ? toTreeOptions(node.children) : undefined,
  }))
}

function formatStepDescription(step: AgentStep): string {
  const time = step.ended_at ? `完成于 ${formatTime(step.ended_at)}` : '未完成'
  return step.error_message ? `${step.description}。${step.error_message}` : `${step.description}。${time}`
}

function formatToolLog(log: ToolCallLog): string {
  const detail = log.error_message ? `；错误：${log.error_message}` : ''
  return `${log.input_summary} -> ${log.output_summary}，耗时 ${log.duration_ms}ms${detail}`
}

function timelineType(status: string): 'default' | 'success' | 'warning' | 'error' | 'info' {
  if (status === 'success') {
    return 'success'
  }
  if (status === 'failed') {
    return 'error'
  }
  return 'info'
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

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  return `${(bytes / 1024).toFixed(1)} KB`
}
</script>
