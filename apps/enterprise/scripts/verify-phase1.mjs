import assert from 'node:assert/strict'
import { DatabaseSync } from 'node:sqlite'
import { ensureOsSchema } from '../server/os/schema.js'
import { ExecutionKernel } from '../server/os/execution-kernel.js'
import { RuntimeStore } from '../server/os/runtime-store.js'
import { TaskService } from '../server/os/task-service.js'

const database = new DatabaseSync(':memory:')
database.exec(`
  PRAGMA foreign_keys=ON;
  CREATE TABLE business_tenant (id INTEGER PRIMARY KEY);
  CREATE TABLE business_work_task (
    id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, title TEXT NOT NULL, instruction TEXT NOT NULL,
    agent_id INTEGER NOT NULL, created_by INTEGER, status TEXT NOT NULL DEFAULT 'pending'
  );
  INSERT INTO business_tenant VALUES (1), (2);
  INSERT INTO business_work_task VALUES (10, 1, '生成日报', '汇总今日经营数据', 7, 3, 'pending');
`)
ensureOsSchema(database)

let sequence = 0
const store = new RuntimeStore({ database, clock: () => `2026-08-21T00:00:0${sequence}.000Z`, id: () => `id-${++sequence}` })
const kernel = new ExecutionKernel().registerRunner('lightweight', {
  run: async request => ({ status: 'success', executionId: 99, traceId: 'trace-ok', output: `done:${request.taskId}`, latencyMs: 12 })
})
const service = new TaskService({ database, kernel, store })
const workTask = service.loadLegacyWorkTask({ taskId: 10, tenantId: 1 })

const first = service.ensureLegacyWorkTask(workTask)
const second = service.ensureLegacyWorkTask(workTask)
assert.equal(first.task_id, second.task_id, 'legacy mapping must be idempotent')

const result = await service.executeLegacyWorkTask({ workTask, user: { id: 3, tenant_id: 1 } })
assert.equal(result.status, 'succeeded')
assert.equal(result.osTaskId, first.task_id)

const detail = store.getTask({ tenantId: 1, taskId: first.task_id })
assert.equal(detail.status, 'succeeded')
assert.equal(detail.executions.length, 1)
assert.equal(detail.executions[0].trace_id, 'trace-ok')
assert.equal(detail.processes[0].status, 'succeeded')
assert.deepEqual(detail.events.map(event => event.event_type), ['task.created', 'execution.started', 'execution.succeeded'])
assert.equal(store.getTask({ tenantId: 2, taskId: first.task_id }), null, 'cross-tenant task lookup must not leak')

const failingKernel = new ExecutionKernel().registerRunner('lightweight', { run: async () => { throw new Error('runner unavailable') } })
const failingService = new TaskService({ database, kernel: failingKernel, store })
const failure = await failingService.executeLegacyWorkTask({ workTask, user: { id: 3, tenant_id: 1 } })
assert.equal(failure.status, 'failed')
assert.equal(store.getTask({ tenantId: 1, taskId: first.task_id }).status, 'failed')

console.log('AI-OS Phase 1 verification passed')
