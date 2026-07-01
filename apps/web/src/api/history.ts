import type { HistoryRecord } from '../types/history'

interface HistoryListResponse {
  records: HistoryRecord[]
}

export async function fetchHistoryRecords(baseUrl: string): Promise<HistoryRecord[]> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/history`)
  if (!response.ok) {
    throw new Error(`历史记录读取失败：HTTP ${response.status}`)
  }
  const payload = (await response.json()) as HistoryListResponse
  return payload.records
}

export async function deleteHistoryRecord(baseUrl: string, recordId: string): Promise<void> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/history/${recordId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(`历史记录删除失败：HTTP ${response.status}`)
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}
