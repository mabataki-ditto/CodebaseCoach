<template>
  <n-layout class="settings-page" embedded>
    <section class="page-heading">
      <div>
        <h1>设置</h1>
        <p>展示后端连接、模型配置说明、显示设置和缓存目录。</p>
      </div>
      <n-button secondary @click="checkHealth">健康检查</n-button>
    </section>

    <n-grid :cols="2" :x-gap="16" :y-gap="16" responsive="screen">
      <n-grid-item>
        <n-card title="后端连接">
          <n-descriptions :column="1" bordered>
            <n-descriptions-item label="服务地址"
              >http://localhost:8000</n-descriptions-item
            >
            <n-descriptions-item label="健康状态">{{
              healthStatus
            }}</n-descriptions-item>
          </n-descriptions>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="模型配置">
          <n-descriptions :column="1" bordered>
            <n-descriptions-item label="当前模型"
              >deepseek V4 flash</n-descriptions-item
            >
            <n-descriptions-item label="LLM 模式">真实 LLM</n-descriptions-item>
            <n-descriptions-item label="API Key"
              >仅在后端 .env 配置</n-descriptions-item
            >
          </n-descriptions>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="显示设置">
          <n-space vertical>
            <span>主题模式：浅色</span>
            <span>Markdown 字号：默认</span>
            <span>工具调用日志：显示</span>
          </n-space>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="缓存目录">
          <n-space vertical>
            <span>临时仓库：temp_repos/</span>
            <span>生成文档：generated_docs/</span>
            <n-button secondary>清理缓存</n-button>
          </n-space>
        </n-card>
      </n-grid-item>
    </n-grid>
  </n-layout>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useMessage } from "naive-ui";

const message = useMessage();
const healthStatus = ref("未检查");

async function checkHealth() {
  try {
    const response = await fetch("http://localhost:8000/health");
    healthStatus.value = response.ok ? "正常" : "异常";
  } catch {
    healthStatus.value = "无法连接";
    message.warning("无法连接后端服务");
  }
}
</script>
