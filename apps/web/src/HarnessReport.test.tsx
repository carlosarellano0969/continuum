import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HarnessReport } from './HarnessReport'
import { formatArmMetrics } from './harnessFormat'
import { api, type HarnessArmAggregate, type HarnessRun, type HarnessRunSummary } from './api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const aggregate: HarnessArmAggregate = {
  cost_usd: 0.002, wall_ms: 36000, vector_calls: 6, tokens: 8265, correct_pct: 92,
  display: { cost: '$0.0020', wall: '36s', vector_calls: '6', tokens: '8,265' },
}

const stubSummary: HarnessRunSummary = {
  run_id: 'bench_atlas001', ts: '2026-09-26T15:00:00Z', model: 'gpt-4.1-mini', seed: 42,
  arms: ['out_of_box', 'context_stuffing', 'continuum'], task_count: 3,
  aggregates: {
    out_of_box: { ...aggregate, correct_pct: 64 },
    context_stuffing: { ...aggregate, correct_pct: 81 },
    continuum: aggregate,
  },
  active_policy_version: 3,
}

const stubRun: HarnessRun = {
  ...stubSummary,
  rows: [{
    arm: 'continuum', task_id: 'task-07', action: 'offer_verified_option', expected_action: 'offer_verified_option',
    correct: true, wall_ms: 12000, total_tokens: 2755, cost_usd: 0.0007, vector_calls: 2, policy_version: 3,
    memory_ids: ['memory-24'], recommendation: 'Offer the verified financing option that matches the customer profile on file.',
  }],
}

describe('harness report', () => {
  it('formats the four required arm metrics in the report order', () => {
    expect(formatArmMetrics(aggregate)).toBe('Cost $0.0020 · Wall 36s · Vector calls 6 · Tokens 8,265')
  })

  it('renders the latest run and links its evidence to the existing panels', async () => {
    vi.spyOn(api, 'benchRuns').mockResolvedValue([stubSummary])
    vi.spyOn(api, 'benchRun').mockResolvedValue(stubRun)
    const onFocusRemember = vi.fn()
    const onFocusExplain = vi.fn()
    render(<HarnessReport onFocusRemember={onFocusRemember} onFocusExplain={onFocusExplain} />)

    expect(await screen.findByText('bench_atlas001')).toBeTruthy()
    expect(screen.getByText('Model gpt-4.1-mini')).toBeTruthy()
    expect(screen.getByText('3 tasks')).toBeTruthy()
    expect(screen.getByText('Policy v3')).toBeTruthy()
    expect(screen.getAllByText('Cost $0.0020 · Wall 36s · Vector calls 6 · Tokens 8,265')).toHaveLength(3)

    fireEvent.click(screen.getByRole('link', { name: 'v3' }))
    fireEvent.click(screen.getByRole('link', { name: 'memory-24' }))
    expect(onFocusExplain).toHaveBeenCalledOnce()
    expect(onFocusRemember).toHaveBeenCalledOnce()

    fireEvent.change(screen.getByRole('combobox', { name: 'Filter rows by arm' }), { target: { value: 'out_of_box' } })
    await waitFor(() => expect(screen.getByText('0 rows · gpt-4.1-mini')).toBeTruthy())
  })

  it('tolerates rows and documents missing the not-yet-merged fields', async () => {
    const bareSummary: HarnessRunSummary = { ...stubSummary, active_policy_version: undefined }
    const bareRun: HarnessRun = {
      ...bareSummary,
      rows: [{
        arm: 'out_of_box', task_id: 'task-01', action: 'none_detected', expected_action: 'offer_verified_option',
        correct: false, wall_ms: 500, total_tokens: 120, cost_usd: 0.0001, vector_calls: 0, policy_version: null,
        memory_ids: [],
      }],
    }
    vi.spyOn(api, 'benchRuns').mockResolvedValue([bareSummary])
    vi.spyOn(api, 'benchRun').mockResolvedValue(bareRun)
    render(<HarnessReport onFocusRemember={() => {}} onFocusExplain={() => {}} />)

    expect(await screen.findByText('bench_atlas001')).toBeTruthy()
    // Falls back to a row's policy_version when active_policy_version is absent,
    // but this bare row has none either, so it renders the placeholder.
    expect(screen.getByText('Policy —')).toBeTruthy()
  })

  it('runs a short live bench and refreshes the report', async () => {
    vi.spyOn(api, 'benchRuns').mockResolvedValue([])
    const runBench = vi.spyOn(api, 'runBench').mockResolvedValue(stubRun)
    const benchRunsAfter = vi.spyOn(api, 'benchRuns')
    render(<HarnessReport onFocusRemember={() => {}} onFocusExplain={() => {}} />)

    await screen.findByText('No benchmark runs yet. Run the bench to create one.')
    benchRunsAfter.mockResolvedValue([stubSummary])
    vi.spyOn(api, 'benchRun').mockResolvedValue(stubRun)

    fireEvent.click(screen.getByRole('button', { name: 'Run live bench' }))
    expect(runBench).toHaveBeenCalledWith({ task_limit: 3 })
    await waitFor(() => expect(screen.getByText('bench_atlas001')).toBeTruthy())
  })
})
