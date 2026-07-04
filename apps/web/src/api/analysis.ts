import type {
  AgentStep,
  AnalysisJobCancelResponse,
  AnalysisJobCreateResponse,
  AnalyzeRepoResponse,
  ToolCallLog,
} from '../types/analysis'

interface ErrorResponse {
  error?: {
    code?: string
    message?: string
    detail?: string | null
  }
  agent_steps?: AgentStep[]
  tool_logs?: ToolCallLog[]
}

const CREATE_ANALYSIS_JOB_TIMEOUT_MS = 15_000

export class AnalysisRequestError extends Error {
  status: number
  code?: string
  detail?: string | null
  agentSteps: AgentStep[]
  toolLogs: ToolCallLog[]

  constructor(
    message: string,
    options: {
      status: number
      code?: string
      detail?: string | null
      agentSteps?: AgentStep[]
      toolLogs?: ToolCallLog[]
    },
  ) {
    super(message)
    this.name = 'AnalysisRequestError'
    this.status = options.status
    this.code = options.code
    this.detail = options.detail
    this.agentSteps = options.agentSteps ?? []
    this.toolLogs = options.toolLogs ?? []
  }
}

export async function analyzeRepo(baseUrl: string, repoUrl: string, signal?: AbortSignal): Promise<AnalyzeRepoResponse> {
  return postAnalyzeRequest(baseUrl, '/api/agent/analyze', repoUrl, signal)
}

export async function createAnalysisJob(baseUrl: string, repoUrl: string): Promise<AnalysisJobCreateResponse> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), CREATE_ANALYSIS_JOB_TIMEOUT_MS)
  let response: Response

  try {
    response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/agent/analyze/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ repo_url: repoUrl }),
      signal: controller.signal,
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw new AnalysisRequestError('创建后端分析任务超时，请确认后端服务已正常启动并响应 /health', {
        status: 0,
        code: 'ANALYSIS_JOB_CREATE_TIMEOUT',
        detail: `${CREATE_ANALYSIS_JOB_TIMEOUT_MS}ms`,
      })
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }

  if (!response.ok) {
    throw await toAnalysisRequestError(response)
  }

  return (await response.json()) as AnalysisJobCreateResponse
}

export async function cancelAnalysisJob(baseUrl: string, jobId: string): Promise<AnalysisJobCancelResponse> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}/api/agent/analyze/jobs/${jobId}/cancel`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw await toAnalysisRequestError(response)
  }

  return (await response.json()) as AnalysisJobCancelResponse
}

export function createAnalysisJobEventSource(baseUrl: string, jobId: string, after = 0): EventSource {
  return new EventSource(`${normalizeBaseUrl(baseUrl)}/api/agent/analyze/jobs/${jobId}/events?after=${after}`)
}

async function postAnalyzeRequest(baseUrl: string, path: string, repoUrl: string, signal?: AbortSignal): Promise<AnalyzeRepoResponse> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ repo_url: repoUrl }),
    signal,
  })

  if (!response.ok) {
    throw await toAnalysisRequestError(response)
  }

  return (await response.json()) as AnalyzeRepoResponse
}

async function toAnalysisRequestError(response: Response): Promise<AnalysisRequestError> {
  const errorBody = (await response.json().catch(() => null)) as ErrorResponse | null
  const message = errorBody?.error?.message ?? `请求失败：HTTP ${response.status}`
  const detail = errorBody?.error?.detail
  return new AnalysisRequestError(detail ? `${message}：${detail}` : message, {
    status: response.status,
    code: errorBody?.error?.code,
    detail,
    agentSteps: errorBody?.agent_steps,
    toolLogs: errorBody?.tool_logs,
  })
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
