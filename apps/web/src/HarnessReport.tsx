import { useEffect, useState } from 'react'
import type { HarnessArm, HarnessArmName, HarnessRun } from './api'
import { api } from './api'

const armLabels: Record<HarnessArmName, string> = {
  out_of_box: 'Out of the box',
  context_stuffing: 'Context stuffing',
  continuum: 'Continuum',
}

export function formatArmMetrics(arm: HarnessArm) {
  return `Cost ${arm.display.cost} · Wall ${arm.display.wall} · Vector calls ${arm.display.vector_calls} · Tokens ${arm.display.tokens}`
}

function hasFallback(run: HarnessRun) {
  return run.traces?.some((trace) => trace.fallback === true) ?? false
}

export function HarnessReport({ health, onFocusRemember, onFocusExplain }: {
  health: { services: { mongodb: string }; models?: { embedding: string | null; chat: string | null } }
  onFocusRemember: () => void
  onFocusExplain: () => void
}) {
  const [runs, setRuns] = useState<HarnessRun[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const [armFilter, setArmFilter] = useState<HarnessArmName | 'all'>('all')
  const run = runs[0]

  async function refresh() {
    setError('')
    try { setRuns(await api.benchRuns()) }
    catch (err) { setError(err instanceof Error ? err.message : 'Harness runs could not be loaded.') }
    finally { setLoading(false) }
  }

  useEffect(() => { void refresh() }, [])

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
      const created = await api.runBench()
      const refreshed = await api.benchRuns()
      setRuns(refreshed.some((item) => item.run_id === created.run_id) ? refreshed : [created, ...refreshed])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The harness run failed.')
    } finally { setRunning(false) }
  }

  const visibleRows = run?.rows.filter((row) => armFilter === 'all' || row.arm === armFilter) ?? []
  const model = health.models?.chat || run?.model || 'model not reported'
  const embedding = health.models?.embedding || 'voyage-4-large'

  return <>
    <div className="page-heading harness-heading"><div><p className="eyebrow">05 · EVALUATE</p><h2 id="harness-title">Harness report</h2><p>Compare grounded actions, latency, cost, and retrieval across three benchmark arms.</p></div><button className="button primary" onClick={() => void startRun()} disabled={running || loading}>{running ? `Running · ${elapsed}s` : 'Run bench'}</button></div>
    <div className="harness-provenance" aria-label="Harness environment">
      <span><strong>Data</strong>{health.services.mongodb === 'unconfigured' ? 'MongoDB unavailable' : 'Atlas Sandbox'}</span>
      <span><strong>Model</strong>OpenRouter {model}</span>
      <span><strong>Embeddings</strong>{embedding}</span>
      {run && hasFallback(run) && <span className="badge danger fallback-badge">Fallback</span>}
    </div>
    {error && <p className="harness-error" role="alert">{error}<button className="button secondary" onClick={() => void refresh()}>Retry</button></p>}
    {loading ? <div className="loading" role="status">Loading harness runs…</div> : run ? <>
      <div className="harness-run-meta"><span>Atlas document <code>{run.run_id}</code></span><span>{new Date(run.ts).toLocaleString()}</span><span>Seed {run.seed}</span></div>
      <div className="harness-cards" aria-label="Benchmark arm summaries">
        {run.arms.map((arm) => <article className="harness-arm-card" key={arm.arm}><p className="eyebrow">{armLabels[arm.arm]}</p><p className="harness-metrics">{formatArmMetrics(arm)}</p><strong className="harness-correct">{arm.correct_pct}% <span>correct</span></strong></article>)}
      </div>
      <div className="harness-table-heading"><div><h3>Task results</h3><span>{visibleRows.length} rows · {run.model}</span></div><label>Filter arm<select aria-label="Filter rows by arm" value={armFilter} onChange={(event) => setArmFilter(event.target.value as HarnessArmName | 'all')}><option value="all">All arms</option>{Object.entries(armLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>
      <div className="harness-table-wrap"><table className="harness-table"><thead><tr><th>Arm</th><th>Task</th><th>Action / expected</th><th>Correct</th><th>Wall</th><th>Tokens</th><th>Cost</th><th>Vectors</th><th>Policy</th><th>Memories</th></tr></thead><tbody>{visibleRows.map((row, index) => <tr key={`${row.task_id}-${row.arm}-${index}`}><td>{armLabels[row.arm]}</td><td>{row.task_id}</td><td><span>{row.action}</span><small>Expected: {row.expected_action}</small></td><td>{row.correct ? 'Yes' : 'No'}</td><td>{(row.wall_ms / 1000).toFixed(1)}s</td><td>{row.total_tokens.toLocaleString()}</td><td>${row.cost_usd.toFixed(2)}</td><td>{row.vector_calls}</td><td>{row.policy_version == null ? '—' : <a href="#explain" onClick={onFocusExplain}>v{row.policy_version}</a>}</td><td>{row.memory_ids.length ? row.memory_ids.map((id) => <a className="harness-memory-link" href="#remember" onClick={onFocusRemember} key={id}>{id}</a>) : '—'}</td></tr>)}</tbody></table></div>
    </> : <div className="empty">{error ? 'No benchmark runs are available yet.' : 'No benchmark runs yet. Run the bench to create one.'}</div>}
  </>
}
