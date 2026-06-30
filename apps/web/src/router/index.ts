import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '../pages/HomePage.vue'
import WorkspacePage from '../pages/WorkspacePage.vue'
import DocsPage from '../pages/DocsPage.vue'
import HistoryPage from '../pages/HistoryPage.vue'
import SettingsPage from '../pages/SettingsPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomePage },
    { path: '/workspace', name: 'workspace', component: WorkspacePage },
    { path: '/docs', name: 'docs', component: DocsPage },
    { path: '/history', name: 'history', component: HistoryPage },
    { path: '/settings', name: 'settings', component: SettingsPage },
  ],
})
