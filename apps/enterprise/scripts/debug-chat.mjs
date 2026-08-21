// 检查最近对话消息与 trace，定位乱码与跑偏
import { init, db } from '../server/db.js'
init()
console.log('=== 最近 12 条消息 ===')
const msgs = db.prepare('SELECT m.id, m.role, substr(m.content,1,120) c, m.conversation_id FROM runtime_message m ORDER BY m.id DESC LIMIT 12').all()
for (const m of msgs.reverse()) console.log(`[${m.role}] conv=${m.conversation_id}: ${m.c}`)
console.log('\n=== 最近 3 次 assistant 执行的 trace 链 ===')
const execs = db.prepare("SELECT execution_id, agent_id, trace_id, status, substr(input,1,80) inp FROM runtime_agent_execution WHERE data_origin='real' ORDER BY execution_id DESC LIMIT 3").all()
for (const e of execs) {
  console.log(`\n-- exec#${e.execution_id} agent=${e.agent_id} ${e.status} input=${e.inp}`)
  const tools = db.prepare('SELECT tool_name, status, substr(output,1,100) o FROM runtime_tool_execution WHERE execution_id = ? ORDER BY id').all(e.execution_id)
  for (const t of tools) console.log(`   [${t.status}] ${t.tool_name} → ${t.o}`)
}
console.log('\n=== 当前模型配置 ===')
import { readFileSync } from 'node:fs'
console.log(readFileSync('../config/model.json', 'utf8'))
