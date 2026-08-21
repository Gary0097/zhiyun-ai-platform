import { init, db } from '../server/db.js'
init()
// 完全复刻 simulator.js 的租户构建逻辑
const tenantIds = db.prepare('SELECT id FROM business_tenant WHERE status = \'active\'').all().map(r => r.id)
console.log('tenantIds:', JSON.stringify(tenantIds))
function mulberry32 (seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed)
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}
const rnd = mulberry32(1)
const tenants = tenantIds.map(id => {
  const users = db.prepare("SELECT id FROM business_user WHERE tenant_id = ? AND status = 'active'").all(id).map(r => r.id)
  const agents = db.prepare("SELECT agent_id, agent_name, model, version FROM business_agent WHERE tenant_id = ? AND status = 'published'").all(id)
  const tools = JSON.parse(db.prepare('SELECT tool_ids FROM business_agent WHERE tenant_id = ? AND status = \'published\' LIMIT 1').get(id)?.tool_ids || '[]')
  const features = db.prepare('SELECT feature_code FROM business_tenant_feature WHERE tenant_id = ? AND enabled = 1').all(id).map(r => r.feature_code)
  const tasks = db.prepare("SELECT task_id, agent_id, name FROM business_scheduled_task WHERE tenant_id = ? AND status = 'active'").all(id)
  return { id, users, agents, tools, features, tasks, weight: 0.5 + rnd() }
}).filter(t => t.agents.length && t.users.length)
console.log('tenants:', tenants.length, JSON.stringify(tenants.map(t => ({ id: t.id, u: t.users.length, a: t.agents.length, w: t.weight.toFixed(2), tools: t.tools.length }))))
