// AI-OS Phase 0 contracts. Keep these transport-neutral so both local and DSH runners share them.
export const TASK_STATUS = Object.freeze([
  'draft', 'planning', 'waiting_confirmation', 'queued', 'running',
  'waiting_input', 'waiting_approval', 'blocked', 'verifying',
  'succeeded', 'partially_succeeded', 'failed', 'cancelled'
])

export const PROCESS_STATUS = Object.freeze([
  'spawned', 'queued', 'running', 'waiting_input', 'waiting_approval',
  'paused', 'blocked', 'stopping', 'stopped', 'succeeded', 'failed', 'zombie'
])

export const EXECUTION_STATUS = Object.freeze([
  'queued', 'running', 'waiting_input', 'waiting_approval', 'verifying',
  'succeeded', 'partially_succeeded', 'failed', 'cancelled'
])

export const RUNNER_KIND = Object.freeze({ LIGHTWEIGHT: 'lightweight', DSH: 'dsh' })

export function assertTenantBound (value, label = 'record') {
  if (!value?.tenantId) throw new TypeError(`${label}.tenantId is required`)
  return value
}

export function normalizeExecutionResult (result, fallback = {}) {
  const status = result?.status === 'success' ? 'succeeded' : (result?.status || fallback.status || 'failed')
  if (!EXECUTION_STATUS.includes(status)) throw new TypeError(`Unsupported execution status: ${status}`)
  return {
    executionId: result?.executionId ?? fallback.executionId ?? null,
    traceId: result?.traceId ?? fallback.traceId ?? null,
    status,
    output: result?.output ?? null,
    error: result?.error ?? null,
    latencyMs: Number(result?.latencyMs ?? 0),
    runner: fallback.runner ?? null,
    raw: result ?? null
  }
}

export function createExecutionRequest (input) {
  assertTenantBound(input, 'executionRequest')
  if (!input.taskId) throw new TypeError('executionRequest.taskId is required')
  if (!input.instruction) throw new TypeError('executionRequest.instruction is required')
  return Object.freeze({
    taskId: String(input.taskId),
    tenantId: String(input.tenantId),
    user: input.user ?? null,
    agentId: input.agentId ?? null,
    instruction: String(input.instruction),
    triggerType: input.triggerType || 'task',
    routeHint: input.routeHint || null,
    contextSnapshotId: input.contextSnapshotId ?? null,
    metadata: input.metadata || {}
  })
}
