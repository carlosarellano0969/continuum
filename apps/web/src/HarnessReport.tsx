import { useEffect, useState } from 'react'
import type { HarnessArmName, HarnessRun, HarnessRunSummary, HarnessTaskSet } from './api'
import { api } from './api'
import {
  LIVE_RUN_TASK_LIMIT, RECOMMENDATION_TRUNCATE_LENGTH, armHarness, armLabels, continuumComparisons, familyScores,
  formatArmMetrics, formatPoints, formatRatio, formatRowCost, groupLabel, presentArms, resolvePolicyVersion,
  taskMatrix, taskSetLabels, truncate,
} from './harnessFormat'

export function HarnessReport({ onFocusRemember, onFocusExplain }: {
  onFocusRemember: () => void
  onFocusExplain: () => void
}) {
  const [runs, setRuns] = useState<HarnessRunSummary[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [detail, setDetail] = useState<HarnessRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const [liveSet, setLiveSet] = useState<HarnessTaskSet>('holdout')
  const [armFilter, setArmFilter] = useState<HarnessArmName | 'all'>('all')

  async function loadRuns(preferId?: string) {
    setError('')
    try {
      const list = await api.benchRuns()
      setRuns(list)
      const chosen = list.find((item) => item.run_id === preferId) ?? list[0] ?? null
      setRunId(chosen?.run_id ?? null)
      setDetail(chosen ? await api.benchRun(chosen.run_id) : null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Harness runs could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  async function selectRun(id: string) {
    setRunId(id)
    setError('')
    try {
      setDetail(await api.benchRun(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That run could not be loaded.')
    }
  }

  useEffect(() => {
    const initialLoad = window.setTimeout(() => { void loadRuns() }, 0)
    return () => window.clearTimeout(initialLoad)
  }, [])

  useEffect(() => {
    if (!running) return
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250)
    return () => window.clearInterval(timer)
  }, [running])

  async function startRun() {
    setRunning(true)
    setElapsed(0)
    setError('')
    try {
      const options = liveSet === 'core' ? { task_limit: LIVE_RUN_TASK_LIMIT } : { task_limit: LIVE_RUN_TASK_LIMIT, task_set: liveSet }
      const result = await api.runBench(options)
      await loadRuns(result.run_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The harness run failed.')
    } finally {
      setRunning(false)
    }
  }

  const run: HarnessRunSummary | null = detail ?? runs.find((item) => item.run_id === runId) ?? null
  const rows = detail?.rows ?? []
  const arms = presentArms(run)
  const matrix = taskMatrix(rows)
  const families = familyScores(rows)
  const comparisons = continuumComparisons(run)
  const policyVersion = resolvePolicyVersion(run, rows)
  const visibleRows = rows.filter((row) => armFilter === 'all' || row.arm === armFilter)
  const maxPerCorrect = Math.max(1, ...arms.map((arm) => run?.aggregates[arm]?.tokens_per_correct ?? 0))

  return <>
    <div className="page-heading harness-heading">
      <div>
        <p className="eyebrow">05 · EVALUATE</p>
        <h2 id="harness-title">Harness report</h2>
        <p>The same questions and the same scoring for every arm. One small model (gpt-oss-20b) runs under three harnesses, and a model six times its size runs with none.</p>
      </div>
      <div className="harness-controls">
        <label>Live run
          <select aria-label="Task set for a live run" value={liveSet} onChange={(event) => setLiveSet(event.target.value as HarnessTaskSet)} disabled={running}>
            <option value="holdout">Held-out questions</option>
            <option value="core">Core questions</option>
          </select>
        </label>
        <button className="button primary" onClick={() => void startRun()} disabled={running || loading}>
          {running ? `Running · ${elapsed}s` : 'Run live bench'}
        </button>
      </div>
    </div>
    {error && <p className="harness-error" role="alert">{error}<button className="button secondary" onClick={() => void loadRuns(runId ?? undefined)}>Retry</button></p>}
    {loading ? <div className="loading" role="status">Loading harness runs…</div> : run ? <>
      <div className="harness-run-meta">
        {runs.length > 1 && <label>Run
          <select aria-label="Choose a stored run" value={runId ?? ''} onChange={(event) => void selectRun(event.target.value)}>
            {runs.map((item) => <option key={item.run_id} value={item.run_id}>{`${taskSetLabels[item.task_set ?? 'core'] ?? item.task_set} · ${item.task_count} tasks · ${new Date(item.ts).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`}</option>)}
          </select>
        </label>}
        <span className="harness-set">{taskSetLabels[run.task_set ?? 'core'] ?? run.task_set}</span>
        <span>Model {run.model}</span>
        <span>{run.task_count} tasks</span>
        <span>Policy {policyVersion == null ? '—' : `v${policyVersion}`}</span>
        <span>Run <code>{run.run_id}</code></span>
      </div>

      {comparisons.length > 0 && <div className="harness-callouts" aria-label="Continuum compared with the other arms">
        {comparisons.map((item) => <p key={item.label}>
          <span>Continuum vs {item.label.toLowerCase()}</span>
          <strong className={item.points < 0 ? 'negative' : undefined}>{formatPoints(item.points)}</strong>
          <small>accuracy · {item.tokenRatio == null ? 'tokens per correct answer n/a' : `${formatRatio(item.tokenRatio)} tokens per correct answer`}</small>
        </p>)}
      </div>}

      <div className="harness-cards" aria-label="Benchmark arm summaries">
        {arms.map((arm) => {
          const aggregate = run.aggregates[arm]!
          const correctCount = matrix.filter((entry) => entry.cells[arm]?.correct).length
          const answered = matrix.filter((entry) => entry.cells[arm]).length
          return <article className={`harness-arm-card${arm === 'continuum' ? ' is-continuum' : ''}`} key={arm}>
            <p className="eyebrow">{armLabels[arm]}</p>
            <p className="harness-arm-model">{run.models?.[arm] ?? run.model} · {armHarness[arm]}</p>
            <strong className="harness-correct">{aggregate.correct_pct}% <span>correct{answered ? ` · ${correctCount}/${answered}` : ''}</span></strong>
            <dl className="harness-stats">
              <div><dt>Tokens per correct</dt><dd>{aggregate.display.tokens_per_correct ?? '—'}</dd></div>
              <div><dt>Unsafe answers</dt><dd>{aggregate.display.unsafe ?? String(aggregate.unsafe_count ?? 0)}</dd></div>
              <div><dt>Atlas vector searches</dt><dd>{aggregate.display.vector_calls}</dd></div>
              <div><dt>Tokens · wall</dt><dd>{aggregate.display.tokens} · {aggregate.display.wall}</dd></div>
            </dl>
            <p className="harness-metrics">{formatArmMetrics(aggregate)}</p>
          </article>
        })}
      </div>

      <div className="harness-charts">
        <figure>
          <figcaption>Correct answers (%)</figcaption>
          <svg viewBox="0 0 420 140" role="img" aria-label="Correct answers by arm">
            {arms.map((arm, index) => {
              const value = run.aggregates[arm]?.correct_pct ?? 0
              const y = 8 + index * 32
              return <g key={arm} className={arm === 'continuum' ? 'bar-continuum' : 'bar-other'}>
                <text x="0" y={y + 15} className="bar-label">{armLabels[arm]}</text>
                <rect x="150" y={y} width={(value / 100) * 220} height="20" rx="2" />
                <text x={156 + (value / 100) * 220} y={y + 15} className="bar-value">{value}%</text>
              </g>
            })}
          </svg>
        </figure>
        <figure>
          <figcaption>Tokens per correct answer (lower is better)</figcaption>
          <svg viewBox="0 0 420 140" role="img" aria-label="Tokens per correct answer by arm">
            {arms.map((arm, index) => {
              const value = run.aggregates[arm]?.tokens_per_correct ?? 0
              const y = 8 + index * 32
              return <g key={arm} className={arm === 'continuum' ? 'bar-continuum' : 'bar-other'}>
                <text x="0" y={y + 15} className="bar-label">{armLabels[arm]}</text>
                <rect x="150" y={y} width={(value / maxPerCorrect) * 200} height="20" rx="2" />
                <text x={156 + (value / maxPerCorrect) * 200} y={y + 15} className="bar-value">{value ? value.toLocaleString() : '—'}</text>
              </g>
            })}
          </svg>
        </figure>
        {families.length > 0 && <div className="harness-families">
          <p className="eyebrow">Correct by question family</p>
          <table>
            <thead><tr><th>Family</th>{arms.map((arm) => <th key={arm}>{armLabels[arm]}</th>)}</tr></thead>
            <tbody>{families.map((family) => <tr key={family.group}>
              <td>{groupLabel(family.group)}</td>
              {arms.map((arm) => <td key={arm} className={family.correct[arm] === family.total ? 'full' : family.correct[arm] ? undefined : 'none'}>{family.correct[arm] ?? 0}/{family.total}</td>)}
            </tr>)}</tbody>
          </table>
        </div>}
      </div>

      <div className="harness-table-heading">
        <div><h3>Every question, every arm</h3><span>{matrix.length} questions · hover a mark to see the answer</span></div>
      </div>
      <div className="harness-table-wrap">
        <table className="harness-table harness-matrix">
          <thead><tr><th>Question</th><th>Family</th><th>Expected action</th>{arms.map((arm) => <th key={arm} className="mark">{armLabels[arm]}</th>)}</tr></thead>
          <tbody>
            {matrix.map((entry) => <tr key={entry.task_id}>
              <td><span className="task-id">{entry.task_id}</span> {entry.scenario ? <span title={entry.scenario}>{truncate(entry.scenario.replace(/^A synthetic /, ''), 110)}</span> : null}</td>
              <td>{groupLabel(entry.group)}{entry.trap ? <small className="trap">trap</small> : null}</td>
              <td><code>{entry.expected_action}</code></td>
              {arms.map((arm) => {
                const cell = entry.cells[arm]
                if (!cell) return <td key={arm} className="mark">—</td>
                const detailText = `${cell.action}${cell.recommendation ? ` — ${cell.recommendation}` : ''}`
                return <td key={arm} className={`mark ${cell.correct ? 'ok' : 'miss'}`} title={detailText}>
                  <span aria-label={cell.correct ? 'correct' : 'incorrect'}>{cell.correct ? '✓' : '✗'}</span>{cell.unsafe ? <small className="unsafe">unsafe</small> : null}
                </td>
              })}
            </tr>)}
          </tbody>
        </table>
      </div>

      <details className="harness-raw">
        <summary>Show raw rows ({rows.length})</summary>
        <div className="harness-table-heading">
          <div><span>{visibleRows.length} rows · {run.model}</span></div>
          <label>Filter arm
            <select aria-label="Filter rows by arm" value={armFilter} onChange={(event) => setArmFilter(event.target.value as HarnessArmName | 'all')}>
              <option value="all">All arms</option>
              {arms.map((value) => <option value={value} key={value}>{armLabels[value]}</option>)}
            </select>
          </label>
        </div>
        <div className="harness-table-wrap">
          <table className="harness-table">
            <thead><tr><th>Arm</th><th>Task</th><th>Expected</th><th>Action</th><th>Tokens</th><th>Cost</th><th>Recommendation</th><th>Policy</th><th>Memories</th></tr></thead>
            <tbody>
              {visibleRows.map((row, index) => <tr key={`${row.task_id}-${row.arm}-${index}`}>
                <td>{armLabels[row.arm] ?? row.arm}</td>
                <td>{row.task_id}</td>
                <td>{row.expected_action}</td>
                <td><span aria-label={row.correct ? 'correct' : 'incorrect'} title={row.action}>{row.correct ? '✓' : '✗'}</span></td>
                <td>{row.total_tokens.toLocaleString()}</td>
                <td>{formatRowCost(row.cost_usd)}</td>
                <td>{row.recommendation ? <span title={row.recommendation}>{truncate(row.recommendation, RECOMMENDATION_TRUNCATE_LENGTH)}</span> : '—'}</td>
                <td>{row.policy_version == null || row.arm !== 'continuum' ? '—' : <a href="#explain" onClick={onFocusExplain}>v{row.policy_version}</a>}</td>
                <td>{row.memory_ids.length && row.arm === 'continuum' ? row.memory_ids.map((id) => <a className="harness-memory-link" href="#remember" onClick={onFocusRemember} key={id}>{id}</a>) : '—'}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </details>
    </> : <div className="empty">{error ? 'No benchmark runs are available yet.' : 'No benchmark runs yet. Run the bench to create one.'}</div>}
  </>
}
