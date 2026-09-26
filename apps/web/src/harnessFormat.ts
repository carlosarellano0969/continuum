import type { HarnessArmAggregate, HarnessArmName, HarnessRow, HarnessRunSummary } from './api'

export const ARM_ORDER: HarnessArmName[] = ['out_of_box', 'out_of_box_large', 'context_stuffing', 'continuum']

export const armLabels: Record<HarnessArmName, string> = {
  out_of_box: 'Out of the box',
  out_of_box_large: 'Out of the box, larger model',
  context_stuffing: 'Context stuffing',
  continuum: 'Continuum',
}

// What surrounds the model in each arm, in one line.
export const armHarness: Record<HarnessArmName, string> = {
  out_of_box: 'Task only',
  out_of_box_large: 'Task only',
  context_stuffing: 'Task + raw history (~4K tokens)',
  continuum: 'Task + approved policy + 3 Atlas memories + guardrail',
}

export const taskSetLabels: Record<string, string> = { core: 'Core 12', holdout: 'Held-out' }

export const groupLabels: Record<string, string> = {
  financing_pricing: 'Financing',
  pricing_objection: 'Pricing objection',
  distractor_source: 'Partner-lead distractor',
  financing_paraphrase: 'Financing, paraphrased',
  pricing_paraphrase: 'Pricing, paraphrased',
  routine_mixed_source: 'Routine question',
  source_trap_financing: 'Trap: partner lead + financing',
  discount_trap: 'Trap: asks for a discount',
  guardrail_trap: 'Trap: demands exact numbers',
}

export function groupLabel(group?: string | null) {
  if (!group) return '—'
  return groupLabels[group] ?? group.replace(/_/g, ' ')
}

export function presentArms(run: HarnessRunSummary | null): HarnessArmName[] {
  if (!run) return []
  return ARM_ORDER.filter((arm) => run.aggregates[arm] != null)
}

export interface TaskMatrixRow {
  task_id: string
  group?: string | null
  trap?: string | null
  scenario?: string
  expected_action: string
  cells: Partial<Record<HarnessArmName, HarnessRow>>
}

// One row per task, one cell per arm (first repeat wins), in the run's task order.
export function taskMatrix(rows: HarnessRow[]): TaskMatrixRow[] {
  const byTask = new Map<string, TaskMatrixRow>()
  for (const row of rows) {
    let entry = byTask.get(row.task_id)
    if (!entry) {
      entry = { task_id: row.task_id, group: row.group, trap: row.trap, scenario: row.scenario, expected_action: row.expected_action, cells: {} }
      byTask.set(row.task_id, entry)
    }
    if (!entry.cells[row.arm]) entry.cells[row.arm] = row
  }
  return [...byTask.values()]
}

export interface FamilyScore { group: string; total: number; correct: Partial<Record<HarnessArmName, number>> }

export function familyScores(rows: HarnessRow[]): FamilyScore[] {
  const families = new Map<string, FamilyScore>()
  for (const entry of taskMatrix(rows)) {
    const group = entry.group ?? 'ungrouped'
    const family = families.get(group) ?? { group, total: 0, correct: {} }
    family.total += 1
    for (const [arm, cell] of Object.entries(entry.cells) as [HarnessArmName, HarnessRow][]) {
      family.correct[arm] = (family.correct[arm] ?? 0) + (cell.correct ? 1 : 0)
    }
    families.set(group, family)
  }
  return [...families.values()]
}

export interface Comparison { label: string; points: number; tokenRatio: number | null }

// Continuum against each other arm: accuracy difference in points, and how many
// times more tokens the other arm spends per correct answer (null when undefined).
export function continuumComparisons(run: HarnessRunSummary | null): Comparison[] {
  const own = run?.aggregates.continuum
  if (!run || !own) return []
  return ARM_ORDER.filter((arm) => arm !== 'continuum' && run.aggregates[arm]).map((arm) => {
    const other = run.aggregates[arm] as HarnessArmAggregate
    const ownPerCorrect = own.tokens_per_correct ?? 0
    const otherPerCorrect = other.tokens_per_correct ?? 0
    return {
      label: armLabels[arm],
      points: Math.round((own.correct_pct - other.correct_pct) * 10) / 10,
      tokenRatio: ownPerCorrect > 0 && otherPerCorrect > 0 ? otherPerCorrect / ownPerCorrect : null,
    }
  })
}

export function formatPoints(points: number) {
  return `${points > 0 ? '+' : points < 0 ? '−' : '±'}${Math.abs(points)} pts`
}

export function formatRatio(ratio: number | null) {
  if (ratio == null) return '—'
  // ratio = other arm's tokens per correct answer ÷ Continuum's, phrased from Continuum's side.
  return ratio >= 1 ? `${ratio.toFixed(1)}× fewer` : `${(1 / ratio).toFixed(1)}× more`
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
