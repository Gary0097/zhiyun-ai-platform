import assert from 'node:assert/strict'
import { DatabaseSync } from 'node:sqlite'
import { ensureOsSchema } from '../server/os/schema.js'
import { ExecutionKernel } from '../server/os/execution-kernel.js'
import { createLightweightRunner } from '../server/os/adapters/lightweight-runner.js'
import { createDshRunner } from '../server/os/adapters/dsh-runner.js'

const database = new DatabaseSync(':memory:')
database.exec('PRAGMA foreign_keys = ON')
database.exec('CREATE TABLE business_tenant (id INTEGER PRIMARY KEY)')
ensureOsSchema(database)
ensureOsSchema(database)

const expectedTables = [
  'runtime_task', 'runtime_task_plan', 'runtime_execution', 'runtime_process',
  'runtime_checkpoint', 'runtime_event', 'runtime_approval', 'runtime_artifact',
  'runtime_context_snapshot', 'capability_registry', 'capability_policy'
]
const actualTables = new Set(database.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all().map(row => row.name))
for (const table of expectedTables) assert(actualTables.has(table), `missing table ${table}`)

let lightweightCalls = 0
let dshCalls = 0
const kernel = new ExecutionKernel()
  .registerRunner('lightweight', createLightweightRunner({
    runAgent: async input => {
      lightweightCalls++
      assert.equal(input.agentId, 7)
      return { executionId: 1, traceId: 'trace-light', status: 'success', output: 'ok', latencyMs: 12 }
    }
  }))
  .registerRunner('dsh', createDshRunner({
    runSession: async input => {
      dshCalls++
      assert.equal(input.tenantId, 'tenant-a')
      return { executionId: 'dsh-1', traceId: 'trace-dsh', status: 'succeeded', output: 'ok' }
    }
  }))

const light = await kernel.run({ taskId: 'task-1', tenantId: 'tenant-a', agentId: 7, instruction: 'query' })
assert.equal(light.status, 'succeeded')
assert.equal(light.runner, 'lightweight')

const dsh = await kernel.run({
  taskId: 'task-2', tenantId: 'tenant-a', instruction: 'complex', metadata: { requiresApproval: true }
})
assert.equal(dsh.status, 'succeeded')
assert.equal(dsh.runner, 'dsh')
assert.equal(lightweightCalls, 1)
assert.equal(dshCalls, 1)

await assert.rejects(() => kernel.run({ taskId: 'missing-tenant', instruction: 'invalid' }), /tenantId is required/)
console.log(`AI-OS Phase 0 verification passed: ${expectedTables.length} tables, 2 runner routes, tenant guard`)
