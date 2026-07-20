import { defineStore } from 'pinia'
import type {
  AgentStep,
  AnalysisJobSnapshot,
  AnalysisRecoveryMode,
  AnalyzeRepoResponse,
  CoreFileSummary,
  FileTreeNode,
  GeneratedDocument,
  ToolCallLog,
} from '../types/analysis'

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
    prepareWorkspaceResume(snapshot: AnalysisJobSnapshot, recoveryMode: AnalysisRecoveryMode) {
      this.workspaceRepoInput = snapshot.job.repo_url
      this.workspaceInputError = ''
      this.workspaceAnalysisResult = snapshot.result
      this.workspaceFailureSteps = []
      this.workspaceFailureToolLogs = []
      this.workspaceCurrentJobId = snapshot.job.id
      this.workspaceIsAnalyzing = true
      this.workspaceLastEventSequence = Math.max(0, ...snapshot.events.map((event) => event.sequence))
      if (snapshot.file_tree.length) this.workspaceStreamFileTree = snapshot.file_tree
      if (snapshot.core_files.length) this.workspaceStreamCoreFiles = snapshot.core_files
      if (snapshot.documents.length) this.workspaceStreamDocuments = snapshot.documents
      this.workspaceStreamMockMode = snapshot.job.mock_mode
      this.workspaceStreamStatusText = recoveryMode === 'checkpoint'
        ? '正在从最近的运行存档继续任务'
        : recoveryMode === 'rebuild_repository'
          ? '临时仓库已被清理，正在重新克隆后继续任务'
          : '仓库版本需要重新确认，将重新生成文档以保证一致性'
      if (
        this.workspaceStreamDocuments.length
        && !this.workspaceStreamDocuments.some((document) => document.path === this.workspaceSelectedDocPath)
      ) {
        this.workspaceSelectedDocPath = this.workspaceStreamDocuments[0].path
      }
    },
    clearWorkspaceStreaming() {
      this.workspaceIsAnalyzing = false
      this.workspaceCurrentJobId = null
      this.resetWorkspaceStreaming()
    },
  },
})
