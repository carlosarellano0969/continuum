import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode, RefObject } from 'react'
import { api, ApiError, type AuditEvent, type DemoSummary, type Explanation, type GuardrailProposal, type Health, type Memory, type Policy, type Recommendation } from './api'
import { dependencyNotice } from './dependencyNotice'
import { toolTraceRows } from './toolTrace'
import { HarnessReport } from './HarnessReport'

type LoadState = 'loading' | 'ready' | 'error'

interface DashboardData {
  health: Health
  summary: DemoSummary
  memories: Memory[]
  policies: { active: Policy | null; history: Policy[] }
  proposals: GuardrailProposal[]
  audit: AuditEvent[]
}

const initialScenario = 'A prospective customer asks what financing options are available and wants an estimated monthly payment. What should we recommend?'

function formatDate(value?: string | null) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' }).format(date)
}

function statusLabel(status: string) { return status.replaceAll('_', ' ') }


function auditDescription(event: AuditEvent) {
  if (event.details) {
    if (typeof event.details.note === 'string' && event.details.note) return event.details.note
    if (typeof event.details.new_policy_version === 'number') return `Activated policy v${event.details.new_policy_version}`
  }
  return event.actor ?? 'System event recorded'
}

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'good' | 'warn' | 'danger' | 'neutral' }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

function Loading({ label = 'Loading the decision system…' }: { label?: string }) {
  return <div className="loading" role="status"><span className="spinner" />{label}</div>
}

function ErrorPanel({ message, retry }: { message: string; retry: () => void }) {
  return <section className="error-panel" role="alert"><span className="alert-mark">!</span><div><strong>Connection needs attention</strong><p>{message}</p><button className="button secondary" onClick={retry}>Try again</button></div></section>
}

function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div> }

export function App() {
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [data, setData] = useState<DashboardData | null>(null)
  const [scenario, setScenario] = useState(initialScenario)
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [working, setWorking] = useState<'recommendation' | 'explanation' | 'proposal' | 'reset' | null>(null)
  const [notice, setNotice] = useState('')
  const explanationHeading = useRef<HTMLHeadingElement>(null)
  const rememberHeading = useRef<HTMLHeadingElement>(null)

  const load = useCallback(async () => {
    setState('loading'); setError('')
    try {
      const [health, summary, memoryResult, policies, proposalResult, auditResult] = await Promise.all([
        api.health(), api.summary(), api.memories(), api.policies(), api.proposals(), api.auditEvents(),
      ])
      setData({ health, summary, memories: memoryResult.items, policies, proposals: proposalResult.items, audit: auditResult.items })
      setState('ready')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The dashboard could not be loaded.')
      setState('error')
    }
  }, [])

  useEffect(() => {
    const initialLoad = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(initialLoad)
  }, [load])

  async function requestRecommendation(event: FormEvent) {
    event.preventDefault()
    if (!scenario.trim()) return
    setWorking('recommendation'); setNotice(''); setExplanation(null)
    try {
      const next = await api.recommend(scenario.trim())
      setRecommendation(next)
      const details = await api.explanation(next.decision_id)
      setExplanation(details)
      setNotice('A recommendation was recorded with its evidence trail.')
    } catch (err) { setNotice(err instanceof Error ? err.message : 'Recommendation failed.') }
    finally { setWorking(null) }
  }

  async function showExplanation(decisionId?: string) {
    if (!decisionId) { setNotice('Choose or create a decision to inspect its explanation.'); return }
    setWorking('explanation'); setNotice('')
    try {
      setExplanation(await api.explanation(decisionId))
      focusExplanation()
    }
    catch (err) { setNotice(err instanceof Error ? err.message : 'Explanation unavailable.') }
    finally { setWorking(null) }
  }

  function focusExplanation() {
    window.setTimeout(() => {
      explanationHeading.current?.focus()
      explanationHeading.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    }, 0)
  }

  function focusRemember() {
    window.setTimeout(() => {
      rememberHeading.current?.focus()
      rememberHeading.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    }, 0)
  }

  function inspectExplanation(decisionId?: string) {
    if (decisionId && explanation?.decision_id === decisionId) { focusExplanation(); return }
    void showExplanation(decisionId)
  }

  async function decide(proposal: GuardrailProposal, decision: 'approve' | 'reject') {
    setWorking('proposal'); setNotice('')
    try {
      await api.decideProposal(proposal.id, decision, decision === 'approve' ? 'Approved from the Continuum console.' : 'Rejected from the Continuum console.')
      if (decision === 'approve') {
        setRecommendation(null)
        setExplanation(null)
      }
      setNotice(`Proposal ${decision}d. The audit trail and policy timeline have been refreshed.`)
      await load()
    } catch (err) { setNotice(err instanceof ApiError && err.status === 409 ? 'This proposal has already been decided. Refreshing the current state.' : err instanceof Error ? err.message : 'Proposal decision failed.') }
    finally { setWorking(null) }
  }

  async function resetDemo() {
    setWorking('reset'); setNotice('')
    try { await api.resetDemo(); await load(); setRecommendation(null); setExplanation(null); setNotice('Demo data restored to its deterministic baseline.') }
    catch (err) { setNotice(err instanceof Error ? err.message : 'Reset failed.') }
    finally { setWorking(null) }
  }

  const dependencyIssue = data && Object.values(data.health.services).some((service) => service !== 'ok')
  const activeProposal = data?.proposals.find((proposal) => proposal.state === 'pending') ?? data?.summary.pending_proposal

  return <main className="app-shell" id="top">
    <a className="skip-link" href="#decide">Skip to decision workspace</a>
    <header className="topbar">
      <a className="brand" href="#top" aria-label="Continuum home"><span className="brand-mark">C</span><span>continuum</span><em>V1.1</em></a>
      <div className="identity"><span className="presence" />demo-org <span className="slash">/</span> demo-agent</div>
      <button className="button text-button" onClick={() => void resetDemo()} disabled={working !== null}>{working === 'reset' ? 'Resetting…' : 'Reset demo'}</button>
    </header>

    <div className="layout">
      <nav className="sidebar" aria-label="Evidence loop">
        <p className="rail-label">EVIDENCE LOOP</p>
        <a className="nav-link" href="#decide"><span>01</span><div><strong>Decide</strong><small>Ask the agent</small></div></a>
        <a className="nav-link" href="#explain"><span>02</span><div><strong>Explain</strong><small>Inspect the change</small></div></a>
        <a className="nav-link" href="#remember"><span>03</span><div><strong>Remember</strong><small>Review evidence</small></div></a>
        <a className="nav-link" href="#govern"><span>04</span><div><strong>Govern</strong><small>Approve policy</small></div></a>
        <a className="nav-link" href="#harness" aria-label="Harness report"><span>05</span><div><strong>Harness</strong><small>Compare runs</small></div></a>
        <div className="sidebar-foot"><span className="eyebrow">SYSTEM</span><div><span className={`dot ${data?.health.status === 'ok' ? 'ok' : 'warn'}`} /> {data ? statusLabel(data.health.status) : 'checking'}</div><small>API {data?.health.version ?? '—'}</small></div>
      </nav>

      <section className="workspace">
        {state === 'loading' && <Loading />}
        {state === 'error' && <ErrorPanel message={error} retry={() => void load()} />}
        {state === 'ready' && data && <>
          {dependencyIssue && <section className="degraded" role="status">{dependencyNotice(data.health.services)}</section>}
          {notice && <div className="notice" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}
          <Overview data={data} pendingProposal={Boolean(activeProposal)} />
          <div className="control-grid">
            <section id="decide" className="workspace-panel panel-decide" aria-labelledby="decide-title">
              <Console scenario={scenario} setScenario={setScenario} onSubmit={requestRecommendation} busy={working === 'recommendation'} locked={working !== null} recommendation={recommendation} activePolicy={data.policies.active} onInspect={() => inspectExplanation(recommendation?.decision_id ?? data.summary.latest_decision?.id)} />
            </section>
            <section id="explain" className="workspace-panel panel-explain" aria-labelledby="explain-title">
              <ExplanationPanel explanation={explanation} latestDecisionId={data.summary.latest_decision?.id} busy={working === 'explanation'} locked={working !== null} onLoad={showExplanation} headingRef={explanationHeading} />
            </section>
            <section id="remember" className="workspace-panel panel-remember" aria-labelledby="remember-title">
              <MemoryInspector memories={data.memories} headingRef={rememberHeading} />
            </section>
            <section id="govern" className="workspace-panel panel-govern" aria-labelledby="govern-title">
              <PolicyHistory policies={data.policies.history} active={data.policies.active} proposal={activeProposal ?? null} audit={data.audit} busy={working === 'proposal'} locked={working !== null} onDecision={decide} />
            </section>
            <section id="harness" className="workspace-panel panel-harness" aria-labelledby="harness-title">
              <HarnessReport health={data.health} onFocusRemember={focusRemember} onFocusExplain={focusExplanation} />
            </section>
          </div>
        </>}
      </section>
    </div>
  </main>
}

function Overview({ data, pendingProposal }: { data: DashboardData; pendingProposal: boolean }) {
  return <section className="overview" aria-labelledby="overview-title">
    <div className="overview-copy"><p className="eyebrow">V1.1 · DECISION CONTROL ROOM</p><h1 id="overview-title">One decision. One evidence trail.</h1><p>Move from a grounded recommendation to its explanation, memory, and human-governed policy without leaving the page.</p></div>
    <div className="proof-strip" aria-label="Workspace summary">
      <div><strong>v{data.policies.active?.version ?? '—'}</strong><span>active policy</span></div>
      <div><strong>{data.memories.length}</strong><span>memories loaded</span></div>
      <div><strong>{data.audit.length}</strong><span>audit events</span></div>
      <div><strong>{pendingProposal ? '1' : '0'}</strong><span>pending review</span></div>
    </div>
  </section>
}

function Console({ scenario, setScenario, onSubmit, busy, locked, recommendation, activePolicy, onInspect }: { scenario: string; setScenario: (value: string) => void; onSubmit: (event: FormEvent) => void; busy: boolean; locked: boolean; recommendation: Recommendation | null; activePolicy: Policy | null; onInspect: () => void }) {
  const traceRows = recommendation ? toolTraceRows(recommendation.tool_trace) : []
  return <>
    <div className="page-heading"><div><p className="eyebrow">01 · DECIDE</p><h2 id="decide-title">Ask with evidence</h2><p>Ground each recommendation in remembered outcomes and the active human guardrail.</p></div><Badge tone="good">Policy v{activePolicy?.version ?? '—'} active</Badge></div>
    <form className="scenario-card" onSubmit={onSubmit} aria-busy={busy}><label htmlFor="scenario">What should the agent decide?</label><textarea id="scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} rows={3} placeholder="Describe a customer scenario…" /><div className="form-row"><span>Recommendations are logged with a policy and memory trail.</span><button className="button primary" disabled={locked || !scenario.trim()}>{busy ? 'Reasoning…' : 'Generate recommendation'} <span aria-hidden>→</span></button></div></form>
    {busy && <Loading label="Retrieving scoped memories and validating policy…" />}
    {!busy && !recommendation && <section className="welcome-grid"><article><span className="number">01</span><h2>Ask</h2><p>Frame a concrete case for the agent.</p></article><article><span className="number">02</span><h2>Ground</h2><p>Continuum retrieves scoped memories and one active policy.</p></article><article><span className="number">03</span><h2>Account</h2><p>Every result gets an inspectable explanation chain.</p></article></section>}
    {recommendation && <section className="recommendation-card"><div className="result-heading"><div><p className="eyebrow">RECOMMENDATION <span className="mono">{recommendation.decision_id}</span></p><h3>{recommendation.recommendation}</h3></div><span className="latency">{recommendation.latency_ms} ms</span></div><p className="rationale">{recommendation.rationale}</p><div className="decision-context"><span className="eyebrow">RECORDED CONTEXT</span><strong>Policy version {recommendation.policy_version}</strong><span>This decision remains bound to this version even when a newer policy becomes active.</span></div><div className="citation-row"><span>Grounded in</span>{recommendation.cited_memory_ids.length ? recommendation.cited_memory_ids.map((id) => <code key={id}>{id}</code>) : <span className="muted">No persisted citations returned</span>}</div><section className="provenance" aria-label="Execution provenance"><div className="section-heading"><div><p className="eyebrow">EXECUTION PROVENANCE</p><h3>How this result was produced</h3></div><Badge tone={traceRows.some((row) => row.status.toLowerCase().includes('fallback') || row.status.toLowerCase().includes('degrad')) ? 'warn' : 'neutral'}>{traceRows.length ? `${traceRows.length} recorded steps` : 'No trace returned'}</Badge></div>{traceRows.length ? <div className="trace-table-wrap"><table className="trace-table"><caption>Recorded model and retrieval trace</caption><thead><tr><th>Retrieval / backend</th><th>Model</th><th>Status</th><th>Fallback reason</th></tr></thead><tbody>{traceRows.map((row, index) => <tr key={`${row.backend}-${index}`}><td>{row.backend}</td><td>{row.model}</td><td><Badge tone={row.status.toLowerCase().includes('fallback') || row.status.toLowerCase().includes('degrad') ? 'warn' : 'good'}>{row.status}</Badge></td><td>{row.fallbackReason}</td></tr>)}</tbody></table></div> : <Empty>The API did not return a tool trace, so model and fallback provenance cannot be verified.</Empty>}</section><button type="button" className="why-button" onClick={onInspect}><span className="why-icon">?</span><span><strong>Why did you change your mind?</strong><small>Jump to the before/after evidence and approval chain.</small></span><span aria-hidden>→</span></button></section>}
  </>
}

function ExplanationPanel({ explanation, latestDecisionId, busy, locked, onLoad, headingRef }: { explanation: Explanation | null; latestDecisionId?: string; busy: boolean; locked: boolean; onLoad: (decisionId?: string) => Promise<void>; headingRef: RefObject<HTMLHeadingElement | null> }) {
  return <>
    <div className="page-heading"><div><p className="eyebrow">02 · EXPLAIN</p><h2 id="explain-title" ref={headingRef} tabIndex={-1}>Understand the change</h2><p>Inspect the decision-bound policy, supporting outcomes, and recorded human approval.</p></div><Badge>Auditable</Badge></div>
    {busy ? <Loading label="Loading the decision explanation…" /> : explanation ? <ExplanationView explanation={explanation} /> : <div className="explanation-empty"><span className="empty-orbit" aria-hidden>↺</span><h3>No explanation selected</h3><p>Generate a recommendation above or inspect the most recent recorded decision.</p><button className="button secondary" disabled={locked || !latestDecisionId} onClick={() => void onLoad(latestDecisionId)}>{latestDecisionId ? 'Inspect latest decision' : 'No recorded decision'}</button></div>}
  </>
}

function ExplanationView({ explanation }: { explanation: Explanation }) {
  const approver = explanation.approval && typeof explanation.approval.actor === 'string' ? explanation.approval.actor : null
  return <section className="explanation-card" aria-label="Decision explanation"><div className="section-heading"><div><p className="eyebrow">EXPLANATION CHAIN</p><h3>Why did you change your mind?</h3></div><Badge tone={explanation.after ? 'good' : 'neutral'}>{explanation.after ? 'Change recorded' : 'Current decision'}</Badge></div><p>{explanation.summary}</p><div className="change-grid"><article><span className="eyebrow">BEFORE</span><p>{explanation.before ? `Policy v${explanation.before.version}: ${explanation.before.rule}` : 'No prior policy version was recorded for this decision.'}</p></article><article><span className="eyebrow">AFTER</span><p>{explanation.after ? `Policy v${explanation.after.version}: ${explanation.after.rule}` : 'No approved successor policy exists yet.'}</p></article></div>{approver && <p className="rationale">Approved by {approver}; supporting outcome and audit identifiers are retained below.</p>}<div className="trace"><div><strong>{explanation.memories.length}</strong><span> memories cited</span></div><div><strong>{explanation.policy_chain.length}</strong><span> policy versions</span></div><div><strong>{explanation.outcomes.length}</strong><span> recorded outcomes</span></div><div><strong>{explanation.audit_event_ids.length}</strong><span> audit events</span></div></div></section>
}

function MemoryInspector({ memories, headingRef }: { memories: Memory[]; headingRef: RefObject<HTMLHeadingElement | null> }) {
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(false)
  const visible = memories.filter((memory) => `${memory.content} ${memory.type} ${memory.provenance}`.toLowerCase().includes(query.toLowerCase()))
  const shown = expanded ? visible : visible.slice(0, 4)
  return <><div className="page-heading"><div><p className="eyebrow">03 · REMEMBER</p><h2 id="remember-title" ref={headingRef} tabIndex={-1}>Inspect the evidence</h2><p>Review only the memories scoped to this organization and agent.</p></div><Badge>{memories.length} loaded</Badge></div><label className="search"><span aria-hidden>⌕</span><input value={query} onChange={(event) => { setQuery(event.target.value); setExpanded(false) }} placeholder="Filter memories" aria-label="Filter memories" /></label><section className="memory-list">{shown.length ? shown.map((memory) => <article className="memory-card" key={memory.id}><div className="memory-meta"><Badge tone={memory.status === 'active' ? 'good' : 'neutral'}>{memory.status}</Badge><span>{memory.type}</span><time dateTime={memory.created_at}>{formatDate(memory.created_at)}</time></div><p>{memory.content}</p><footer><span>Source: {memory.provenance}</span><span>Confidence {Math.round(memory.confidence * 100)}%</span><code>{memory.id}</code></footer></article>) : <Empty>No memories match this filter.</Empty>}</section>{visible.length > 4 && <button className="button list-toggle" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? 'Show fewer memories' : `Show ${visible.length - shown.length} more memories`}</button>}</>
}

function PolicyHistory({ policies, active, proposal, audit, busy, locked, onDecision }: { policies: Policy[]; active: Policy | null; proposal: GuardrailProposal | null; audit: AuditEvent[]; busy: boolean; locked: boolean; onDecision: (proposal: GuardrailProposal, decision: 'approve' | 'reject') => void }) {
  const timeline = [...policies].sort((a, b) => b.version - a.version)
  return <><div className="page-heading"><div><p className="eyebrow">04 · GOVERN</p><h2 id="govern-title">Approve policy change</h2><p>Policies stay immutable; a new version exists only after recorded human approval.</p></div><Badge tone="good">v{active?.version ?? '—'} active</Badge></div>{proposal ? <Proposal proposal={proposal} busy={busy} locked={locked} onDecision={onDecision} /> : <Empty>No policy changes are awaiting review.</Empty>}<section className="split-panel"><div><div className="section-heading"><h3>Version timeline</h3><span>{timeline.length} versions</span></div><ol className="timeline">{timeline.length ? timeline.map((policy) => <li key={policy.id}><span className={policy.status === 'active' ? 'timeline-dot active' : 'timeline-dot'} /><div><div className="policy-title"><strong>Version {policy.version}</strong>{policy.status === 'active' && <Badge tone="good">Active</Badge>}</div><p>{policy.rule}</p><small>{policy.risk} risk · {formatDate(policy.created_at)}</small></div></li>) : <li><Empty>No policies returned.</Empty></li>}</ol></div><div><div className="section-heading"><h3>Audit log</h3><span>append-only</span></div><ul className="audit-list">{audit.length ? audit.map((event) => <li key={event.id}><span className="audit-icon">↳</span><div><strong>{statusLabel(event.event_type)}</strong><p>{auditDescription(event)}</p><time>{formatDate(event.created_at)}</time></div></li>) : <li><Empty>No audit events returned.</Empty></li>}</ul></div></section></>
}

function Proposal({ proposal, busy, locked, onDecision }: { proposal: GuardrailProposal; busy: boolean; locked: boolean; onDecision: (proposal: GuardrailProposal, decision: 'approve' | 'reject') => void }) {
  return <section className="proposal-card" aria-busy={busy}><div className="proposal-heading"><div><p className="eyebrow">PENDING GUARDRAIL PROPOSAL</p><h3>Evidence asks for a policy adjustment</h3></div><Badge tone="warn">Human review required</Badge></div><div className="rule-diff"><article><span>Current policy</span><p>{proposal.current_rule}</p></article><span className="diff-arrow">→</span><article className="proposed"><span>Proposed policy</span><p>{proposal.proposed_rule}</p></article></div><div className="proposal-evidence"><div><span className="eyebrow">EVIDENCE</span><p>{proposal.evidence.length ? proposal.evidence.join(' · ') : 'No evidence identifiers provided'}</p></div><div><span className="eyebrow">EXPECTED EFFECT</span><p>{proposal.expected_effect}</p></div><div><span className="eyebrow">CONFIDENCE / RISK</span><p>{Math.round(proposal.confidence * 100)}% / {proposal.risk}</p></div></div><div className="proposal-actions"><small>Approval writes a new immutable policy version and audit event.</small><div><button className="button secondary" onClick={() => onDecision(proposal, 'reject')} disabled={locked}>{busy ? 'Recording…' : 'Reject'}</button><button className="button primary" onClick={() => onDecision(proposal, 'approve')} disabled={locked}>{busy ? 'Recording…' : 'Approve change'}</button></div></div></section>
}
