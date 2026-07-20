<template>
  <main class="page-stack">
    <section class="section-header">
      <div>
        <h1>历史记录</h1>
        <p>查看已经分析过的仓库，打开旧文档，删除历史记录，或重新分析当前仓库。</p>
      </div>
      <n-space>
        <n-button secondary :loading="isLoading" @click="loadHistory">刷新</n-button>
        <n-button type="primary" @click="$router.push('/')">新分析</n-button>
      </n-space>
    </section>

    <n-alert v-if="errorMessage" type="error" :show-icon="false">
      {{ errorMessage }}
    </n-alert>

    <n-spin :show="isLoading">
      <section v-if="records.length" class="history-list">
        <n-card v-for="record in records" :key="record.id" class="history-card" :bordered="false">
          <div class="history-card-main">
            <div class="history-title">
              <strong>{{ record.owner || 'unknown' }}/{{ record.repo || 'unknown' }}</strong>
              <n-tag size="small" :type="record.status === 'success' ? 'success' : 'error'">
                {{ record.status === 'success' ? '成功' : '失败' }}
              </n-tag>
              <n-tag size="small" :type="record.mock_mode ? 'warning' : 'success'">
                {{ record.mock_mode ? 'mock' : '真实 AI' }}
              </n-tag>
            </div>
            <p>{{ record.repo_url }}</p>
            <div class="history-meta">
              <span>核心文件 {{ record.core_files_count }}</span>
              <span>创建 {{ formatTime(record.created_at) }}</span>
              <span>完成 {{ formatTime(record.completed_at) }}</span>
              <span>{{ record.docs_dir || '未生成文档' }}</span>
            </div>
            <n-alert v-if="record.error_message" class="history-error" type="error" :show-icon="false">
              {{ record.error_message }}
            </n-alert>
          </div>
          <n-space class="history-actions" :wrap="true">
            <n-button size="small" :disabled="!record.docs_dir" @click="openDocs(record.id)">打开文档</n-button>
            <n-button
              v-if="resumeStatuses[record.id]?.can_resume"
              size="small"
              type="primary"
              :loading="resumingId === record.id"
              :disabled="resumingId !== null"
              @click="resume(record)"
            >
              继续任务
            </n-button>
            <n-button size="small" secondary :loading="reanalyzingId === record.id" @click="reanalyze(record)">
              重新分析
            </n-button>
            <n-button size="small" tertiary type="error" :loading="deletingId === record.id" @click="removeRecord(record.id)">
              删除记录
            </n-button>
          </n-space>
        </n-card>
      </section>

      <n-card v-else :bordered="false">
        <n-empty description="暂无历史记录">
          <template #extra>
            <n-button secondary @click="$router.push('/')">返回首页</n-button>
          </template>
        </n-empty>
      </n-card>
    </n-spin>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  analyzeRepo,
  getAnalysisJob,
  getAnalysisJobResumeStatus,
  resumeAnalysisJob,
} from '../api/analysis'
import { deleteHistoryRecord, fetchHistoryRecords } from '../api/history'
import { useAppStore } from '../stores/app'
import type { HistoryRecord } from '../types/history'
import type { AnalysisJobResumeStatusResponse } from '../types/analysis'

const router = useRouter()
const message = useMessage()
const appStore = useAppStore()
const records = ref<HistoryRecord[]>([])
const isLoading = ref(false)
const errorMessage = ref('')
const deletingId = ref<string | null>(null)
const reanalyzingId = ref<string | null>(null)
const resumingId = ref<string | null>(null)
const resumeStatuses = ref<Record<string, AnalysisJobResumeStatusResponse>>({})

onMounted(loadHistory)

async function loadHistory() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    records.value = await fetchHistoryRecords(appStore.backendBaseUrl)
    const failedRecords = records.value.filter((record) => record.status === 'failed')
    const statuses = await Promise.all(
      failedRecords.map(async (record) => {
        try {
          return [record.id, await getAnalysisJobResumeStatus(appStore.backendBaseUrl, record.id)] as const
        } catch {
          return null
        }
      }),
    )
    resumeStatuses.value = Object.fromEntries(statuses.filter((item) => item !== null))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '历史记录读取失败'
  } finally {
    isLoading.value = false
  }
}

async function resume(record: HistoryRecord) {
  if (resumingId.value !== null) return
  resumingId.value = record.id
  try {
    const snapshot = await getAnalysisJob(appStore.backendBaseUrl, record.id)
    const resumed = await resumeAnalysisJob(appStore.backendBaseUrl, record.id)
    appStore.prepareWorkspaceResume(snapshot, resumed.recovery_mode)
    if (resumed.recovery_mode === 'rebuild_repository') {
      message.info('临时仓库已被清理，系统将重新克隆仓库后继续任务。')
    } else if (resumed.recovery_mode === 'full_restart') {
      message.info('仓库版本发生变化，本次将重新执行文档生成以保证结果一致。')
    }
    await router.push({ name: 'workspace' })
  } catch (error) {
    message.error(error instanceof Error ? error.message : '继续任务失败')
    await loadHistory()
  } finally {
    resumingId.value = null
  }
}

function openDocs(recordId: string) {
  router.push({ name: 'docs', query: { history_id: recordId } })
}

async function removeRecord(recordId: string) {
  deletingId.value = recordId
  try {
    await deleteHistoryRecord(appStore.backendBaseUrl, recordId)
    records.value = records.value.filter((record) => record.id !== recordId)
    message.success('历史记录已删除，生成的 Markdown 文件已保留')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '历史记录删除失败')
  } finally {
    deletingId.value = null
  }
}

async function reanalyze(record: HistoryRecord) {
  reanalyzingId.value = record.id
  try {
    await analyzeRepo(appStore.backendBaseUrl, record.repo_url)
    message.success('重新分析完成，已生成新的历史记录')
    await loadHistory()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '重新分析失败')
    await loadHistory()
  } finally {
    reanalyzingId.value = null
  }
}

function formatTime(value: string | null | undefined): string {
  if (!value) {
    return '未记录'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>
