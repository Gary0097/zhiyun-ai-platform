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
  CREATE TABLE business_scheduled_task (
    task_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, agent_id INTEGER NOT NULL,
    name TEXT NOT NULL, input TEXT, created_by INTEGER
  );
  INSERT INTO business_tenant VALUES (1), (2);
  INSERT INTO business_scheduled_task VALUES (20, 1, 8, '经营日报', '{"instruction":"生成经营日报"}', 4);
`)
ensureOsSchema(database)

let sequence = 0
const store = new RuntimeStore({ database, clock: () => `2026-08-21T01:00:${String(sequence).padStart(2, '0')}.000Z`, id: () => `phase2-${++sequence}` })
let shouldFail = false
const kernel = new ExecutionKernel().registerRunner('lightweight', {
  run: async request => shouldFail
    ? { status: 'failed', error: 'temporary gateway error' }
    : { status: 'success', executionId: 101, traceId: `trace-${request.metadata.retryCount}`, output: '日报完成' }
})
const service = new TaskService({ database, kernel, store })
const scheduledTask = database.prepare('SELECT * FROM business_scheduled_task WHERE task_id=20').get()

const first = await service.executeScheduledTask({ scheduledTask, instruction: '生成经营日报', triggerSource: 'scheduler', attempt: 0 })
assert.equal(first.status, 'succeeded')

shouldFail = true
const retry = await service.executeScheduledTask({ scheduledTask, instruction: '生成经营日报', triggerSource: 'scheduler', attempt: 1 })
assert.equal(retry.status, 'failed')

const task = service.ensureScheduledTask(scheduledTask)
const detail = store.getTask({ tenantId: 1, taskId: task.task_id })
assert.equal(detail.executions.length, 2)
assert.deepEqual(detail.executions.map(run => run.retry_count).sort(), [0, 1])
assert.equal(detail.checkpoints.length, 2)
assert(detail.checkpoints.every(checkpoint => checkpoint.safe_to_resume === 1))
assert.equal(service.ensureScheduledTask(scheduledTask).task_id, task.task_id)
assert.equal(store.getTask({ tenantId: 2, taskId: task.task_id }), null)

console.log('AI-OS Phase 2 verification passed: scheduler mapping, retry attempts, checkpoints, tenant isolation')
