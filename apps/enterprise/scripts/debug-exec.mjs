import { init, db } from '../server/db.js'
init()
const execs = db.prepare("SELECT execution_id, agent_id, status, substr(output,1,300) AS out FROM runtime_agent_execution WHERE data_origin='real' ORDER BY execution_id DESC LIMIT 5").all()
for (const e of execs) {
  console.log(`\n=== exec#${e.execution_id} agent=${e.agent_id} ${e.status} ===`)
  console.log('输出:', e.out)
  const tools = db.prepare('SELECT tool_name, status, substr(output,1,120) AS o FROM runtime_tool_execution WHERE execution_id = ?').all(e.execution_id)
  for (const t of tools) console.log(`  [${t.status}] ${t.tool_name} → ${t.o}`)
}
