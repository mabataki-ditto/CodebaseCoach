<template>
  <main class="page-stack">
    <section class="section-header">
      <div>
        <h1>文档页</h1>
        <p>用于查看、复制和下载后续生成的 Markdown 文档。</p>
      </div>
      <n-space>
        <n-button secondary @click="copyMarkdown">复制 Markdown</n-button>
        <n-button secondary @click="downloadMarkdown">下载 Markdown</n-button>
      </n-space>
    </section>

    <n-grid :cols="2" :x-gap="16" :y-gap="16" responsive="screen">
      <n-grid-item>
        <n-card title="文档列表">
          <n-tabs type="segment">
            <n-tab-pane name="overview" tab="项目概览" />
            <n-tab-pane name="stack" tab="技术栈分析" />
            <n-tab-pane name="qa" tab="面试问答" />
          </n-tabs>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="Markdown 预览">
          <article class="markdown-preview">
            <h2>项目概览</h2>
            <p>后续阶段会从 `generated_docs/` 读取文档内容。</p>
          </article>
        </n-card>
      </n-grid-item>
    </n-grid>
  </main>
</template>

<script setup lang="ts">
import { useMessage } from 'naive-ui'

const message = useMessage()

function copyMarkdown() {
  message.info('当前阶段仅提供复制入口')
}

function downloadMarkdown() {
  message.info('当前阶段仅提供下载入口')
}
</script>
