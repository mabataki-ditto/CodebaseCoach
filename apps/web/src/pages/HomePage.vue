<template>
  <main class="page-stack">
    <section class="hero">
      <div>
        <p class="eyebrow">开源项目学习与面试准备 Agent</p>
        <h1>CodebaseCoach</h1>
        <p class="lead">把 GitHub 仓库分析成可学习、可复盘、可用于面试表达的结构化材料。</p>
      </div>

      <n-card title="开始分析" :bordered="false">
        <n-space vertical size="large">
          <n-input
            v-model:value="repoUrl"
            size="large"
            placeholder="https://github.com/owner/repo"
            clearable
          />
          <n-button type="primary" size="large" block @click="startAnalyze">
            开始分析
          </n-button>
          <n-alert v-if="errorMessage" type="warning" :show-icon="false">
            {{ errorMessage }}
          </n-alert>
        </n-space>
      </n-card>
    </section>

    <n-grid class="home-info-grid" :cols="3" :x-gap="16" :y-gap="16" responsive="screen">
      <n-grid-item>
        <n-card class="home-info-card" title="示例仓库" size="small">
          <n-button text type="primary" @click="useExample">vuejs/core</n-button>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card class="home-info-card" title="最近分析" size="small">
          暂无历史记录，后续阶段接入本地记录。
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card class="home-info-card" title="能力范围" size="small">
          当前阶段提供页面入口和工作台骨架，暂不执行真实仓库分析。
        </n-card>
      </n-grid-item>
    </n-grid>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const repoUrl = ref('')
const errorMessage = ref('')

const githubRepoPattern = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?$/

function useExample() {
  repoUrl.value = 'https://github.com/vuejs/core'
  errorMessage.value = ''
}

function startAnalyze() {
  if (!githubRepoPattern.test(repoUrl.value.trim())) {
    errorMessage.value = '请输入有效的 GitHub 仓库地址，例如 https://github.com/owner/repo'
    return
  }

  router.push({ name: 'workspace', query: { repo: repoUrl.value.trim() } })
}
</script>
