const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor'])

function depthOf (value, depth = 0) {
  if (value === null || typeof value !== 'object') return depth
  return Math.max(depth, ...Object.entries(value).map(([key, child]) => {
    if (FORBIDDEN_KEYS.has(key)) throw new TypeError(`forbidden argument key: ${key}`)
    return depthOf(child, depth + 1)
  }))
}

export function evaluateToolRisk ({ toolName, sensitive, args = {}, userId = null, confirmed = false, writesEnabled = true, recentWrites = 0, writeLimit = 20 }) {
  const encoded = JSON.stringify(args)
  if (encoded.length > 16 * 1024) return { allowed: false, code: 'ARGUMENT_TOO_LARGE', reason: '工具参数超过 16KB 限制' }
  try {
    if (depthOf(args) > 6) return { allowed: false, code: 'ARGUMENT_TOO_DEEP', reason: '工具参数嵌套超过 6 层' }
  } catch (error) {
    return { allowed: false, code: 'UNSAFE_ARGUMENT_KEY', reason: error.message }
  }
  if (!sensitive) return { allowed: true, riskLevel: 'low' }
  if (!writesEnabled) return { allowed: false, code: 'WRITE_KILL_SWITCH', reason: '本租户高风险写操作已熔断' }
  if (!userId) return { allowed: false, code: 'AUTOMATION_WRITE_BLOCKED', reason: '自动任务禁止执行高风险写操作' }
  if (!confirmed) return { allowed: false, code: 'CONFIRM_REQUIRED', reason: `高风险操作需要当前用户明确确认：${toolName}`, pendingConfirm: true }
  if (recentWrites >= writeLimit) return { allowed: false, code: 'WRITE_RATE_LIMIT', reason: `高风险写操作超过每分钟 ${writeLimit} 次限制` }
  if (toolName === 'update_order') {
    if (!/^SO-[A-Za-z0-9-]{3,40}$/.test(String(args.order_no || ''))) return { allowed: false, code: 'INVALID_ORDER_NO', reason: '订单号格式不符合安全规则' }
    if (args.progress != null && (!Number.isFinite(Number(args.progress)) || Number(args.progress) < 0 || Number(args.progress) > 100)) return { allowed: false, code: 'INVALID_PROGRESS', reason: '订单进度必须在 0 到 100 之间' }
    if (args.risk_level != null && !['绿色', '黄色', '红色'].includes(args.risk_level)) return { allowed: false, code: 'INVALID_RISK_LEVEL', reason: '订单风险等级不在允许范围内' }
  }
  return { allowed: true, riskLevel: 'high' }
}

export function enforceToolRisk ({ database, now, tenantId, userId, traceId, toolName, sensitive, args, confirmed }) {
  const writesEnabled = database.prepare('SELECT value FROM business_setting WHERE key=?').get(`risk.write.enabled.${tenantId}`)?.value !== '0'
  const recentWrites = sensitive
    ? database.prepare("SELECT COUNT(*) c FROM audit_audit_log WHERE tenant_id=? AND category='risk.high.allowed' AND julianday(created_at) >= julianday('now','-1 minute')").get(tenantId).c
    : 0
  const decision = evaluateToolRisk({ toolName, sensitive, args, userId, confirmed, writesEnabled, recentWrites })
  if (sensitive || !decision.allowed) {
    database.prepare("INSERT INTO audit_audit_log (tenant_id, category, trace_id, payload, created_at, data_origin) VALUES (?,?,?,?,?,'real')")
      .run(tenantId, decision.allowed ? 'risk.high.allowed' : 'risk.blocked', traceId, JSON.stringify({ toolName, userId, code: decision.code || null, riskLevel: decision.riskLevel || 'high' }), now())
  }
  if (!decision.allowed) {
    const error = new Error(decision.reason)
    error.status = decision.pendingConfirm ? 202 : 403
    error.riskCode = decision.code
    error.pendingConfirm = decision.pendingConfirm ? { tool: toolName } : null
    throw error
  }
  return decision
}
