import type { GeneratedDocument } from '../types/analysis'

export interface DocsResponse {
  history_id: string
  docs_dir: string
  documents: GeneratedDocument[]
}

export async function fetchDocsByHistoryId(baseUrl: string, historyId: string): Promise<DocsResponse> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/docs/${historyId}`)
  if (!response.ok) {
    throw new Error(`文档读取失败：HTTP ${response.status}`)
  }
  return (await response.json()) as DocsResponse
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}
