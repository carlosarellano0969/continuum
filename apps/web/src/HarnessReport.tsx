import { useEffect, useState } from 'react'
import type { HarnessArmName, HarnessRun, HarnessRunSummary } from './api'
import { api } from './api'
import { ARM_ORDER, LIVE_RUN_TASK_LIMIT, RECOMMENDATION_TRUNCATE_LENGTH, armLabels, formatArmMetrics, formatArmQuality, formatRowCost, resolvePolicyVersion, truncate } from './harnessFormat'

export function HarnessReport({ onFocusRemember, onFocusExplain }: {
  onFocusRemember: () => void
  onFocusExplain: () => void
}) {
  const [run, setRun] = useState<HarnessRunSummary | null>(null)
  const [detail, setDetail] = useState<HarnessRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const [armFilter, setArmFilter] = useState<HarnessArmName | 'all'>('all')

  async function loadLatest() {
    setError('')
    try {
      const runs = await api.benchRuns()
      const latest = runs[0] ?? null
      setRun(latest)
      setDetail(latest ? await api.benchRun(latest.run_id) : null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Harness runs could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const initialLoad = window.setTimeout(() => { void loadLatest() }, 0)
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
      await api.runBench({ task_limit: LIVE_RUN_TASK_LIMIT })
      await loadLatest()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The harness run failed.')
    } finally {
      setRunning(false)
    }
  }

  const rows = detail?.rows ?? []
  const visibleRows = rows.filter((row) => armFilter === 'all' || row.arm === armFilter)
  const policyVersion = resolvePolicyVersion(run, rows)

  return <>
    <div className="page-heading harness-heading">
      <div>
        <p className="eyebrow">05 · EVALUATE</p>
        <h2 id="harness-title">Harness report</h2>
        <p>Compare grounded actions, latency, cost, and retrieval across three benchmark arms.</p>
      </div>
      <button className="button primary" onClick={() => void startRun()} disabled={running || loading}>
        {running ? `Running · ${elapsed}s` : 'Run live bench'}
      </button>
    </div>
    {error && <p className="harness-error" role="alert">{error}<button className="button secondary" onClick={() => void loadLatest()}>Retry</button></p>}
    {loading ? <div className="loading" role="status">Loading harness runs…</div> : run ? <>
      <div className="harness-run-meta">
        <span>Model {run.model}</span>
        <span>{run.task_count} tasks</span>
        <span>Policy {policyVersion == null ? '—' : `v${policyVersion}`}</span>
        <span>Run <code>{run.run_id}</code></span>
      </div>
      <div className="harness-cards" aria-label="Benchmark arm summaries">
        {ARM_ORDER.map((arm) => {
          const aggregate = run.aggregates[arm]
          return <article className="harness-arm-card" key={arm}>
            <p className="eyebrow">{armLabels[arm]}</p>
            <p className="harness-metrics">{aggregate ? formatArmMetrics(aggregate) : 'No data for this arm.'}</p>
            {aggregate ? <p className="harness-metrics">{formatArmQuality(aggregate)}</p> : null}
            <strong className="harness-correct">{aggregate ? `${aggregate.correct_pct}%` : '—'} <span>correct</span></strong>
          </article>
        })}
      </div>
      <div className="harness-table-heading">
        <div><h3>Task results</h3><span>{visibleRows.length} rows · {run.model}</span></div>
        <label>Filter arm
          <select aria-label="Filter rows by arm" value={armFilter} onChange={(event) => setArmFilter(event.target.value as HarnessArmName | 'all')}>
            <option value="all">All arms</option>
            {ARM_ORDER.map((value) => <option value={value} key={value}>{armLabels[value]}</option>)}
          </select>
        </label>
      </div>
      <div className="harness-table-wrap">
        <table className="harness-table">
          <thead><tr><th>Arm</th><th>Task</th><th>Expected</th><th>Action</th><th>Tokens</th><th>Cost</th><th>Recommendation</th><th>Policy</th><th>Memories</th></tr></thead>
          <tbody>
            {visibleRows.map((row, index) => <tr key={`${row.task_id}-${row.arm}-${index}`}>
              <td>{armLabels[row.arm]}</td>
              <td>{row.task_id}</td>
              <td>{row.expected_action}</td>
              <td><span aria-label={row.correct ? 'correct' : 'incorrect'} title={row.action}>{row.correct ? '✓' : '✗'}</span></td>
              <td>{row.total_tokens.toLocaleString()}</td>
              <td>{formatRowCost(row.cost_usd)}</td>
              <td>{row.recommendation ? <span title={row.recommendation}>{truncate(row.recommendation, RECOMMENDATION_TRUNCATE_LENGTH)}</span> : '—'}</td>
              <td>{row.policy_version == null ? '—' : <a href="#explain" onClick={onFocusExplain}>v{row.policy_version}</a>}</td>
              <td>{row.memory_ids.length ? row.memory_ids.map((id) => <a className="harness-memory-link" href="#remember" onClick={onFocusRemember} key={id}>{id}</a>) : '—'}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </> : <div className="empty">{error ? 'No benchmark runs are available yet.' : 'No benchmark runs yet. Run the bench to create one.'}</div>}
  </>
}
