export type DependencyState = 'ok' | 'degraded' | 'unconfigured'

export interface ApiErrorShape { detail: string }

export interface Health {
  status: DependencyState
  version: string
  services: Record<'api' | 'mongodb' | 'ollama' | 'embedding_model' | 'chat_model', DependencyState>
  models?: { embedding: string | null; chat: string | null }
}

export interface Memory {
  id: string
  organization_id: string
  agent_id: string
  content: string
  type: string
  provenance: string
  confidence: number
  status: string
  supersedes: string | null
  created_at: string
  updated_at: string
  embedding_model: string
  score?: number
}

export interface Policy {
  id: string
  logical_policy_id: string
  organization_id: string
  agent_id: string
  version: number
  status: string
  rule: string
  risk: string
  evidence_ids: string[]
  approval: Record<string, unknown> | null
  created_at: string
}

export interface GuardrailProposal {
  id: string
  state: string
  current_rule: string
  proposed_rule: string
  evidence: string[]
  expected_effect: string
  confidence: number
  risk: string
  approval_required: boolean
  created_at: string
  decided_at: string | null
}

export interface Recommendation {
  decision_id: string
  recommendation: string
  rationale: string
  policy_version: number
  cited_memory_ids: string[]
  tool_trace: Array<Record<string, unknown>>
  latency_ms: number
}

export interface Explanation {
  decision_id: string
  summary: string
  before: Policy | null
  after: Policy | null
  policy_chain: Policy[]
  memories: Memory[]
  outcomes: Array<{ id?: string; result?: string; metrics?: Record<string, unknown>; created_at?: string }>
  approval: Record<string, unknown> | null
  audit_event_ids: string[]
}

export interface AuditEvent {
  id: string
  event_type: string
  created_at: string
  actor?: string
  details?: Record<string, unknown>
  decision_id?: string
}

export interface DemoSummary {
  counts: Record<string, number>
  active_policy: Policy | null
  pending_proposal: GuardrailProposal | null
  latest_decision: { id: string; policy_version: number; recommendation: string } | null
}

export interface DemoResetResult {
  seed: number
  counts: Record<string, number>
  active_policy_version: number
}

export interface ProposalDecisionResult {
  proposal: GuardrailProposal
  policy: Policy | null
}

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
  } catch {
    throw new ApiError('Cannot reach the Continuum API. Start the local service and try again.')
  }

  const body = (await response.json().catch(() => ({}))) as T | ApiErrorShape
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body ? String(body.detail) : `Request failed (${response.status})`
    throw new ApiError(detail, response.status)
  }
  return body as T
}

export const api = {
  health: () => request<Health>('/health'),
  summary: () => request<DemoSummary>('/demo/summary'),
  resetDemo: (seed?: number) => request<DemoResetResult>('/demo/reset', { method: 'POST', body: JSON.stringify({ seed }) }),
  memories: (query = '') => request<{ items: Memory[]; total: number }>(`/memories?limit=20${query ? `&query=${encodeURIComponent(query)}` : ''}`),
  policies: () => request<{ active: Policy | null; history: Policy[] }>('/policies'),
  proposals: () => request<{ items: GuardrailProposal[] }>('/proposals'),
  auditEvents: () => request<{ items: AuditEvent[] }>('/audit-events?limit=12'),
  recommend: (scenario: string) => request<Recommendation>('/recommendations', { method: 'POST', body: JSON.stringify({ scenario }) }),
  explanation: (id: string) => request<Explanation>(`/decisions/${encodeURIComponent(id)}/explanation`),
  decideProposal: (id: string, decision: 'approve' | 'reject', note?: string) =>
    request<ProposalDecisionResult>(`/proposals/${encodeURIComponent(id)}/decision`, {
      method: 'POST', body: JSON.stringify({ decision, actor: 'demo-operator', note }),
    }),
}
