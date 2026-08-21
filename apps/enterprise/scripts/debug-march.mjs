import { init, db } from '../server/db.js'
init()
const rows = db.prepare("SELECT job_id, task_id, status, scheduled_at, started_at, finished_at, failure_reason, execution_id FROM runtime_scheduled_job WHERE task_id = 3 AND data_origin = 'real' ORDER BY job_id DESC LIMIT 5").all()
console.log('task3 real jobs:', rows.length)
for (const r of rows) console.log(JSON.stringify(r))
if (rows[0]?.failure_reason) {
  const e = db.prepare('SELECT error, substr(output,1,200) AS out FROM runtime_agent_execution WHERE execution_id = ?').get(rows[0].execution_id)
  console.log('执行详情:', JSON.stringify(e))
}
