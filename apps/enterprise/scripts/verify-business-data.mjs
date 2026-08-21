// 验证生成数据的体系性：财务派生/售后状态/订单状态机
import { init, db } from '../server/db.js'
init()
console.log('=== 财务月度（企业A，2026 年生成部分）===')
for (const r of db.prepare("SELECT month, category, amount FROM business_finance WHERE tenant_id=1 AND data_origin='generated' ORDER BY month, category LIMIT 9").all()) {
  console.log(` ${r.month} ${r.category}: ¥${Number(r.amount).toLocaleString()}`)
}
console.log('=== 售后工单状态分布 ===')
for (const r of db.prepare("SELECT status, COUNT(*) c FROM business_after_sale WHERE data_origin='generated' GROUP BY status").all()) {
  console.log(` ${r.status}: ${r.c}`)
}
console.log('=== 订单状态机（节点分布）===')
for (const r of db.prepare("SELECT current_node, COUNT(*) c, ROUND(AVG(progress)) p FROM business_order WHERE data_origin='generated' GROUP BY current_node").all()) {
  console.log(` ${r.current_node}: ${r.c} 单，平均进度 ${r.p}%`)
}
console.log('=== 各租户生成量 ===')
for (const r of db.prepare("SELECT tenant_id, COUNT(*) c, ROUND(SUM(amount)/10000) w FROM business_order WHERE data_origin='generated' GROUP BY tenant_id").all()) {
  console.log(` 租户${r.tenant_id}: ${r.c} 单，总额 ¥${Number(r.w).toLocaleString()} 万`)
}
