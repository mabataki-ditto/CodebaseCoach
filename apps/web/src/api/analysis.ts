import type { AnalyzeRepoResponse } from '../types/analysis'

interface ErrorResponse {
  error?: {
    code?: string
    message?: string
    detail?: string | null
  }
}

export async function analyzeRepo(baseUrl: string, repoUrl: string): Promise<AnalyzeRepoResponse> {
  return postAnalyzeRequest(baseUrl, '/api/agent/analyze', repoUrl)
}

export async function analyzeRepoWithMock(baseUrl: string, repoUrl: string): Promise<AnalyzeRepoResponse> {
  return postAnalyzeRequest(baseUrl, '/api/agent/analyze/mock', repoUrl)
}

async function postAnalyzeRequest(baseUrl: string, path: string, repoUrl: string): Promise<AnalyzeRepoResponse> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ repo_url: repoUrl }),
  })

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as ErrorResponse | null
    const message = errorBody?.error?.message ?? `请求失败：HTTP ${response.status}`
    const detail = errorBody?.error?.detail
    throw new Error(detail ? `${message}：${detail}` : message)
  }

  return (await response.json()) as AnalyzeRepoResponse
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}
