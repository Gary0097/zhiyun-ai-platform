import { randomUUID } from 'node:crypto'

const J = value => JSON.stringify(value ?? null)

export class RuntimeStore {
  constructor ({ database, clock = () => new Date().toISOString(), id = randomUUID }) {
    this.db = database
    this.clock = clock
    this.id = id
  }

  ensureSourceTask ({ tenantId, sourceType, sourceId, title, objective, createdBy = null, ownerId = null }) {
    const existing = this.db.prepare('SELECT * FROM runtime_task WHERE tenant_id = ? AND source_type = ? AND source_id = ?')
      .get(tenantId, sourceType, String(sourceId))
    if (existing) return existing
    const taskId = this.id()
    const at = this.clock()
    this.db.prepare(`INSERT INTO runtime_task
      (task_id, tenant_id, title, objective, created_by, owner_id, source_type, source_id, status, created_at, updated_at, data_origin)
      VALUES (?,?,?,?,?,?,?,?,'queued',?,?,'real')`)
      .run(taskId, tenantId, title, objective, createdBy, ownerId, sourceType, String(sourceId), at, at)
    this.appendEvent({ tenantId, taskId, eventType: 'task.created', payload: { sourceType, sourceId: String(sourceId) } })
    return this.db.prepare('SELECT * FROM runtime_task WHERE task_id = ?').get(taskId)
  }

  startExecution ({ task, runner, triggerType, agentId = null, input = null, retryCount = 0 }) {
    const executionId = this.id()
    const processId = this.id()
    const at = this.clock()
    this.db.prepare(`INSERT INTO runtime_execution
      (execution_id, task_id, tenant_id, runner, trigger_type, status, input_json, retry_count, started_at, created_at)
      VALUES (?,?,?,?,?,'running',?,?,?,?)`)
      .run(executionId, task.task_id, task.tenant_id, runner, triggerType, J(input), retryCount, at, at)
    this.db.prepare(`INSERT INTO runtime_process
      (process_id, tenant_id, task_id, execution_id, agent_id, status, heartbeat_at, started_at)
      VALUES (?,?,?,?,?,'running',?,?)`)
      .run(processId, task.tenant_id, task.task_id, executionId, agentId, at, at)
    this.db.prepare("UPDATE runtime_task SET status='running', progress=0, updated_at=? WHERE task_id=? AND tenant_id=?")
      .run(at, task.task_id, task.tenant_id)
    this.appendEvent({ tenantId: task.tenant_id, taskId: task.task_id, executionId, processId, eventType: 'execution.started', payload: { runner, triggerType } })
    return { executionId, processId }
  }

  saveCheckpoint ({ task, executionId, processId = null, stepKey, state, safeToResume = true }) {
    const checkpointId = this.id()
    this.db.prepare(`INSERT INTO runtime_checkpoint
      (checkpoint_id, tenant_id, task_id, execution_id, process_id, step_key, state_json, safe_to_resume, created_at)
      VALUES (?,?,?,?,?,?,?,?,?)`)
      .run(checkpointId, task.tenant_id, task.task_id, executionId, processId, stepKey, J(state), safeToResume ? 1 : 0, this.clock())
    this.appendEvent({
      tenantId: task.tenant_id,
      taskId: task.task_id,
      executionId,
      processId,
      eventType: 'checkpoint.saved',
      payload: { checkpointId, stepKey, safeToResume }
    })
    return checkpointId
  }

  finishExecution ({ task, executionId, processId, result }) {
    const at = this.clock()
    const status = result.status
    const error = result.error ? String(result.error) : null
    this.db.prepare(`UPDATE runtime_execution SET status=?, trace_id=?, output_json=?, error_message=?, finished_at=?
      WHERE execution_id=? AND tenant_id=?`).run(status, result.traceId, J(result.output), error, at, executionId, task.tenant_id)
    this.db.prepare(`UPDATE runtime_process SET status=?, heartbeat_at=?, finished_at=?
      WHERE process_id=? AND tenant_id=?`).run(status === 'partially_succeeded' ? 'succeeded' : status, at, at, processId, task.tenant_id)
    this.db.prepare(`UPDATE runtime_task SET status=?, progress=?, updated_at=? WHERE task_id=? AND tenant_id=?`)
      .run(status, status === 'succeeded' ? 1 : 0, at, task.task_id, task.tenant_id)
    this.appendEvent({
      tenantId: task.tenant_id,
      taskId: task.task_id,
      executionId,
      processId,
      traceId: result.traceId,
      eventType: status === 'succeeded' ? 'execution.succeeded' : 'execution.failed',
      payload: { status, error }
    })
  }

  appendEvent ({ tenantId, taskId = null, executionId = null, processId = null, traceId = null, eventType, payload = {} }) {
    this.db.prepare(`INSERT INTO runtime_event
      (event_id, event_type, tenant_id, task_id, execution_id, process_id, trace_id, payload_json, created_at)
      VALUES (?,?,?,?,?,?,?,?,?)`)
      .run(this.id(), eventType, tenantId, taskId, executionId, processId, traceId, J(payload), this.clock())
  }

  listTasks ({ tenantId, status = null, limit = 100 }) {
    const size = Math.min(Math.max(Number(limit) || 100, 1), 200)
    return status
      ? this.db.prepare('SELECT * FROM runtime_task WHERE tenant_id=? AND status=? ORDER BY updated_at DESC LIMIT ?').all(tenantId, status, size)
      : this.db.prepare('SELECT * FROM runtime_task WHERE tenant_id=? ORDER BY updated_at DESC LIMIT ?').all(tenantId, size)
  }

  getTask ({ tenantId, taskId }) {
    const task = this.db.prepare('SELECT * FROM runtime_task WHERE task_id=? AND tenant_id=?').get(taskId, tenantId)
    if (!task) return null
    return {
      ...task,
      executions: this.db.prepare('SELECT * FROM runtime_execution WHERE task_id=? AND tenant_id=? ORDER BY created_at DESC').all(taskId, tenantId),
      processes: this.db.prepare('SELECT * FROM runtime_process WHERE task_id=? AND tenant_id=? ORDER BY started_at DESC').all(taskId, tenantId),
      events: this.db.prepare('SELECT * FROM runtime_event WHERE task_id=? AND tenant_id=? ORDER BY created_at').all(taskId, tenantId),
      artifacts: this.db.prepare('SELECT * FROM runtime_artifact WHERE task_id=? AND tenant_id=? ORDER BY created_at DESC').all(taskId, tenantId),
      checkpoints: this.db.prepare('SELECT * FROM runtime_checkpoint WHERE task_id=? AND tenant_id=? ORDER BY created_at DESC').all(taskId, tenantId)
    }
  }
}
