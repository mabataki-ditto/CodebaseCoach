<template>
  <n-config-provider>
    <n-message-provider>
      <n-layout class="app-shell">
        <n-layout-header bordered class="app-header">
          <RouterLink class="brand" to="/">CodebaseCoach</RouterLink>
          <nav class="nav-links" aria-label="主导航">
            <RouterLink v-for="item in navItems" :key="item.path" :to="item.path">
              {{ item.label }}
            </RouterLink>
          </nav>
        </n-layout-header>

        <n-layout-content class="app-content">
          <RouterView />
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
const navItems = [
  { path: '/', label: '首页' },
  { path: '/workspace', label: '分析工作台' },
  { path: '/docs', label: '文档页' },
  { path: '/history', label: '历史记录' },
  { path: '/settings', label: '设置' },
]
</script>
