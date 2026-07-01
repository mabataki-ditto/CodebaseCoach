export interface HistoryRecord {
  id: string
  repo_url: string
  owner: string
  repo: string
  status: 'success' | 'failed' | string
  created_at: string
  completed_at: string | null
  docs_dir: string
  core_files_count: number
  error_message?: string | null
  mock_mode: boolean
}
