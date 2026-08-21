// 身份认证与权限中心：Tenant + RBAC + Feature + Data Scope 四层模型
// API 层强制校验；tenant_id 一律由服务端 Context 注入，客户端不可指定
import { createHmac, timingSafeEqual } from 'node:crypto'
import { db, now } from './db.js'

const SECRET = process.env.ZHIYUN_SECRET || 'zhiyun-dev-secret-change-me'

export function signToken (payload) {
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
  const mac = createHmac('sha256', SECRET).update(body).digest('base64url')
  return `${body}.${mac}`
}

export function parseToken (token) {
  if (!token) return null
  const [body, mac] = token.split('.')
  if (!body || !mac) return null
  const expect = createHmac('sha256', SECRET).update(body).digest('base64url')
  if (expect.length !== mac.length || !timingSafeEqual(Buffer.from(expect), Buffer.from(mac))) return null
  try { return JSON.parse(Buffer.from(body, 'base64url').toString()) } catch { return null }
}

/** 从请求解析登录用户；失败抛 401 */
export function authenticate (req) {
  const header = req.headers.authorization || ''
  const token = header.startsWith('Bearer ') ? header.slice(7) : null
  const payload = parseToken(token)
  if (!payload) { const e = new Error('未认证'); e.status = 401; throw e }
  const user = db.prepare('SELECT * FROM business_user WHERE id = ? AND status = \'active\'').get(payload.uid)
  if (!user || user.tenant_id !== payload.tenant_id) { const e = new Error('会话失效'); e.status = 401; throw e }
  return user
}

export class PermissionError extends Error { constructor (msg) { super(msg); this.status = 403 } }

/** 功能权限校验：permission code 通配符支持 platform_admin */
export function requirePermission (user, code) {
  if (user.role === 'platform_admin') return
  const hit = db.prepare('SELECT 1 FROM business_role_permission WHERE role = ? AND (permission_code = ? OR permission_code = \'*\')').get(user.role, code)
  if (!hit) throw new PermissionError(`无权限：${code}（角色 ${user.role}）`)
}

/** 企业功能授权：未授权模块 API 直接拒绝（PRD §60） */
export function requireFeature (tenantId, featureCode) {
  const hit = db.prepare('SELECT enabled FROM business_tenant_feature WHERE tenant_id = ? AND feature_code = ?').get(tenantId, featureCode)
  if (!hit || !hit.enabled) throw new PermissionError(`企业未授权该功能模块：${featureCode}`)
}

/** 数据域：self / dept / dept_and_below / custom / tenant → SQL 片段与参数 */
export function dataScope (user) {
  switch (user.data_scope) {
    case 'self': return { clause: 'AND owner_id = ?', params: [user.id] }
    case 'dept': case 'dept_and_below': {
      const depts = [user.dept_id]
      if (user.data_scope === 'dept_and_below') {
        let frontier = [user.dept_id]
        while (frontier.length) {
          const rows = db.prepare(`SELECT id FROM business_department WHERE parent_id IN (${frontier.map(() => '?').join(',')})`).all(...frontier).map(r => r.id)
          frontier = rows.filter(id => !depts.includes(id))
          depts.push(...frontier)
        }
      }
      if (!depts.filter(Boolean).length) return { clause: 'AND 1=0', params: [] }
      return { clause: `AND dept_id IN (${depts.map(() => '?').join(',')})`, params: depts }
    }
    default: return { clause: '', params: [] } // tenant 全企业
  }
}

/** 记录操作日志（log_operation_log） */
export function logOperation ({ tenantId, userId, module, action, resourceType = null, resourceId = null, before = null, after = null, ip = null, userAgent = null }) {
  db.prepare(`INSERT INTO log_operation_log (tenant_id, user_id, module, action, resource_type, resource_id, before_data, after_data, ip, user_agent, created_at, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?,?, 'real')`)
    .run(tenantId, userId, module, action, resourceType, resourceId == null ? null : String(resourceId),
      before == null ? null : JSON.stringify(before), after == null ? null : JSON.stringify(after), ip, userAgent, now())
}
