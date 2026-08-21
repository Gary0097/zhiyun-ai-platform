import assert from 'node:assert/strict'
import { DatabaseSync } from 'node:sqlite'
import { ensureOsSchema } from '../server/os/schema.js'
import { RuntimeStore } from '../server/os/runtime-store.js'

const database = new DatabaseSync(':memory:')
database.exec(`
  PRAGMA foreign_keys=ON;
  CREATE TABLE business_tenant (id INTEGER PRIMARY KEY);
  CREATE TABLE runtime_scheduled_job (job_id INTEGER PRIMARY KEY, tenant_id INTEGER, status TEXT);
  CREATE TABLE audit_audit_log (audit_id INTEGER PRIMARY KEY, tenant_id INTEGER, category TEXT, trace_id TEXT, payload TEXT, created_at TEXT);
  INSERT INTO business_tenant VALUES (1), (2);
  INSERT INTO runtime_scheduled_job VALUES (1,1,'pending'), (2,2,'running');
  INSERT INTO audit_audit_log VALUES (1,1,'risk.blocked','trace-risk','{"toolName":"update_order","code":"AUTOMATION_WRITE_BLOCKED"}',datetime('now'));
`)
ensureOsSchema(database)
let sequence = 0
const store = new RuntimeStore({ database, id: () => `monitor-${++sequence}` })
const task = store.ensureSourceTask({ tenantId: 1, sourceType: 'work_task', sourceId: 1, title: '测试任务', objective: '测试监视器' })
const run = store.startExecution({ task, runner: 'lightweight', triggerType: 'task' })
store.finishExecution({ task, ...run, result: { status: 'failed', traceId: 'trace-exec', error: 'expected failure' } })
store.saveCheckpoint({ task, ...run, stepKey: 'attempt.completed', state: { status: 'failed' } })

const snapshot = store.monitorSnapshot({ tenantId: 1 })
assert.equal(snapshot.kpi.tasks, 1)
assert.equal(snapshot.kpi.queuedJobs, 1)
assert.equal(snapshot.kpi.failed24h, 1)
assert.equal(snapshot.kpi.checkpoints24h, 1)
assert.equal(snapshot.kpi.riskBlocked24h, 1)
assert.equal(snapshot.recentExecutions[0].title, '测试任务')
assert.equal(snapshot.risks[0].payload.code, 'AUTOMATION_WRITE_BLOCKED')
assert.equal(store.monitorSnapshot({ tenantId: 2 }).kpi.tasks, 0)

console.log('AI-OS Phase 5 verification passed: monitor KPIs, execution feed, risk feed, tenant isolation')
