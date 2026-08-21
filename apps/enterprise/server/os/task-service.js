import { RUNNER_KIND } from './contracts.js'

export class TaskService {
  constructor ({ database, kernel, store }) {
    this.db = database
    this.kernel = kernel
    this.store = store
  }

  loadLegacyWorkTask ({ taskId, tenantId }) {
    return this.db.prepare('SELECT * FROM business_work_task WHERE id=? AND tenant_id=?').get(taskId, tenantId)
  }

  ensureLegacyWorkTask (workTask) {
    return this.store.ensureSourceTask({
      tenantId: workTask.tenant_id,
      sourceType: 'work_task',
      sourceId: workTask.id,
      title: workTask.title,
      objective: workTask.instruction,
      createdBy: workTask.created_by
    })
  }

  async executeLegacyWorkTask ({ workTask, user }) {
    return this.executeSourceTask({
      task: this.ensureLegacyWorkTask(workTask),
      user,
      agentId: workTask.agent_id,
      instruction: workTask.instruction,
      triggerType: 'task',
      sourceType: 'work_task',
      sourceId: workTask.id
    })
  }

  ensureScheduledTask (scheduledTask) {
    const input = JSON.parse(scheduledTask.input || '{}')
    return this.store.ensureSourceTask({
      tenantId: scheduledTask.tenant_id,
      sourceType: 'scheduled_task',
      sourceId: scheduledTask.task_id,
      title: scheduledTask.name,
      objective: input.instruction || scheduledTask.name,
      createdBy: scheduledTask.created_by
    })
  }

  async executeScheduledTask ({ scheduledTask, instruction, triggerSource, attempt = 0 }) {
    return this.executeSourceTask({
      task: this.ensureScheduledTask(scheduledTask),
      user: null,
      agentId: scheduledTask.agent_id,
      instruction,
      triggerType: `scheduled:${triggerSource}`,
      sourceType: 'scheduled_task',
      sourceId: scheduledTask.task_id,
      retryCount: attempt
    })
  }

  async executeSourceTask ({ task, user, agentId, instruction, triggerType, sourceType, sourceId, retryCount = 0 }) {
    const runner = RUNNER_KIND.LIGHTWEIGHT
    const run = this.store.startExecution({
      task,
      runner,
      triggerType,
      agentId,
      retryCount,
      input: { instruction, sourceType, sourceId: String(sourceId) }
    })
    const result = await this.kernel.run({
      taskId: task.task_id,
      tenantId: task.tenant_id,
      user,
      agentId,
      instruction,
      triggerType,
      routeHint: runner,
      metadata: { sourceType, sourceId: String(sourceId), retryCount }
    })
    this.store.finishExecution({ task, ...run, result })
    this.store.saveCheckpoint({
      task,
      executionId: run.executionId,
      processId: run.processId,
      stepKey: 'attempt.completed',
      state: { status: result.status, retryCount, traceId: result.traceId },
      safeToResume: true
    })
    return { ...result, osTaskId: task.task_id, osExecutionId: run.executionId }
  }

  recordExternalExecution ({ tenantId, title, objective, sourceType, sourceId, agentId = null, triggerType, sessionId = null, result }) {
    const task = this.store.ensureSourceTask({ tenantId, sourceType, sourceId, title, objective })
    const run = this.store.startExecution({
      task,
      runner: RUNNER_KIND.DSH,
      triggerType,
      agentId,
      input: { instruction: objective, sessionId, sourceType, sourceId: String(sourceId) }
    })
    const normalized = {
      status: result.status === 'success' ? 'succeeded' : result.status,
      traceId: result.traceId ?? null,
      output: result.output ?? null,
      error: result.error ?? null
    }
    this.store.finishExecution({ task, ...run, result: normalized })
    this.store.saveCheckpoint({
      task,
      executionId: run.executionId,
      processId: run.processId,
      stepKey: 'session.turn.completed',
      state: { sessionId, status: normalized.status, traceId: normalized.traceId },
      safeToResume: Boolean(sessionId)
    })
    return { osTaskId: task.task_id, osExecutionId: run.executionId }
  }
}
