import { init, db, now } from '../server/db.js'
init()
// 复现 tick 的条件分支判断
const task = db.prepare("SELECT * FROM business_scheduled_task WHERE task_id = 3").get()
console.log('任务:', task.task_id, task.name, task.status, task.trigger_type, task.condition_expr)
const { evaluateCondition } = await import('../server/tools.js')
const ev = evaluateCondition(task.tenant_id, task.condition_tool, task.condition_expr)
console.log('条件评估:', JSON.stringify({ met: ev.met, detail: ev.detail }))
const cutoff = db.prepare("SELECT strftime('%Y-%m-%dT%H:%M:%S','now','-1 hour') AS c").get().c
console.log('1小时_cutoff:', cutoff)
const recent = db.prepare("SELECT job_id, status, scheduled_at FROM runtime_scheduled_job WHERE task_id = 3 AND data_origin='real' ORDER BY job_id DESC LIMIT 3").all()
for (const j of recent) console.log('job', j.job_id, j.status, j.scheduled_at, '阻塞?', j.scheduled_at >= cutoff)
const lock = db.prepare("SELECT job_id, status FROM runtime_scheduled_job WHERE task_id = 3 AND status IN ('pending','running','retrying')").all()
console.log('job_lock:', JSON.stringify(lock))
