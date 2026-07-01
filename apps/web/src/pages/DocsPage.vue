<template>
  <main class="page-stack">
    <section class="section-header">
      <div>
        <h1>文档页</h1>
        <p>查看、复制和下载历史分析生成的 Markdown 文档。</p>
      </div>
      <n-space>
        <n-button secondary :disabled="!selectedDocument" @click="copyMarkdown">复制 Markdown</n-button>
        <n-button secondary :disabled="!selectedDocument" @click="downloadMarkdown">下载 Markdown</n-button>
        <n-button secondary @click="$router.push('/history')">返回历史</n-button>
      </n-space>
    </section>

    <n-alert v-if="errorMessage" type="error" :show-icon="false">
      {{ errorMessage }}
    </n-alert>

    <n-spin :show="isLoading">
      <n-grid :cols="2" :x-gap="16" :y-gap="16" responsive="screen">
        <n-grid-item>
          <n-card title="文档列表" :bordered="false">
            <div v-if="documents.length" class="doc-list">
              <button
                v-for="document in documents"
                :key="document.path"
                class="doc-list-item"
                :class="{ active: document.path === selectedDocPath }"
                type="button"
                @click="selectedDocPath = document.path"
              >
                <strong>{{ document.title }}</strong>
                <span>{{ document.filename }}</span>
              </button>
            </div>
            <n-empty v-else description="从历史记录打开文档后显示 Markdown 列表" />
          </n-card>
        </n-grid-item>

        <n-grid-item>
          <n-card title="Markdown 预览" :bordered="false">
            <div v-if="selectedDocument" class="doc-meta">
              <n-tag size="small">{{ docsDir }}</n-tag>
              <span>{{ selectedDocument.path }}</span>
            </div>
            <article v-if="selectedDocument" class="markdown-preview rich-preview" v-html="renderMarkdown(selectedDocument.content)" />
            <n-alert v-else type="info" :show-icon="false">
              请从历史记录页打开一次分析结果。
            </n-alert>
          </n-card>
        </n-grid-item>
      </n-grid>
    </n-spin>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { fetchDocsByHistoryId } from '../api/docs'
import { useAppStore } from '../stores/app'
import type { GeneratedDocument } from '../types/analysis'

const route = useRoute()
const message = useMessage()
const appStore = useAppStore()
const documents = ref<GeneratedDocument[]>([])
const docsDir = ref('')
const selectedDocPath = ref<string | null>(null)
const isLoading = ref(false)
const errorMessage = ref('')

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

const selectedDocument = computed(() => documents.value.find((document) => document.path === selectedDocPath.value) ?? null)

onMounted(loadDocs)
watch(() => route.query.history_id, loadDocs)

async function loadDocs() {
  const historyId = String(route.query.history_id ?? '')
  if (!historyId) {
    documents.value = []
    selectedDocPath.value = null
    docsDir.value = ''
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  try {
    const result = await fetchDocsByHistoryId(appStore.backendBaseUrl, historyId)
    documents.value = result.documents
    docsDir.value = result.docs_dir
    selectedDocPath.value = result.documents[0]?.path ?? null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '文档读取失败'
  } finally {
    isLoading.value = false
  }
}

async function copyMarkdown() {
  if (!selectedDocument.value) {
    return
  }
  await navigator.clipboard.writeText(selectedDocument.value.content)
  message.success('Markdown 已复制')
}

function downloadMarkdown() {
  if (!selectedDocument.value) {
    return
  }
  const blob = new Blob([selectedDocument.value.content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = selectedDocument.value.filename
  link.click()
  URL.revokeObjectURL(url)
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
</script>
