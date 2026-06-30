export interface FileTreeNode {
  name: string
  path: string
  type: 'directory' | 'file' | string
  children: FileTreeNode[]
}

export interface BasicFileSummary {
  path: string
  file_type: string
  size: number
  content_preview: string
  truncated: boolean
}

export interface CoreFileSummary {
  path: string
  file_type: string
  size: number
  content_preview: string
  truncated: boolean
  reason: string
  read_status: string
  used_for_context: boolean
}

export interface AgentStep {
  title: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' | string
  description: string
  started_at: string
  ended_at: string
  error_message?: string | null
}

export interface ToolCallLog {
  tool_name: string
  status: 'success' | 'failed' | 'info' | string
  input_summary: string
  output_summary: string
  duration_ms: number
  created_at: string
  error_message?: string | null
}

export interface GeneratedDocument {
  title: string
  filename: string
  path: string
  content: string
}

export interface MockAnalysisMetrics {
  candidate_core_files: number
  selected_core_files: number
  read_files: number
  truncated_files: number
  raw_candidate_chars: number
  final_context_chars: number
  context_compression_ratio: number
  mock_doc_count: number
  mock_doc_total_chars: number
  analysis_duration_ms: number
}

export interface AnalyzeRepoResponse {
  owner: string
  repo: string
  repo_url: string
  file_tree: FileTreeNode[]
  basic_files: BasicFileSummary[]
  core_files: CoreFileSummary[]
  agent_steps: AgentStep[]
  tool_logs: ToolCallLog[]
  documents: GeneratedDocument[]
  docs_dir: string
  metrics: MockAnalysisMetrics
  mock_mode: boolean
}

export type MockAnalyzeResponse = AnalyzeRepoResponse
