<template>
  <main class="page-stack">
    <section class="section-header">
      <div>
        <h1>历史记录</h1>
        <p>后续阶段会展示已分析仓库、生成文档路径和分析状态。</p>
      </div>
    </section>

    <n-card>
      <n-empty description="暂无历史记录">
        <template #extra>
          <n-button secondary @click="$router.push('/')">返回首页</n-button>
        </template>
      </n-empty>
    </n-card>
  </main>
</template>
