import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  NAlert,
  NButton,
  NCard,
  NConfigProvider,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NGrid,
  NGridItem,
  NInput,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NMessageProvider,
  NScrollbar,
  NSpace,
  NSpin,
  NStep,
  NSteps,
  NTabPane,
  NTabs,
  NTag,
  NTimeline,
  NTimelineItem,
  NTree,
  create,
} from 'naive-ui'
import App from './App.vue'
import { router } from './router'
import './styles.css'

const naive = create({
  components: [
    NAlert,
    NButton,
    NCard,
    NConfigProvider,
    NDescriptions,
    NDescriptionsItem,
    NEmpty,
    NGrid,
    NGridItem,
    NInput,
    NLayout,
    NLayoutContent,
    NLayoutHeader,
    NMessageProvider,
    NScrollbar,
    NSpace,
    NSpin,
    NStep,
    NSteps,
    NTabPane,
    NTabs,
    NTag,
    NTimeline,
    NTimelineItem,
    NTree,
  ],
})

createApp(App).use(createPinia()).use(router).use(naive).mount('#app')
