import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HarnessReport, formatArmMetrics } from './HarnessReport'
import { api, type HarnessArm, type HarnessRun } from './api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const arm: HarnessArm = {
  arm: 'continuum', cost_usd: 0.26, wall_ms: 175000, vector_calls: 5, tokens: 4251, correct_pct: 92,
  display: { cost: '$0.26', wall: '2m 55s', vector_calls: '5', tokens: '4,251' },
}

const stubRun: HarnessRun = {
  run_id: 'atlas-run-001', ts: '2026-09-26T15:00:00Z', model: 'gpt-4.1-mini', seed: 42,
  arms: [
    { ...arm, arm: 'out_of_box', correct_pct: 64 },
    { ...arm, arm: 'context_stuffing', correct_pct: 81 },
    arm,
  ],
  rows: [{
    arm: 'continuum', task_id: 'task-07', action: 'Offer verified option', expected_action: 'Offer verified option', correct: true,
    wall_ms: 175000, total_tokens: 4251, cost_usd: 0.26, vector_calls: 5, policy_version: 3, memory_ids: ['memory-24'],
  }],
  traces: [{ fallback: true }],
}

describe('harness report', () => {
  it('formats the four required arm metrics in the report order', () => {
    expect(formatArmMetrics(arm)).toBe('Cost $0.26 · Wall 2m 55s · Vector calls 5 · Tokens 4,251')
  })

  it('renders the stub run and links its evidence to the existing panels', async () => {
    vi.spyOn(api, 'benchRuns').mockResolvedValue([stubRun])
    const onFocusRemember = vi.fn()
    const onFocusExplain = vi.fn()
    render(<HarnessReport health={{ services: { mongodb: 'ok' }, models: { chat: 'gpt-4.1-mini', embedding: 'voyage-4-large' } }} onFocusRemember={onFocusRemember} onFocusExplain={onFocusExplain} />)

    expect(await screen.findByText('Atlas document')).toBeTruthy()
    expect(screen.getByText('atlas-run-001')).toBeTruthy()
    expect(screen.getByText('OpenRouter gpt-4.1-mini')).toBeTruthy()
    expect(screen.getByText('voyage-4-large')).toBeTruthy()
    expect(screen.getByText('Fallback')).toBeTruthy()
    expect(screen.getAllByText('Cost $0.26 · Wall 2m 55s · Vector calls 5 · Tokens 4,251')).toHaveLength(3)
    fireEvent.click(screen.getByRole('link', { name: 'v3' }))
    fireEvent.click(screen.getByRole('link', { name: 'memory-24' }))
    expect(onFocusExplain).toHaveBeenCalledOnce()
    expect(onFocusRemember).toHaveBeenCalledOnce()
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter rows by arm' }), { target: { value: 'out_of_box' } })
    await waitFor(() => expect(screen.getByText('0 rows · gpt-4.1-mini')).toBeTruthy())
  })
})
