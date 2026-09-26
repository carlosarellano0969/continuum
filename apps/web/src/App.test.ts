import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { dependencyNotice } from './dependencyNotice'
import { toolTraceRows } from './toolTrace'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('dependency status presentation', () => {
  it('explains intentional local-only mode without implying an Atlas fallback', () => {
    expect(dependencyNotice({ api: 'ok', mongodb: 'unconfigured', ollama: 'ok', embedding_model: 'ok', chat_model: 'ok' })).toBe(
      'Local-only mode. MongoDB Atlas is not configured; deterministic storage is active.',
    )
  })

  it('distinguishes configured Atlas degradation from local-only mode', () => {
    expect(dependencyNotice({ api: 'ok', mongodb: 'degraded', ollama: 'ok', embedding_model: 'ok', chat_model: 'ok' })).toContain(
      'Atlas connectivity is degraded',
    )
  })
})

describe('tool trace presentation', () => {
  it('makes fallback execution provenance explicit', () => {
    expect(toolTraceRows([{
      retrieval_backend: 'deterministic-memory-repository',
      model: 'nomic-embed-text:latest',
      status: 'degraded',
      fallback: true,
      fallback_reason: 'Atlas is unconfigured',
    }])).toEqual([{
      backend: 'deterministic-memory-repository',
      model: 'nomic-embed-text:latest',
      status: 'degraded',
      fallbackReason: 'Atlas is unconfigured',
    }])
  })

  it('does not silently imply a fallback when the API has not recorded one', () => {
    expect(toolTraceRows([{ tool: 'retrieve_memories', status: 'ok' }])[0]).toMatchObject({
      backend: 'retrieve_memories', model: 'not reported', status: 'ok', fallbackReason: 'No fallback recorded.',
    })
  })
})

describe('V1.1 single-page workspace', () => {
  it('renders all four evidence-loop panels together', async () => {
    const responses: Record<string, unknown> = {
      '/api/health': {
        status: 'degraded', version: 'v1',
        services: { api: 'ok', mongodb: 'unconfigured', ollama: 'ok', embedding_model: 'ok', chat_model: 'ok' },
      },
      '/api/demo/summary': { counts: {}, active_policy: null, pending_proposal: null, latest_decision: null },
      '/api/memories?limit=20': { items: [], total: 0 },
      '/api/policies': { active: null, history: [] },
      '/api/proposals': { items: [] },
      '/api/audit-events?limit=12': { items: [] },
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const key = String(input)
      return new Response(JSON.stringify(responses[key]), { status: responses[key] ? 200 : 404 })
    }))

    render(createElement(App))

    expect(await screen.findByRole('heading', { name: 'Ask with evidence' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Understand the change' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Inspect the evidence' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Approve policy change' })).toBeTruthy()
    expect(document.querySelectorAll('.workspace-panel')).toHaveLength(4)
    expect(screen.getByRole('navigation', { name: 'Evidence loop' }).querySelectorAll('a')).toHaveLength(4)
  })

  it('loads the latest explanation in place and focuses its panel', async () => {
    const responses: Record<string, unknown> = {
      '/api/health': {
        status: 'degraded', version: 'v1',
        services: { api: 'ok', mongodb: 'unconfigured', ollama: 'ok', embedding_model: 'ok', chat_model: 'ok' },
      },
      '/api/demo/summary': { counts: {}, active_policy: null, pending_proposal: null, latest_decision: { id: 'dec-1', policy_version: 1, recommendation: 'Recorded result' } },
      '/api/memories?limit=20': { items: [], total: 0 },
      '/api/policies': { active: null, history: [] },
      '/api/proposals': { items: [] },
      '/api/audit-events?limit=12': { items: [] },
      '/api/decisions/dec-1/explanation': {
        decision_id: 'dec-1', summary: 'Verified explanation loaded in the persistent panel.', before: null, after: null,
        policy_chain: [], memories: [], outcomes: [], approval: null, audit_event_ids: [],
      },
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const key = String(input)
      return new Response(JSON.stringify(responses[key]), { status: responses[key] ? 200 : 404 })
    }))

    render(createElement(App))
    fireEvent.click(await screen.findByRole('button', { name: 'Inspect latest decision' }))

    expect(await screen.findByText('Verified explanation loaded in the persistent panel.')).toBeTruthy()
    await waitFor(() => expect(document.activeElement?.id).toBe('explain-title'))
    expect(document.querySelectorAll('.workspace-panel')).toHaveLength(4)
  })

  it('locks policy decisions while a recommendation is running', async () => {
    const policy = {
      id: 'policy-1', logical_policy_id: 'pricing', organization_id: 'demo-org', agent_id: 'demo-agent',
      version: 1, status: 'active', rule: 'Use verified information.', risk: 'medium', evidence_ids: [], approval: null,
      created_at: '2026-09-24T13:00:00Z',
    }
    const proposal = {
      id: 'proposal-1', state: 'pending', current_rule: policy.rule, proposed_rule: 'Respond faster with verified information.',
      evidence: [], expected_effect: 'Faster grounded replies.', confidence: 0.8, risk: 'medium', approval_required: true,
      created_at: '2026-09-24T13:05:00Z', decided_at: null,
    }
    const responses: Record<string, unknown> = {
      '/api/health': {
        status: 'degraded', version: 'v1',
        services: { api: 'ok', mongodb: 'unconfigured', ollama: 'ok', embedding_model: 'ok', chat_model: 'ok' },
      },
      '/api/demo/summary': { counts: {}, active_policy: policy, pending_proposal: proposal, latest_decision: null },
      '/api/memories?limit=20': { items: [], total: 0 },
      '/api/policies': { active: policy, history: [policy] },
      '/api/proposals': { items: [proposal] },
      '/api/audit-events?limit=12': { items: [] },
    }
    const unresolvedRecommendation = new Promise<Response>(() => undefined)
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const key = String(input)
      if (key === '/api/recommendations') return unresolvedRecommendation
      return Promise.resolve(new Response(JSON.stringify(responses[key]), { status: responses[key] ? 200 : 404 }))
    }))

    render(createElement(App))
    const approve = await screen.findByRole('button', { name: 'Approve change' })
    fireEvent.click(screen.getByRole('button', { name: 'Generate recommendation' }))

    await waitFor(() => expect((approve as HTMLButtonElement).disabled).toBe(true))
    expect(screen.getByRole('button', { name: 'Reasoning…' })).toBeTruthy()
  })
})
