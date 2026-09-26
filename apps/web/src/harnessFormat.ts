import type { HarnessArmAggregate, HarnessArmName, HarnessRow, HarnessRunSummary } from './api'

export const ARM_ORDER: HarnessArmName[] = ['out_of_box', 'context_stuffing', 'continuum']

export const armLabels: Record<HarnessArmName, string> = {
  out_of_box: 'Out of the box',
  context_stuffing: 'Context stuffing',
  continuum: 'Continuum',
}

// A short live run so it fits inside a serverless function's time limit.
export const LIVE_RUN_TASK_LIMIT = 3
export const RECOMMENDATION_TRUNCATE_LENGTH = 80

export function formatArmMetrics(aggregate: HarnessArmAggregate) {
  return `Cost ${aggregate.display.cost} · Wall ${aggregate.display.wall} · Vector calls ${aggregate.display.vector_calls} · Tokens ${aggregate.display.tokens}`
}

export function formatArmQuality(aggregate: HarnessArmAggregate) {
  const unsafe = aggregate.display.unsafe ?? String(aggregate.unsafe_count ?? 0)
  const perCorrect = aggregate.display.tokens_per_correct ?? '—'
  return `Unsafe answers ${unsafe} · Tokens per correct answer ${perCorrect}`
}

export function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text
}

// Bench rows carry raw cost, not the pre-formatted `display` strings the
// aggregates get, so mirror the API's own rounding (bench.py `format_cost`):
// fractions of a cent need 4 decimals or they all collapse to "$0.00".
export function formatRowCost(value: number) {
  if (value !== 0 && Math.abs(value) < 0.01) return `$${value.toFixed(4)}`
  return `$${value.toFixed(2)}`
}

// `active_policy_version` arrives with a follow-up PR; until then, fall back
// to a row's `policy_version` (preferring the continuum arm, which is the
// only one that carries a real policy).
export function resolvePolicyVersion(run: HarnessRunSummary | null, rows: HarnessRow[]): string | number | null {
  if (run?.active_policy_version != null) return run.active_policy_version
  const withVersion = rows.find((row) => row.arm === 'continuum' && row.policy_version != null) ?? rows.find((row) => row.policy_version != null)
  return withVersion?.policy_version ?? null
}
