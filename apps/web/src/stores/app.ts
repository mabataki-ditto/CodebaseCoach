import { defineStore } from 'pinia'
import type { AgentStep, AnalyzeRepoResponse, CoreFileSummary, FileTreeNode, GeneratedDocument, ToolCallLog } from '../types/analysis'

export const useAppStore = defineStore('app', {
  state: () => ({
    backendBaseUrl: 'http://localhost:8000',
    workspaceRepoInput: '',
    workspaceInputError: '',
    workspaceAnalysisResult: null as AnalyzeRepoResponse | null,
    workspaceFailureSteps: [] as AgentStep[],
    workspaceFailureToolLogs: [] as ToolCallLog[],
    workspaceSelectedDocPath: null as string | null,
    workspaceIsAnalyzing: false,
    workspaceCurrentJobId: null as string | null,
    workspaceLastEventSequence: 0,
    workspaceStreamStatusText: '',
    workspaceStreamFileTree: [] as FileTreeNode[],
    workspaceStreamCoreFiles: [] as CoreFileSummary[],
    workspaceStreamDocuments: [] as GeneratedDocument[],
    workspaceStreamMockMode: null as boolean | null,
  }),
  actions: {
    setWorkspaceAnalysisResult(result: AnalyzeRepoResponse) {
      this.workspaceAnalysisResult = result
      this.workspaceFailureSteps = []
      this.workspaceFailureToolLogs = []
      this.workspaceInputError = ''
      this.workspaceSelectedDocPath = result.documents[0]?.path ?? null
      this.workspaceIsAnalyzing = false
      this.workspaceCurrentJobId = null
    },
    setWorkspaceFailure(message: string, steps: AgentStep[], toolLogs: ToolCallLog[]) {
      this.workspaceAnalysisResult = null
      this.workspaceFailureSteps = steps
      this.workspaceFailureToolLogs = toolLogs
      this.workspaceInputError = message
      this.workspaceSelectedDocPath = null
      this.workspaceIsAnalyzing = false
      this.workspaceCurrentJobId = null
    },
    clearWorkspaceAnalysis() {
      this.workspaceInputError = ''
      this.workspaceAnalysisResult = null
      this.workspaceFailureSteps = []
      this.workspaceFailureToolLogs = []
      this.workspaceSelectedDocPath = null
      this.clearWorkspaceStreaming()
    },
    resetWorkspaceStreaming() {
      this.workspaceLastEventSequence = 0
      this.workspaceStreamStatusText = ''
      this.workspaceStreamFileTree = []
      this.workspaceStreamCoreFiles = []
      this.workspaceStreamDocuments = []
      this.workspaceStreamMockMode = null
    },
    clearWorkspaceStreaming() {
      this.workspaceIsAnalyzing = false
      this.workspaceCurrentJobId = null
      this.resetWorkspaceStreaming()
    },
  },
})
