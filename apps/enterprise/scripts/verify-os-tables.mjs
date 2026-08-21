// 验证 OS 表已在真实库建立且原有数据无损
import { init, db } from '../server/db.js'
init()
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'runtime_tas%' OR name LIKE 'runtime_exec%' OR name LIKE 'runtime_process%' OR name LIKE 'runtime_event%' OR name LIKE 'capability%') ORDER BY name").all().map(r => r.name)
console.log('OS 表（真实库）:', tables.join(', '))
console.log('共', tables.length, '张')
console.log('租户:', db.prepare('SELECT COUNT(*) c FROM business_tenant').get().c, '家')
console.log('执行历史:', db.prepare('SELECT COUNT(*) c FROM runtime_agent_execution').get().c, '条')
console.log('知识条目:', db.prepare('SELECT COUNT(*) c FROM business_knowledge_item').get().c, '条')
console.log('发票:', db.prepare('SELECT COUNT(*) c FROM business_invoice').get().c, '张')
