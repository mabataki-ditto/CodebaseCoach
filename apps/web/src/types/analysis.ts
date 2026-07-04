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

export interface CoreFileCandidateMetric {
  path: string
  file_type: string
  size: number
  reason: string
  score: number
  truncated: boolean
}

export interface ContextDirectoryCoverage {
  directory: string
  selected_file_count: number
}

export interface ContextSelectionReasonCount {
  reason: string
  selected_file_count: number
}

export interface ContextQualityReport {
  candidate_file_count: number
  selected_file_count: number
  omitted_candidate_count: number
  context_char_count: number
  raw_candidate_chars: number
  compression_ratio: number
  truncated_selected_file_count: number
  budget_limit_reached: boolean
  selected_files: string[]
  directory_coverage: ContextDirectoryCoverage[]
  selection_reasons: ContextSelectionReasonCount[]
  omitted_candidates: CoreFileCandidateMetric[]
  notes: string[]
}

export interface AgentStep {
  step_id: string
  id: string
  key: string
  title: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' | string
  description: string
  started_at: string | null
  ended_at: string | null
  completed_at: string | null
  duration_ms: number
  error_message?: string | null
  metadata: Record<string, unknown>
}

export interface ToolCallLog {
  id: string
  tool_provider: string
  tool_name: string
  permission: 'read' | 'network' | 'llm' | 'write' | 'command' | 'delete' | string
  requires_confirmation: boolean
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  status: 'running' | 'success' | 'failed' | 'skipped' | 'info' | string
  input_summary: string
  output_summary: string
  input: Record<string, unknown>
  output: Record<string, unknown>
  related_files: string[]
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

export interface GeneratedDocumentEvaluation {
  filename: string
  title: string
  has_title: boolean
  char_count: number
  referenced_file_paths: string[]
  valid_referenced_file_paths: string[]
  invalid_referenced_file_paths: string[]
  placeholder_hits: string[]
  issues: string[]
}

export interface GeneratedResultEvaluation {
  document_count: number
  evaluated_document_count: number
  textcitation_score: number
  coverage_score: number
  hallucination_risk: number
  usefulness_score: number
  valid_reference_count: number
  invalid_reference_count: number
  referenced_context_file_count: number
  context_file_count: number
  interview_question_count: number
  interview_question_target: number
  document_evaluations: GeneratedDocumentEvaluation[]
  issues: string[]
}

export interface MockAnalysisMetrics {
  total_files: number
  ignored_dirs: number
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
  agent_step_count: number
  agent_success_step_count: number
  agent_failed_step_count: number
  agent_skipped_step_count: number
  llm_input_tokens: number
  llm_output_tokens: number
  llm_total_tokens: number
  tool_call_count: number
  tool_success_count: number
  tool_failed_count: number
  avg_tool_duration_ms: number
  max_tool_duration_ms: number
  total_tool_duration_ms: number
}

export interface AnalyzeRepoResponse {
  owner: string
  repo: string
  repo_url: string
  file_tree: FileTreeNode[]
  basic_files: BasicFileSummary[]
  core_files: CoreFileSummary[]
  context_quality_report: ContextQualityReport
  agent_steps: AgentStep[]
  tool_logs: ToolCallLog[]
  documents: GeneratedDocument[]
  result_evaluation: GeneratedResultEvaluation
  docs_dir: string
  metrics: MockAnalysisMetrics
  mock_mode: boolean
}


export type AnalysisJobStatus = 'queued' | 'running' | 'success' | 'failed' | 'cancelled' | string

export type AnalysisEventType =
  | 'job_started'
  | 'stage_started'
  | 'stage_completed'
  | 'stage_failed'
  | 'metrics_updated'
  | 'document_generated'
  | 'job_completed'
  | 'job_failed'
  | 'job_cancelled'

export interface AnalysisJobCreateResponse {
  job_id: string
  status: AnalysisJobStatus
}

export interface AnalysisJobCancelResponse {
  job_id: string
  status: AnalysisJobStatus
}

export interface AnalysisEvent {
  id: string
  job_id: string
  type: AnalysisEventType
  payload: Record<string, unknown>
  created_at: string
  sequence: number
}
