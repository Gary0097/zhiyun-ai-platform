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
    const task = this.ensureLegacyWorkTask(workTask)
    const runner = RUNNER_KIND.LIGHTWEIGHT
    const run = this.store.startExecution({
      task,
      runner,
      triggerType: 'task',
      agentId: workTask.agent_id,
      input: { instruction: workTask.instruction, legacyWorkTaskId: workTask.id }
    })
    const result = await this.kernel.run({
      taskId: task.task_id,
      tenantId: task.tenant_id,
      user,
      agentId: workTask.agent_id,
      instruction: workTask.instruction,
      triggerType: 'task',
      routeHint: runner,
      metadata: { sourceType: 'work_task', sourceId: String(workTask.id) }
    })
    this.store.finishExecution({ task, ...run, result })
    return { ...result, osTaskId: task.task_id, osExecutionId: run.executionId }
  }
}
