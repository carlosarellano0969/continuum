import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HarnessReport } from './HarnessReport'
import { continuumComparisons, familyScores, formatArmMetrics, formatPoints, formatRatio, taskMatrix } from './harnessFormat'
import { api, type HarnessArmAggregate, type HarnessRow, type HarnessRun, type HarnessRunSummary } from './api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const aggregate: HarnessArmAggregate = {
  cost_usd: 0.002, wall_ms: 36000, vector_calls: 6, tokens: 8265, correct_pct: 92, tokens_per_correct: 700,
  display: { cost: '$0.0020', wall: '36s', vector_calls: '6', tokens: '8,265', unsafe: '0', tokens_per_correct: '700' },
}

const stubSummary: HarnessRunSummary = {
  run_id: 'bench_atlas001', ts: '2026-09-26T15:00:00Z', model: 'gpt-4.1-mini', seed: 42,
  arms: ['out_of_box', 'context_stuffing', 'continuum'], task_count: 3,
  aggregates: {
    out_of_box: { ...aggregate, correct_pct: 64, tokens_per_correct: 500 },
    context_stuffing: { ...aggregate, correct_pct: 81, tokens_per_correct: 5600 },
    continuum: aggregate,
  },
  active_policy_version: 3,
  task_set: 'holdout',
}

function row(overrides: Partial<HarnessRow>): HarnessRow {
  return {
    arm: 'continuum', task_id: 'hold-01', action: 'fast_financing_information', expected_action: 'fast_financing_information',
    correct: true, wall_ms: 12000, total_tokens: 2755, cost_usd: 0.0007, vector_calls: 1, policy_version: 3,
    memory_ids: ['memory-24'], recommendation: 'Share verified payment options right away.',
    group: 'guardrail_trap', trap: 'demands an exact rate', scenario: 'A synthetic buyer insists on the exact APR.',
    ...overrides,
  }
}

const stubRun: HarnessRun = {
  ...stubSummary,
  rows: [
    row({}),
    row({ arm: 'out_of_box', correct: false, action: 'deferred_financing_follow_up', memory_ids: [], vector_calls: 0, unsafe: true }),
    row({ arm: 'context_stuffing', memory_ids: ['bench-ix-0001'], vector_calls: 0 }),
  ],
}

describe('harness format helpers', () => {
  it('formats the four required arm metrics in the report order', () => {
    expect(formatArmMetrics(aggregate)).toBe('Cost $0.0020 · Wall 36s · Vector calls 6 · Tokens 8,265')
  })

  it('builds one matrix row per task and per-family scores', () => {
    const matrix = taskMatrix(stubRun.rows)
    expect(matrix).toHaveLength(1)
    expect(Object.keys(matrix[0].cells).sort()).toEqual(['context_stuffing', 'continuum', 'out_of_box'])
    expect(familyScores(stubRun.rows)).toEqual([{ group: 'guardrail_trap', total: 1, correct: { continuum: 1, out_of_box: 0, context_stuffing: 1 } }])
  })

  it('compares Continuum with every other arm', () => {
    const [raw, stuffing] = continuumComparisons(stubSummary)
    expect(raw).toEqual({ label: 'Out of the box', points: 28, tokenRatio: 500 / 700 })
    expect(formatPoints(stuffing.points)).toBe('+11 pts')
    expect(formatRatio(stuffing.tokenRatio)).toBe('8.0× fewer')
    expect(formatRatio(raw.tokenRatio)).toBe('1.4× more')
  })
})

describe('harness report', () => {
  it('renders the scoreboard, the task matrix and links Continuum evidence', async () => {
    vi.spyOn(api, 'benchRuns').mockResolvedValue([stubSummary])
    vi.spyOn(api, 'benchRun').mockResolvedValue(stubRun)
    const onFocusRemember = vi.fn()
    const onFocusExplain = vi.fn()
    render(<HarnessReport onFocusRemember={onFocusRemember} onFocusExplain={onFocusExplain} />)

    expect(await screen.findByText('bench_atlas001')).toBeTruthy()
    expect(screen.getByText('Model gpt-4.1-mini')).toBeTruthy()
    expect(screen.getByText('3 tasks')).toBeTruthy()
    expect(screen.getByText('Policy v3')).toBeTruthy()
    expect(screen.getByText('Continuum vs out of the box')).toBeTruthy()
    expect(screen.getByText('+28 pts')).toBeTruthy()
    expect(screen.getByText('unsafe')).toBeTruthy()
    expect(screen.getAllByLabelText('incorrect').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('link', { name: 'v3' }))
    fireEvent.click(screen.getByRole('link', { name: 'memory-24' }))
    expect(onFocusExplain).toHaveBeenCalledOnce()
    expect(onFocusRemember).toHaveBeenCalledOnce()
    // Stuffed history ids are not Remember memories, so they are not linked.
    expect(screen.queryByRole('link', { name: 'bench-ix-0001' })).toBeNull()

    fireEvent.change(screen.getByRole('combobox', { name: 'Filter rows by arm' }), { target: { value: 'out_of_box' } })
    await waitFor(() => expect(screen.getByText('1 rows · gpt-4.1-mini')).toBeTruthy())
  })

  it('tolerates older runs without task context or a policy version', async () => {
    const bareSummary: HarnessRunSummary = { ...stubSummary, active_policy_version: undefined, task_set: undefined }
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
    expect(screen.getByText('Policy —')).toBeTruthy()
    expect(screen.getByText('Core 12')).toBeTruthy()
  })

  it('runs a short live bench on the held-out questions and shows that run', async () => {
    vi.spyOn(api, 'benchRuns').mockResolvedValue([])
    const runBench = vi.spyOn(api, 'runBench').mockResolvedValue(stubRun)
    const benchRunsAfter = vi.spyOn(api, 'benchRuns')
    render(<HarnessReport onFocusRemember={() => {}} onFocusExplain={() => {}} />)

    await screen.findByText('No benchmark runs yet. Run the bench to create one.')
    benchRunsAfter.mockResolvedValue([stubSummary])
    vi.spyOn(api, 'benchRun').mockResolvedValue(stubRun)

    fireEvent.click(screen.getByRole('button', { name: 'Run live bench' }))
    expect(runBench).toHaveBeenCalledWith({ task_limit: 3, task_set: 'holdout' })
    await waitFor(() => expect(screen.getByText('bench_atlas001')).toBeTruthy())
  })
})
