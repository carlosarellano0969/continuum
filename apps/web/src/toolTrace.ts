export interface ToolTraceRow {
  backend: string
  model: string
  status: string
  fallbackReason: string
}

function traceValue(trace: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = trace[key]
    if (typeof value === 'string' && value.trim()) return value
    if (typeof value === 'number') return String(value)
  }
  return null
}

export function toolTraceRows(trace: Array<Record<string, unknown>>): ToolTraceRow[] {
  return trace.map((step, index) => {
    const fallback = step.fallback === true || step.used_fallback === true
    const backend = traceValue(step, ['retrieval_backend', 'backend', 'retriever', 'provider', 'tool', 'name']) ?? `execution step ${index + 1}`
    const model = traceValue(step, ['model', 'model_name', 'embedding_model', 'chat_model']) ?? 'not reported'
    const status = traceValue(step, ['status', 'state']) ?? (fallback ? 'fallback' : 'recorded')
    const fallbackReason = traceValue(step, ['fallback_reason', 'fallbackReason', 'reason', 'error', 'detail']) ?? (fallback ? 'Fallback invoked; API did not provide a reason.' : 'No fallback recorded.')
    return { backend, model, status, fallbackReason }
  })
}
