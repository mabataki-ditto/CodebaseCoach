import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    backendBaseUrl: 'http://localhost:8000',
  }),
})
