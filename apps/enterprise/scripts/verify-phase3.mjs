import assert from 'node:assert/strict'
import { DatabaseSync } from 'node:sqlite'
import { ensureOsSchema } from '../server/os/schema.js'
import { RuntimeStore } from '../server/os/runtime-store.js'
import { TaskService } from '../server/os/task-service.js'

const database = new DatabaseSync(':memory:')
database.exec('PRAGMA foreign_keys=ON; CREATE TABLE business_tenant (id INTEGER PRIMARY KEY); INSERT INTO business_tenant VALUES (1), (2);')
ensureOsSchema(database)

let sequence = 0
const store = new RuntimeStore({ database, id: () => `phase3-${++sequence}` })
const service = new TaskService({ database, kernel: null, store })
const base = {
  tenantId: 1,
  title: '采购分析自动运行',
  objective: '分析采购数据',
  sourceType: 'auto_session',
  sourceId: 'report:session-abc',
  agentId: 9,
  triggerType: 'auto:report',
  sessionId: 'session-abc'
}

const success = service.recordExternalExecution({ ...base, result: { status: 'success', traceId: 'trace-1', output: '报告完成' } })
const failure = service.recordExternalExecution({ ...base, result: { status: 'failed', traceId: 'trace-2', error: 'timeout' } })
assert.equal(success.osTaskId, failure.osTaskId)

const detail = store.getTask({ tenantId: 1, taskId: success.osTaskId })
assert.equal(detail.executions.length, 2)
assert(detail.executions.every(execution => execution.runner === 'dsh'))
assert.equal(detail.checkpoints.length, 2)
assert(detail.checkpoints.every(checkpoint => JSON.parse(checkpoint.state_json).sessionId === 'session-abc'))
assert(detail.checkpoints.every(checkpoint => checkpoint.safe_to_resume === 1))
assert.equal(store.getTask({ tenantId: 2, taskId: success.osTaskId }), null)

console.log('AI-OS Phase 3 verification passed: DSH session mapping, external executions, checkpoints, tenant isolation')
