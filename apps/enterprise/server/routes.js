// REST API：所有业务端点强制 认证 → 权限 → 功能授权 → 租户注入
import { join } from 'node:path'
import { db, now, verifyPassword, hashPassword, DATA_DIR } from './db.js'
import { authenticate, requirePermission, requireFeature, logOperation, signToken, PermissionError } from './auth.js'
import { runAgent, replayTrace } from './harness.js'
import { runTaskNow, tick } from './scheduler.js'
import { simulate, clearSimulated } from './simulator.js'
import { generateBusinessData, clearGeneratedBusinessData, generatedBusinessStats } from './business-generator.js'
import { startAutoRun, stopAutoRun, autoRunStatus, autoRunAnalytics, runJhlReport, jhlReport, runMultiAgentTest, runFeatureDemo, recentAutoExecutions, recentAutoMessages } from './auto-run.js'
import { FUNCTION_CATALOG, catalogByModule } from './function-catalog.js'
import { runKnowledgeHarvest, harvestStatus } from './knowledge-harvester.js'
import { modelInfo } from './llm.js'

export function route (method, path, handler, opts = {}) {
  return { method, path, handler, ...opts }
}

const J = (d) => JSON.stringify(d)
const readBody = (req) => new Promise((resolve) => { let b = ''; req.on('data', c => { b += c }); req.on('end', () => { try { resolve(b ? JSON.parse(b) : {}) } catch { resolve({}) } }) })

// 可通过数据管理中心编辑的业务表白名单
const EDITABLE_TABLES = ['business_customer', 'business_order', 'business_inventory', 'business_finance', 'business_after_sale', 'business_department']

export function buildRoutes () {
  const R = []
  const H = (method, path, handler, opt) => R.push(route(method, path, handler, opt))

  // ---- Agent 对话（聊天）----
  const loadConv = (user, id) => {
    const c = db.prepare('SELECT * FROM runtime_conversation WHERE id = ?').get(id)
    if (!c || c.tenant_id !== user.tenant_id) throw Object.assign(new Error('会话不存在'), { status: 404 })
    return c
  }
  H('GET', '/api/conversations', (req, res, { user }) => db.prepare(
    'SELECT c.id, c.title, c.agent_id, c.created_at, a.agent_name, (SELECT COUNT(*) FROM runtime_message m WHERE m.conversation_id = c.id) AS msg_count FROM runtime_conversation c LEFT JOIN business_agent a ON a.agent_id = c.agent_id WHERE c.tenant_id = ? AND c.user_id = ? ORDER BY c.id DESC LIMIT 50').all(user.tenant_id, user.id))
  H('POST', '/api/conversations', async (req, res, { user }) => {
    const b = await readBody(req)
    const agent = db.prepare("SELECT * FROM business_agent WHERE agent_id = ? AND status = 'published'").get(b.agent_id)
    if (!agent || agent.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在或未发布'), { status: 404 })
    const id = db.prepare('INSERT INTO runtime_conversation (tenant_id, user_id, agent_id, title, created_at, data_origin) VALUES (?,?,?,?,?, \'real\')')
      .run(user.tenant_id, user.id, agent.agent_id, b.title || '新对话', now()).lastInsertRowid
    return { id: Number(id) }
  })
  H('GET', '/api/conversations/:id/messages', (req, res, { user, params }) => {
    loadConv(user, params.id)
    return db.prepare('SELECT id, role, content, created_at FROM runtime_message WHERE conversation_id = ? ORDER BY id').all(params.id)
  })
  H('DELETE', '/api/conversations/:id', (req, res, { user, params }) => {
    loadConv(user, params.id)
    db.prepare('DELETE FROM runtime_message WHERE conversation_id = ?').run(params.id)
    db.prepare('DELETE FROM runtime_conversation WHERE id = ?').run(params.id)
    return { ok: true }
  })
  H('POST', '/api/conversations/:id/chat', async (req, res, { user, params }) => {
    const conv = loadConv(user, params.id)
    const b = await readBody(req)
    const content = String(b.content || '').trim()
    if (!content) throw Object.assign(new Error('消息不能为空'), { status: 400 })
    // 乱码检测：U+FFFD 替换符说明传输编码损坏，提示重发而不是让模型猜测语义
    if (content.includes('�')) throw Object.assign(new Error('消息编码异常（含乱码字符），请重新输入后再发送'), { status: 400 })
    db.prepare("INSERT INTO runtime_message (conversation_id, role, content, created_at, data_origin) VALUES (?, 'user', ?, ?, 'real')").run(conv.id, content, now())
    db.prepare('UPDATE runtime_conversation SET title = ? WHERE id = ? AND title = ?').run(content.slice(0, 24), conv.id, '新对话')
    const result = await runAgent({ agentId: conv.agent_id, user, instruction: content, triggerType: 'chat' })
    db.prepare("INSERT INTO runtime_message (conversation_id, role, content, created_at, data_origin) VALUES (?, 'assistant', ?, ?, 'real')")
      .run(conv.id, result.output, now())
    return { reply: result.output, traceId: result.traceId, executionId: result.executionId, status: result.status }
  })
  // 会话内可用 Agent（对话入口）
  H('GET', '/api/chat/agents', (req, res, { user }) => db.prepare(
    "SELECT agent_id, agent_name, agent_type, CASE WHEN agent_type = 'assistant' THEN 0 ELSE 1 END AS sort FROM business_agent WHERE tenant_id = ? AND status = 'published' ORDER BY sort, agent_id").all(user.tenant_id))

  // ---- 采购数据看板（真实发票聚合 + 本地 AI 洞察）----
  H('GET', '/api/invoices', (req, res, { user }) => {
    requirePermission(user, 'finance:view')
    return db.prepare('SELECT invoice_id, invoice_no, invoice_date, supplier, category, amount_excl_tax, tax, amount_total, note, data_origin FROM business_invoice WHERE tenant_id = ? ORDER BY invoice_date').all(user.tenant_id)
  })
  H('GET', '/api/invoices/:id/items', (req, res, { user, params }) => {
    requirePermission(user, 'finance:view')
    const inv = db.prepare('SELECT invoice_id FROM business_invoice WHERE invoice_id = ? AND tenant_id = ?').get(params.id, user.tenant_id)
    if (!inv) throw Object.assign(new Error('发票不存在'), { status: 404 })
    return db.prepare('SELECT item_name, spec, qty, unit_price, amount, tax FROM business_invoice_item WHERE invoice_id = ? ORDER BY amount DESC').all(params.id)
  })
  H('GET', '/api/stats/procurement', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    const t = user.tenant_id
    const one = (sql, p = []) => db.prepare(sql).get(...p)
    const months = db.prepare(`SELECT substr(invoice_date,1,7) AS month, COUNT(*) AS n, SUM(amount_total) AS amount, SUM(tax) AS tax
      FROM business_invoice WHERE tenant_id = ? GROUP BY month ORDER BY month`).all(t)
    const suppliers = db.prepare(`SELECT supplier, COUNT(*) AS n, SUM(amount_total) AS amount, MAX(invoice_date) AS last_date
      FROM business_invoice WHERE tenant_id = ? GROUP BY supplier ORDER BY amount DESC`).all(t)
    const categories = db.prepare(`SELECT category, SUM(amount_total) AS amount
      FROM business_invoice WHERE tenant_id = ? GROUP BY category ORDER BY amount DESC`).all(t)
    const topItems = db.prepare(`SELECT t.item_name, SUM(t.qty) AS qty, SUM(t.amount) AS amount
      FROM business_invoice_item t WHERE t.tenant_id = ? GROUP BY t.item_name ORDER BY amount DESC LIMIT 10`).all(t)
    return {
      kpi: {
        invoice_count: one('SELECT COUNT(*) c FROM business_invoice WHERE tenant_id=?', [t]).c,
        supplier_count: suppliers.length,
        total: one('SELECT COALESCE(SUM(amount_total),0) c FROM business_invoice WHERE tenant_id=?', [t]).c,
        tax_total: one('SELECT COALESCE(SUM(tax),0) c FROM business_invoice WHERE tenant_id=?', [t]).c,
        item_count: one('SELECT COUNT(*) c FROM business_invoice_item WHERE tenant_id=?', [t]).c,
        top_supplier: suppliers[0]?.supplier || '-'
      },
      months, suppliers, categories, topItems
    }
  })
  // AI 智能洞察：本地模型分析全量真实数据（缓存于 business_setting，refresh=1 强制重跑）
  H('GET', '/api/stats/ai-insight', async (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    const url = new URL(req.url, 'http://x')
    const refresh = url.searchParams.get('refresh') === '1'
    const cacheKey = `ai.insight.${user.tenant_id}`
    const cached = db.prepare('SELECT value, updated_at FROM business_setting WHERE key = ?').get(cacheKey)
    if (!refresh && cached?.value) return { insight: cached.value, generated_at: cached.updated_at, cached: true }

    const t = user.tenant_id
    const invs = db.prepare('SELECT invoice_no, invoice_date, supplier, category, amount_total FROM business_invoice WHERE tenant_id = ? ORDER BY invoice_date').all(t)
    if (!invs.length) return { insight: '', generated_at: null, cached: false, empty: true }
    const bySupplier = {}
    const byCategory = {}
    const byMonth = {}
    for (const i of invs) {
      bySupplier[i.supplier] = (bySupplier[i.supplier] || 0) + i.amount_total
      byCategory[i.category] = (byCategory[i.category] || 0) + i.amount_total
      byMonth[i.invoice_date.slice(0, 7)] = (byMonth[i.invoice_date.slice(0, 7)] || 0) + i.amount_total
    }
    const topItems = db.prepare('SELECT item_name, SUM(qty) qty, SUM(amount) amt FROM business_invoice_item WHERE tenant_id = ? GROUP BY item_name ORDER BY amt DESC LIMIT 8').all(t)
    const data = {
      发票数: invs.length,
      价税合计: Math.round(invs.reduce((s, i) => s + i.amount_total, 0)),
      月度: byMonth, 供应商: bySupplier, 品类: byCategory,
      高额物料TOP8: topItems.map(x => ({ 名称: x.item_name, 数量: x.qty, 金额: Math.round(x.amt) })),
      发票列表: invs.map(i => ({ 日期: i.invoice_date, 供应商: i.supplier, 品类: i.category, 金额: i.amount_total }))
    }
    const { chat } = await import('./llm.js')
    const res2 = await chat([
      { role: 'system', content: `你是资深采购与供应链分析师。基于用户企业的真实发票数据（JSON）撰写看板洞察。要求：
1. 用中文分 3-5 段，每段一个主题：总体规模、供应商结构与集中度、品类结构、月度趋势、采购建议。
2. 必须引用具体数字（金额、占比、供应商名）。
3. 指出供应商集中风险与可优化点，给出可执行建议。
4. 直接输出 markdown 文本（可用 **加粗**、- 列表），不要输出 JSON，不要寒暄。` },
      { role: 'user', content: '分析以下企业采购发票数据：\n' + JSON.stringify(data) }
    ], [])
    const insight = res2.content || ''
    db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at')
      .run(cacheKey, insight, now())
    return { insight, generated_at: now(), cached: false }
  })

  // ---- 系统设置（品牌 / Logo / dsh 工作台入口）----
  H('GET', '/api/settings/brand', () => {
    const get = (k) => db.prepare('SELECT value FROM business_setting WHERE key = ?').get(k)?.value || ''
    return { name: get('brand.name'), logo: get('brand.logo') ? '/logo.png' : '' }
  })
  H('PUT', '/api/settings/brand', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    if (b.name) db.prepare("UPDATE business_setting SET value = ?, updated_at = ? WHERE key = 'brand.name'").run(String(b.name).slice(0, 60), now())
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '修改系统名称', after: { name: b.name } })
    return { ok: true }
  })
  H('POST', '/api/settings/logo', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    const m = String(b.data || '').match(/^data:image\/(png|jpeg|jpg|svg\+xml|webp|gif);base64,(.+)$/)
    if (!m) throw Object.assign(new Error('仅支持 png/jpeg/svg/webp/gif 图片（dataURL）'), { status: 400 })
    if (m[2].length > 2 * 1024 * 1024) throw Object.assign(new Error('图片过大（>1.5MB）'), { status: 400 })
    const { writeFileSync } = await import('node:fs')
    const ext = m[1].replace('svg+xml', 'svg').replace('jpeg', 'jpg')
    writeFileSync(join(DATA_DIR, 'logo.' + ext), Buffer.from(m[2], 'base64'))
    db.prepare("UPDATE business_setting SET value = ?, updated_at = ? WHERE key = 'brand.logo'").run('logo.' + ext, now())
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '修改系统 Logo', after: { file: 'logo.' + ext } })
    return { ok: true, logo: '/logo.png' }
  })
  H('DELETE', '/api/settings/logo', (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    db.prepare("UPDATE business_setting SET value = '', updated_at = ? WHERE key = 'brand.logo'").run(now())
    return { ok: true }
  })
  // 所有登录用户可读（AI 对话页需要拿管理员配置的工作台地址）；写入仍限管理员
  H('GET', '/api/settings/dsh', (req, res, { user }) => {
    return { url: db.prepare('SELECT value FROM business_setting WHERE key = ?').get('dsh.url')?.value || '' }
  })
  H('PUT', '/api/settings/dsh', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    db.prepare("UPDATE business_setting SET value = ?, updated_at = ? WHERE key = 'dsh.url'").run(String(b.url || '').slice(0, 200), now())
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '修改 dsh 工作台地址', after: { url: b.url } })
    return { ok: true }
  })

  // ---- 认证 ----
  H('POST', '/api/auth/login', async (req) => {
    const body = await readBody(req)
    const user = db.prepare('SELECT * FROM business_user WHERE username = ?').get(body.username || '')
    const fail = () => {
      db.prepare("INSERT INTO log_login_log (tenant_id, user_id, ip, user_agent, success, created_at, data_origin) VALUES (0,null,?, ?,0,?, 'real')")
        .run(req.socket.remoteAddress || '-', req.headers['user-agent'] || '', now())
      throw Object.assign(new Error('用户名或密码错误'), { status: 401 })
    }
    if (!user || !verifyPassword(body.password || '', user.password_hash)) fail()
    const token = signToken({ uid: user.id, tenant_id: user.tenant_id, role: user.role })
    db.prepare("INSERT INTO log_login_log (tenant_id, user_id, ip, user_agent, success, created_at, data_origin) VALUES (?,?,?,?,1,?, 'real')")
      .run(user.tenant_id, user.id, req.socket.remoteAddress || '-', req.headers['user-agent'] || '', now())
    return { token, user: { id: user.id, username: user.username, display_name: user.display_name, role: user.role, tenant_id: user.tenant_id, data_scope: user.data_scope } }
  })
  H('GET', '/api/auth/me', (req, res, { user }) => {
    const tenant = db.prepare('SELECT id, name, code FROM business_tenant WHERE id = ?').get(user.tenant_id)
    const features = db.prepare('SELECT feature_code FROM business_tenant_feature WHERE tenant_id = ? AND enabled = 1').all(user.tenant_id).map(r => r.feature_code)
    const perms = user.role === 'platform_admin' ? ['*'] : db.prepare('SELECT permission_code FROM business_role_permission WHERE role = ?').all(user.role).map(r => r.permission_code)
    return { user: { id: user.id, username: user.username, display_name: user.display_name, role: user.role, data_scope: user.data_scope, dept_id: user.dept_id }, tenant, features, perms }
  })

  // ---- 系统管理：租户/用户/部门/角色/功能授权 ----
  H('GET', '/api/tenants', (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    return db.prepare('SELECT t.*, (SELECT COUNT(*) FROM business_user u WHERE u.tenant_id = t.id) AS user_count FROM business_tenant t ORDER BY t.id').all()
  })
  H('POST', '/api/tenants', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    if (user.role !== 'platform_admin') throw new PermissionError('仅平台超级管理员可创建企业')
    const b = await readBody(req)
    const id = db.prepare("INSERT INTO business_tenant (code, name, status, data_origin, created_at) VALUES (?,?,'active','manual',?)").run(b.code, b.name, now()).lastInsertRowid
    for (const t of ['data_center', 'order_center', 'ai_center', 'log_center']) db.prepare('INSERT INTO business_tenant_feature VALUES (?, ?, 1)').run(id, t)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '创建企业', resourceType: 'tenant', resourceId: id, after: b })
    return { id: Number(id) }
  })
  H('GET', '/api/users', (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const tenantId = user.role === 'platform_admin' && req.url.includes('all=1') ? null : user.tenant_id
    const rows = tenantId
      ? db.prepare('SELECT id, username, display_name, dept_id, title, role, data_scope, status FROM business_user WHERE tenant_id = ?').all(tenantId)
      : db.prepare('SELECT u.id, u.username, u.display_name, u.title, u.role, u.status, t.name AS tenant FROM business_user u JOIN business_tenant t ON t.id = u.tenant_id').all()
    return rows
  })
  H('POST', '/api/users', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    if (user.role !== 'platform_admin' && Number(b.tenant_id) !== user.tenant_id) throw new PermissionError('不得为其他企业创建用户')
    const id = db.prepare('INSERT INTO business_user (tenant_id, username, password_hash, display_name, dept_id, title, role, data_scope, data_origin, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)')
      .run(b.tenant_id || user.tenant_id, b.username, hashPassword(b.password || 'Zhiyun@2026'), b.display_name, b.dept_id || null, b.title || null, b.role || 'employee', b.data_scope || 'self', 'manual', now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '创建用户', resourceType: 'user', resourceId: id, after: { username: b.username, role: b.role } })
    return { id: Number(id) }
  })
  H('GET', '/api/departments', (req, res, { user }) => db.prepare('SELECT d.*, t.name AS tenant FROM business_department d JOIN business_tenant t ON t.id = d.tenant_id WHERE d.tenant_id = ?').all(user.tenant_id))
  H('GET', '/api/features', (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    return {
      features: db.prepare('SELECT * FROM business_feature').all(),
      matrix: db.prepare('SELECT tenant_id, feature_code, enabled FROM business_tenant_feature').all()
    }
  })
  H('PUT', '/api/features', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    const before = db.prepare('SELECT enabled FROM business_tenant_feature WHERE tenant_id = ? AND feature_code = ?').get(b.tenant_id, b.feature_code)
    db.prepare('INSERT INTO business_tenant_feature VALUES (?,?,?) ON CONFLICT(tenant_id, feature_code) DO UPDATE SET enabled = excluded.enabled').run(b.tenant_id, b.feature_code, b.enabled ? 1 : 0)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '修改企业功能授权', resourceType: 'tenant_feature', resourceId: `${b.tenant_id}:${b.feature_code}`, before, after: b })
    return { ok: true }
  })
  H('GET', '/api/roles', () => ({
    roles: [
      { code: 'platform_admin', name: 'Platform Super Admin' }, { code: 'tenant_admin', name: 'Tenant Admin' },
      { code: 'dept_admin', name: 'Department Admin' }, { code: 'employee', name: 'Employee' }, { code: 'auditor', name: 'Auditor' }
    ],
    permissions: db.prepare('SELECT * FROM business_permission').all(),
    role_permissions: db.prepare('SELECT * FROM business_role_permission').all()
  }))

  // ---- AI 中心：Agent / Skill / Tool ----
  const agentVisible = (user) => user.role === 'platform_admin' ? '' : 'WHERE tenant_id = ?'
  H('GET', '/api/agents', (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    const where = agentVisible(user)
    return db.prepare(`SELECT a.*, (SELECT COUNT(*) FROM runtime_agent_execution e WHERE e.agent_id = a.agent_id) AS run_count FROM business_agent a ${where}`).all(...(where ? [user.tenant_id] : []))
  })
  H('POST', '/api/agents', async (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    const b = await readBody(req)
    const toolIds = Array.isArray(b.tool_ids) ? b.tool_ids : []
    // 校验工具确属本企业已注册
    const owned = db.prepare('SELECT tool_name FROM business_tool WHERE tenant_id = ?').all(user.tenant_id).map(r => r.tool_name)
    const bad = toolIds.filter(t => !owned.includes(t))
    if (bad.length) throw Object.assign(new Error(`未授权工具：${bad.join(',')}`), { status: 400 })
    const id = db.prepare(`INSERT INTO business_agent (tenant_id, agent_name, agent_type, system_prompt, model, temperature, tool_ids, skill_ids, knowledge_ids, permission_scope, status, version, created_by, updated_at, data_origin)
      VALUES (?,?,?,?,?,?,?,?,?,?,'draft',1,?,?, 'manual')`)
      .run(user.tenant_id, b.agent_name || '未命名 Agent', b.agent_type || 'custom', b.system_prompt || '输出 JSON', b.model || modelInfo().model, b.temperature ?? 0.3,
        JSON.stringify(toolIds), JSON.stringify(b.skill_ids || []), JSON.stringify(b.knowledge_ids || []), b.permission_scope || 'tenant', user.id, now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '创建Agent', resourceType: 'agent', resourceId: id, after: { agent_name: b.agent_name } })
    return { agent_id: Number(id) }
  })
  H('PUT', '/api/agents/:id', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const agent = db.prepare('SELECT * FROM business_agent WHERE agent_id = ?').get(params.id)
    if (!agent || agent.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在'), { status: 404 })
    const b = await readBody(req)
    db.prepare('UPDATE business_agent SET agent_name=?, agent_type=?, system_prompt=?, model=?, temperature=?, tool_ids=?, skill_ids=?, permission_scope=?, updated_at=? WHERE agent_id=?')
      .run(b.agent_name ?? agent.agent_name, b.agent_type ?? agent.agent_type, b.system_prompt ?? agent.system_prompt, b.model ?? agent.model, b.temperature ?? agent.temperature,
        b.tool_ids ? JSON.stringify(b.tool_ids) : agent.tool_ids, b.skill_ids ? JSON.stringify(b.skill_ids) : agent.skill_ids, b.permission_scope ?? agent.permission_scope, now(), params.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '修改Agent', resourceType: 'agent', resourceId: params.id, before: { agent_name: agent.agent_name, system_prompt: agent.system_prompt }, after: b })
    return { ok: true }
  })
  H('POST', '/api/agents/:id/copy', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const a = db.prepare('SELECT * FROM business_agent WHERE agent_id = ?').get(params.id)
    if (!a || a.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在'), { status: 404 })
    const id = db.prepare(`INSERT INTO business_agent (tenant_id, agent_name, agent_type, system_prompt, model, temperature, tool_ids, skill_ids, knowledge_ids, permission_scope, status, version, created_by, updated_at, data_origin)
      VALUES (?,?,?,?,?,?,?,?,?,?, 'draft', 1, ?, ?, 'manual')`)
      .run(a.tenant_id, a.agent_name + '（副本）', a.agent_type, a.system_prompt, a.model, a.temperature, a.tool_ids, a.skill_ids, a.knowledge_ids, a.permission_scope, user.id, now()).lastInsertRowid
    return { agent_id: Number(id) }
  })
  H('POST', '/api/agents/:id/publish', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const a = db.prepare('SELECT * FROM business_agent WHERE agent_id = ?').get(params.id)
    if (!a || a.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在'), { status: 404 })
    db.prepare('UPDATE business_agent SET status = ?, updated_at = ? WHERE agent_id = ?').run('published', now(), params.id)
    db.prepare('INSERT INTO business_agent_version (agent_id, version, snapshot, published_at, published_by) VALUES (?,?,?,?,?)')
      .run(params.id, a.version, JSON.stringify({ agent_name: a.agent_name, system_prompt: a.system_prompt, tool_ids: JSON.parse(a.tool_ids) }), now(), user.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '发布Agent', resourceType: 'agent', resourceId: params.id, after: { version: a.version } })
    return { ok: true }
  })
  H('POST', '/api/agents/:id/disable', (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    db.prepare('UPDATE business_agent SET status = ?, updated_at = ? WHERE agent_id = ? AND tenant_id = ?').run('disabled', now(), params.id, user.tenant_id)
    return { ok: true }
  })
  H('GET', '/api/agents/:id/versions', (req, res, { user, params }) => {
    const a = db.prepare('SELECT tenant_id FROM business_agent WHERE agent_id = ?').get(params.id)
    if (!a || a.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在'), { status: 404 })
    return db.prepare('SELECT * FROM business_agent_version WHERE agent_id = ? ORDER BY version DESC').all(params.id)
  })
  H('POST', '/api/agents/:id/restore', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const b = await readBody(req)
    const v = db.prepare('SELECT * FROM business_agent_version WHERE agent_id = ? AND version = ?').get(params.id, b.version)
    const a = db.prepare('SELECT * FROM business_agent WHERE agent_id = ?').get(params.id)
    if (!v || !a || a.tenant_id !== user.tenant_id) throw Object.assign(new Error('版本不存在'), { status: 404 })
    const snap = JSON.parse(v.snapshot)
    db.prepare('UPDATE business_agent SET agent_name=?, system_prompt=?, tool_ids=?, updated_at=? WHERE agent_id=?')
      .run(snap.agent_name, snap.system_prompt, JSON.stringify(snap.tool_ids || []), now(), params.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '恢复Agent历史版本', resourceType: 'agent', resourceId: params.id, before: { version: a.version }, after: { version: b.version } })
    return { ok: true }
  })
  H('DELETE', '/api/agents/:id', (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const a = db.prepare('SELECT * FROM business_agent WHERE agent_id = ?').get(params.id)
    if (!a || a.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在'), { status: 404 })
    db.prepare('DELETE FROM business_agent WHERE agent_id = ?').run(params.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '删除Agent', resourceType: 'agent', resourceId: params.id, before: { agent_name: a.agent_name } })
    return { ok: true }
  })
  // Agent 测试运行（PRD §6 必须支持"测试"）
  H('POST', '/api/agents/:id/test', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const b = await readBody(req)
    return runAgent({ agentId: Number(params.id), user, instruction: b.instruction || '请执行你的职责。', triggerType: 'manual', confirmedTool: b.confirmed_tool || null })
  })
  // 敏感工具人工确认后执行
  H('POST', '/api/executions/:id/confirm', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const exec = db.prepare('SELECT * FROM runtime_agent_execution WHERE execution_id = ?').get(params.id)
    if (!exec || exec.tenant_id !== user.tenant_id) throw Object.assign(new Error('执行记录不存在'), { status: 404 })
    const pending = db.prepare("SELECT * FROM runtime_tool_execution WHERE execution_id = ? AND status = 'pending_confirm'").all(params.id)
    const { executeTool } = await import('./tools.js')
    for (const p of pending) {
      executeTool({ tenantId: exec.tenant_id, userId: user.id, traceId: exec.trace_id, executionId: exec.execution_id, toolName: p.tool_name, args: JSON.parse(p.input || '{}'), agentToolIds: null, confirmed: true })
    }
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '人工确认敏感工具执行', resourceType: 'execution', resourceId: params.id })
    return { confirmed: pending.length }
  })

  H('GET', '/api/skills', () => db.prepare('SELECT * FROM business_skill').all())
  H('POST', '/api/skills', async (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    const b = await readBody(req)
    const id = db.prepare('INSERT INTO business_skill (name, description, kind, data_origin) VALUES (?,?,?,?)').run(b.name, b.description, b.kind || 'custom', 'manual').lastInsertRowid
    return { skill_id: Number(id) }
  })
  H('GET', '/api/tools', (req, res, { user }) => db.prepare('SELECT * FROM business_tool WHERE tenant_id = ?').all(user.tenant_id))
  H('PUT', '/api/tools/:id', async (req, res, { user, params }) => {
    requirePermission(user, 'tool:manage')
    const b = await readBody(req)
    db.prepare('UPDATE business_tool SET enabled = ?, sensitive = ? WHERE tool_id = ? AND tenant_id = ?').run(b.enabled ? 1 : 0, b.sensitive ? 1 : 0, params.id, user.tenant_id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '修改Tool配置', resourceType: 'tool', resourceId: params.id, after: b })
    return { ok: true }
  })
  H('GET', '/api/model', () => modelInfo())
  // 模型配置在线编辑（系统设置 → 模型配置）
  H('PUT', '/api/model', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    const { updateModelConfig } = await import('./llm.js')
    const info = updateModelConfig(b)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'system', action: '修改模型配置', after: { baseURL: info.baseURL, model: info.model, mock: info.mock } })
    return info
  })
  H('POST', '/api/model/test', async (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    const b = await readBody(req)
    const { testModelConnection, loadModelConfig } = await import('./llm.js')
    // 优先用提交的草稿测试（不落盘），否则测当前生效配置
    const cfg = (b.baseURL || b.model) ? { ...loadModelConfig(), ...b } : null
    return testModelConnection(cfg)
  })

  // ---- 业务数据中心 ----
  H('GET', '/api/orders', (req, res, { user }) => {
    requirePermission(user, 'order:view')
    const url = new URL(req.url, 'http://x')
    const tenantId = Number(url.searchParams.get('tenant_id')) || user.tenant_id
    if (tenantId !== user.tenant_id && user.role !== 'platform_admin') throw new PermissionError('跨租户访问被拒绝')
    return db.prepare('SELECT * FROM business_order WHERE tenant_id = ? ORDER BY id').all(tenantId)
  })
  H('GET', '/api/dashboard/orders', (req, res, { user }) => {
    requirePermission(user, 'order:view')
    return db.prepare('SELECT current_node, COUNT(*) AS n, AVG(progress) AS avg_progress, SUM(delay_hours) AS total_delay FROM business_order WHERE tenant_id = ? GROUP BY current_node').all(user.tenant_id)
  })
  H('GET', '/api/dashboard/risks', (req, res, { user }) => {
    requirePermission(user, 'order:view')
    return db.prepare('SELECT risk_level, COUNT(*) AS n FROM business_order WHERE tenant_id = ? GROUP BY risk_level').all(user.tenant_id)
  })
  H('GET', '/api/inventory', (req, res, { user }) => db.prepare('SELECT *, (stock < safety_stock) AS low FROM business_inventory WHERE tenant_id = ?').all(user.tenant_id))

  // ---- 自动化中心 ----
  H('GET', '/api/tasks', (req, res, { user }) => {
    requirePermission(user, 'task:manage')
    return db.prepare('SELECT t.*, a.agent_name FROM business_scheduled_task t JOIN business_agent a ON a.agent_id = t.agent_id WHERE t.tenant_id = ? ORDER BY t.task_id').all(user.tenant_id)
  })
  H('POST', '/api/tasks', async (req, res, { user }) => {
    requirePermission(user, 'task:manage')
    const b = await readBody(req)
    const id = db.prepare(`INSERT INTO business_scheduled_task (tenant_id, agent_id, name, trigger_type, cron, interval_seconds, condition_tool, condition_expr, input, status, max_retry, timeout_seconds, created_by, created_at, data_origin)
      VALUES (?,?,?,?,?,?,?,?,?,'active',2,300,?,?, 'manual')`)
      .run(user.tenant_id, b.agent_id, b.name || '新任务', b.trigger_type || 'cron', b.cron || null, b.interval_seconds || null, b.condition_tool || null, b.condition_expr || null,
        JSON.stringify(b.input || { instruction: '执行任务' }), user.id, now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'automation', action: '创建任务', resourceType: 'scheduled_task', resourceId: id, after: b })
    return { task_id: Number(id) }
  })
  H('PUT', '/api/tasks/:id', async (req, res, { user, params }) => {
    requirePermission(user, 'task:manage')
    const b = await readBody(req)
    const t = db.prepare('SELECT * FROM business_scheduled_task WHERE task_id = ?').get(params.id)
    if (!t || t.tenant_id !== user.tenant_id) throw Object.assign(new Error('任务不存在'), { status: 404 })
    db.prepare('UPDATE business_scheduled_task SET name=?, cron=?, interval_seconds=?, input=?, status=? WHERE task_id=?')
      .run(b.name ?? t.name, b.cron ?? t.cron, b.interval_seconds ?? t.interval_seconds, b.input ? JSON.stringify(b.input) : t.input, b.status ?? t.status, params.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'automation', action: '修改任务', resourceType: 'scheduled_task', resourceId: params.id, before: { name: t.name, cron: t.cron }, after: b })
    return { ok: true }
  })
  H('POST', '/api/tasks/:id/run', async (req, res, { user, params }) => {
    requirePermission(user, 'task:manage')
    return runTaskNow(Number(params.id), 'manual', null, user)
  })
  H('POST', '/api/tasks/:id/pause', (req, res, { user, params }) => {
    requirePermission(user, 'task:manage')
    db.prepare("UPDATE business_scheduled_task SET status = 'paused' WHERE task_id = ? AND tenant_id = ?").run(params.id, user.tenant_id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'automation', action: '暂停任务', resourceType: 'scheduled_task', resourceId: params.id })
    return { ok: true }
  })
  H('POST', '/api/tasks/:id/resume', (req, res, { user, params }) => {
    requirePermission(user, 'task:manage')
    db.prepare("UPDATE business_scheduled_task SET status = 'active' WHERE task_id = ? AND tenant_id = ?").run(params.id, user.tenant_id)
    return { ok: true }
  })
  H('DELETE', '/api/tasks/:id', (req, res, { user, params }) => {
    requirePermission(user, 'task:manage')
    db.prepare('DELETE FROM business_scheduled_task WHERE task_id = ? AND tenant_id = ?').run(params.id, user.tenant_id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'automation', action: '删除任务', resourceType: 'scheduled_task', resourceId: params.id })
    return { ok: true }
  })
  H('GET', '/api/jobs', (req, res, { user }) => {
    const url = new URL(req.url, 'http://x')
    const status = url.searchParams.get('status')
    const where = status ? 'WHERE j.status = ? AND j.tenant_id = ?' : 'WHERE j.tenant_id = ?'
    const params = status ? [status, user.tenant_id] : [user.tenant_id]
    return db.prepare(`SELECT j.*, t.name AS task_name, t.agent_id FROM runtime_scheduled_job j JOIN business_scheduled_task t ON t.task_id = j.task_id ${where} ORDER BY j.job_id DESC LIMIT 200`).all(...params)
  })
  H('POST', '/api/jobs/:id/rerun', async (req, res, { user, params }) => {
    requirePermission(user, 'task:manage')
    const job = db.prepare('SELECT * FROM runtime_scheduled_job WHERE job_id = ?').get(params.id)
    if (!job || job.tenant_id !== user.tenant_id) throw Object.assign(new Error('Job 不存在'), { status: 404 })
    return runTaskNow(job.task_id, 'rerun', null, user)
  })
  H('POST', '/api/scheduler/tick', async (req, res, { user }) => {
    requirePermission(user, 'task:manage')
    const fired = await tick(true)
    return { fired: fired.length }
  })

  // ---- 一次性 AI 任务（新建任务：runAgent 真实执行，异步回写状态）----
  async function executeWorkTask (taskId, user) {
    const t = db.prepare('SELECT * FROM business_work_task WHERE id = ?').get(taskId)
    if (!t || t.status === 'running') return
    db.prepare("UPDATE business_work_task SET status='running', error=NULL, output=NULL WHERE id = ?").run(taskId)
    try {
      const res = await runAgent({ agentId: t.agent_id, user, instruction: t.instruction, triggerType: 'task' })
      db.prepare('UPDATE business_work_task SET status=?, execution_id=?, trace_id=?, output=?, latency_ms=?, finished_at=? WHERE id=?')
        .run(res.status, res.executionId, res.traceId, String(res.output ?? '').slice(0, 4000), res.latencyMs, now(), taskId)
    } catch (e) {
      // runAgent 对不存在/未发布/跨租户 Agent 在落库前抛错，业务表兜底置 failed
      db.prepare("UPDATE business_work_task SET status='failed', error=?, finished_at=? WHERE id=?")
        .run(String(e.message).slice(0, 500), now(), taskId)
    }
  }
  H('GET', '/api/worktasks', (req, res, { user }) => {
    requirePermission(user, 'worktask:run')
    const url = new URL(req.url, 'http://x')
    const projectId = Number(url.searchParams.get('project_id')) || null
    const status = url.searchParams.get('status')
    let where = 'WHERE w.tenant_id = ?'; const params = [user.tenant_id]
    if (projectId) { where += ' AND w.project_id = ?'; params.push(projectId) }
    if (status) { where += ' AND w.status = ?'; params.push(status) }
    return db.prepare(`SELECT w.*, a.agent_name, p.name AS project_name FROM business_work_task w
      LEFT JOIN business_agent a ON a.agent_id = w.agent_id
      LEFT JOIN business_project p ON p.id = w.project_id
      ${where} ORDER BY w.id DESC LIMIT 200`).all(...params)
  })
  H('POST', '/api/worktasks', async (req, res, { user }) => {
    requirePermission(user, 'worktask:run')
    const b = await readBody(req)
    if (!b.title || !b.instruction || !b.agent_id) throw Object.assign(new Error('标题、指令与 Agent 必填'), { status: 400 })
    const agent = db.prepare("SELECT * FROM business_agent WHERE agent_id = ? AND status = 'published'").get(b.agent_id)
    if (!agent || agent.tenant_id !== user.tenant_id) throw Object.assign(new Error('Agent 不存在或未发布'), { status: 404 })
    if (b.project_id) {
      const p = db.prepare('SELECT id FROM business_project WHERE id = ? AND tenant_id = ?').get(b.project_id, user.tenant_id)
      if (!p) throw Object.assign(new Error('项目不存在'), { status: 404 })
    }
    const id = db.prepare(`INSERT INTO business_work_task (tenant_id, title, instruction, agent_id, project_id, status, created_by, created_at, data_origin)
      VALUES (?,?,?,?,?,'pending',?,?, 'manual')`).run(user.tenant_id, b.title, b.instruction, b.agent_id, b.project_id || null, user.id, now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'task', action: '创建任务并执行', resourceType: 'work_task', resourceId: id, after: { title: b.title, agent: agent.agent_name } })
    executeWorkTask(Number(id), user).catch(() => {}) // fire-and-forget，状态由前端轮询
    return { id: Number(id) }
  })
  H('POST', '/api/worktasks/:id/run', (req, res, { user, params }) => {
    requirePermission(user, 'worktask:run')
    const t = db.prepare('SELECT * FROM business_work_task WHERE id = ?').get(params.id)
    if (!t || t.tenant_id !== user.tenant_id) throw Object.assign(new Error('任务不存在'), { status: 404 })
    if (t.status === 'running') throw Object.assign(new Error('任务执行中，请等待完成'), { status: 409 })
    executeWorkTask(t.id, user).catch(() => {})
    return { ok: true }
  })
  H('DELETE', '/api/worktasks/:id', (req, res, { user, params }) => {
    requirePermission(user, 'worktask:run')
    const t = db.prepare('SELECT * FROM business_work_task WHERE id = ?').get(params.id)
    if (!t || t.tenant_id !== user.tenant_id) throw Object.assign(new Error('任务不存在'), { status: 404 })
    if (t.status === 'running') throw Object.assign(new Error('任务执行中，禁止删除'), { status: 409 })
    db.prepare('DELETE FROM business_work_task WHERE id = ?').run(t.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'task', action: '删除任务', resourceType: 'work_task', resourceId: t.id, before: { title: t.title } })
    return { ok: true }
  })

  // ---- 项目 ----
  H('GET', '/api/projects', (req, res, { user }) => {
    requirePermission(user, 'worktask:run')
    return db.prepare(`SELECT p.*, (SELECT COUNT(*) FROM business_work_task w WHERE w.project_id = p.id) AS task_count
      FROM business_project p WHERE p.tenant_id = ? ORDER BY p.id DESC`).all(user.tenant_id)
  })
  H('POST', '/api/projects', async (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    const b = await readBody(req)
    if (!b.name) throw Object.assign(new Error('项目名称必填'), { status: 400 })
    const id = db.prepare(`INSERT INTO business_project (tenant_id, name, description, status, owner_id, created_by, created_at, data_origin)
      VALUES (?,?,?,?,?,?,?, 'manual')`).run(user.tenant_id, b.name, b.description || null, b.status || 'active', b.owner_id || null, user.id, now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '创建项目', resourceType: 'project', resourceId: id, after: { name: b.name } })
    return { id: Number(id) }
  })
  H('DELETE', '/api/projects/:id', (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const p = db.prepare('SELECT * FROM business_project WHERE id = ?').get(params.id)
    if (!p || p.tenant_id !== user.tenant_id) throw Object.assign(new Error('项目不存在'), { status: 404 })
    db.prepare('UPDATE business_work_task SET project_id = NULL WHERE project_id = ?').run(p.id) // 关联任务解除而非级联删除
    db.prepare('DELETE FROM business_project WHERE id = ?').run(p.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '删除项目', resourceType: 'project', resourceId: p.id, before: { name: p.name } })
    return { ok: true }
  })

  // ---- 知识库（库 + 条目；knowledge_search 工具的数据源）----
  H('GET', '/api/knowledge', (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    return db.prepare(`SELECT k.*, (SELECT COUNT(*) FROM business_knowledge_item i WHERE i.knowledge_id = k.id) AS item_count
      FROM business_knowledge k WHERE k.tenant_id = ? ORDER BY k.id DESC`).all(user.tenant_id)
  })
  H('POST', '/api/knowledge', async (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    const b = await readBody(req)
    if (!b.name) throw Object.assign(new Error('知识库名称必填'), { status: 400 })
    const id = db.prepare('INSERT INTO business_knowledge (tenant_id, name, description, status, created_by, created_at, data_origin) VALUES (?,?,?,\'active\',?,?, \'manual\')')
      .run(user.tenant_id, b.name, b.description || null, user.id, now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '创建知识库', resourceType: 'knowledge', resourceId: id, after: { name: b.name } })
    return { id: Number(id) }
  })
  H('DELETE', '/api/knowledge/:id', (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const k = db.prepare('SELECT * FROM business_knowledge WHERE id = ?').get(params.id)
    if (!k || k.tenant_id !== user.tenant_id) throw Object.assign(new Error('知识库不存在'), { status: 404 })
    db.prepare('DELETE FROM business_knowledge_item WHERE knowledge_id = ?').run(k.id)
    db.prepare('DELETE FROM business_knowledge WHERE id = ?').run(k.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '删除知识库', resourceType: 'knowledge', resourceId: k.id, before: { name: k.name } })
    return { ok: true }
  })
  H('GET', '/api/knowledge/:id/items', (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const k = db.prepare('SELECT * FROM business_knowledge WHERE id = ?').get(params.id)
    if (!k || k.tenant_id !== user.tenant_id) throw Object.assign(new Error('知识库不存在'), { status: 404 })
    return db.prepare('SELECT * FROM business_knowledge_item WHERE knowledge_id = ? ORDER BY id DESC').all(k.id)
  })
  H('POST', '/api/knowledge/:id/items', async (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const k = db.prepare('SELECT * FROM business_knowledge WHERE id = ?').get(params.id)
    if (!k || k.tenant_id !== user.tenant_id) throw Object.assign(new Error('知识库不存在'), { status: 404 })
    const b = await readBody(req)
    if (!b.title || !b.content) throw Object.assign(new Error('标题与正文必填'), { status: 400 })
    const id = db.prepare('INSERT INTO business_knowledge_item (knowledge_id, tenant_id, title, content, tags, created_by, created_at, data_origin) VALUES (?,?,?,?,?,?,?, \'manual\')')
      .run(k.id, user.tenant_id, b.title, b.content, b.tags || null, user.id, now()).lastInsertRowid
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '添加知识条目', resourceType: 'knowledge_item', resourceId: id, after: { title: b.title } })
    return { id: Number(id) }
  })
  H('DELETE', '/api/knowledge/item/:itemId', (req, res, { user, params }) => {
    requirePermission(user, 'agent:manage')
    const i = db.prepare('SELECT * FROM business_knowledge_item WHERE id = ?').get(params.itemId)
    if (!i || i.tenant_id !== user.tenant_id) throw Object.assign(new Error('条目不存在'), { status: 404 })
    db.prepare('DELETE FROM business_knowledge_item WHERE id = ?').run(i.id)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '删除知识条目', resourceType: 'knowledge_item', resourceId: i.id, before: { title: i.title } })
    return { ok: true }
  })
  // 知识收割：Qwen27B 阅读工作区联网资料（web-research.md）加工成知识条目并导出 KNOWLEDGE.md
  H('POST', '/api/knowledge/harvest', async (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '启动知识收割（联网资料加工）', resourceType: 'knowledge' })
    runKnowledgeHarvest(user).catch(() => {})
    return { queued: true }
  })
  H('GET', '/api/knowledge/harvest-status', (req, res, { user }) => {
    requirePermission(user, 'agent:manage')
    return harvestStatus()
  })

  // ---- 数据模拟中心 ----
  H('POST', '/api/simulator/generate', async (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    requireFeature(user.tenant_id, 'simulator_center')
    const b = await readBody(req)
    const summary = simulate({ start: b.start, end: b.end, dailyBase: b.dailyBase, failRate: b.failRate, toolCallRate: b.toolCallRate, scheduledRatio: b.scheduledRatio, seed: b.seed, tenants: b.tenant_id ? [b.tenant_id] : null })
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '生成模拟数据', resourceType: 'simulator', after: { range: `${b.start}~${b.end}`, ...summary } })
    return summary
  })
  H('POST', '/api/simulator/clear', async (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    const b = await readBody(req)
    const removed = clearSimulated({ start: b.start, end: b.end, tenantId: b.tenant_id || null })
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '清空模拟数据', after: { removed } })
    return { removed }
  })

  // ---- 企业业务数据自动生成（客户/订单/库存/财务/售后成体系生成）----
  H('POST', '/api/business/generate', async (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    requireFeature(user.tenant_id, 'simulator_center')
    const b = await readBody(req)
    const summary = generateBusinessData({ months: b.months, tenantId: b.tenant_id || null, seed: b.seed, clear: b.clear !== false })
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '生成企业业务数据', resourceType: 'business-data', after: summary })
    return summary
  })
  H('POST', '/api/business/clear', (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    const removed = clearGeneratedBusinessData()
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '清空生成业务数据', after: { removed } })
    return { removed }
  })
  H('GET', '/api/business/stats', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    return generatedBusinessStats()
  })

  // ---- 数据库可视化（表浏览器：只读，system:manage）----
  // 白名单按前缀+风险双过滤：排除凭证列（password_hash）与跨租户敏感表
  const DB_TABLES = [
    // [表名, 中文名, 是否含租户列]
    ['business_tenant', '企业', true], ['business_user', '用户', true], ['business_department', '部门', true],
    ['business_feature', '功能定义', false], ['business_tenant_feature', '企业功能授权', true],
    ['business_agent', 'Agent', true], ['business_skill', 'Skill', false], ['business_tool', 'Tool', true],
    ['business_customer', '客户', true], ['business_order', '订单', true], ['business_inventory', '库存', true],
    ['business_finance', '财务', true], ['business_after_sale', '售后工单', true],
    ['business_project', '项目', true], ['business_work_task', '一次性任务', true],
    ['business_knowledge', '知识库', true], ['business_knowledge_item', '知识条目', true],
    ['business_invoice', '发票（导入）', true], ['business_invoice_item', '发票物料明细', true],
    ['business_scheduled_task', '定时任务', true], ['business_setting', '系统设置(KV)', false],
    ['runtime_agent_execution', 'AI 执行日志', true], ['runtime_tool_execution', 'Tool 调用日志', true],
    ['runtime_conversation', '会话', true], ['runtime_message', '会话消息', true],
    ['runtime_model_usage', '模型用量', true], ['runtime_scheduled_job', '任务执行记录', true],
    ['log_login_log', '登录日志', true], ['log_feature_usage', '功能使用日志', true],
    ['log_operation_log', '操作日志', true], ['log_amendment', '日志修正', false],
    ['audit_audit_log', '审计日志', true], ['audit_change', '数据修改留痕', true],
  ]
  const HIDDEN_COLUMNS = new Set(['password_hash'])
  H('GET', '/api/db/tables', (req, res, { user }) => {
    requirePermission(user, 'system:manage')
    return DB_TABLES.map(([name, label]) => {
      const cols = db.prepare(`PRAGMA table_info(${name})`).all().map(c => c.name).filter(c => !HIDDEN_COLUMNS.has(c))
      const count = db.prepare(`SELECT COUNT(*) c FROM ${name}`).get().c
      return { name, label, columns: cols, count }
    })
  })
  H('GET', '/api/db/table/:name', (req, res, { user, params }) => {
    requirePermission(user, 'system:manage')
    const table = DB_TABLES.find(([n]) => n === params.name)
    if (!table) throw Object.assign(new Error('表不在可浏览白名单内'), { status: 403 })
    const url = new URL(req.url, 'http://x')
    const page = Math.max(1, Number(url.searchParams.get('page')) || 1)
    const size = Math.min(Number(url.searchParams.get('size')) || 50, 200)
    const q = String(url.searchParams.get('q') || '').trim()
    // 全列模糊搜索（值统一转字符串比较，避免类型问题；防注入：仅白名单表）
    const cols = db.prepare(`PRAGMA table_info(${table[0]})`).all().map(c => c.name).filter(c => !HIDDEN_COLUMNS.has(c))
    let where = ''; const args = []
    if (q) {
      where = 'WHERE ' + cols.map(c => `CAST(${c} AS TEXT) LIKE ?`).join(' OR ')
      args.push(`%${q}%`); for (let i = 1; i < cols.length; i++) args.push(`%${q}%`)
    }
    const total = db.prepare(`SELECT COUNT(*) c FROM ${table[0]} ${where}`).get(...args).c
    const rows = db.prepare(`SELECT ${cols.join(',')} FROM ${table[0]} ${where} ORDER BY rowid DESC LIMIT ? OFFSET ?`)
      .all(...args, size, (page - 1) * size)
    return { name: table[0], label: table[1], columns: cols, rows, total, page, size }
  })

  // ---- AI 自动运行（dsh Harness 直驱真实模型，全程日志落库）----
  // 监控查询为平台级视角：模拟器跨租户跑多企业角色，stats:view 用户可看全部
  // auto:* 记录（租户名列区分归属）；真实业务日志仍走 /api/logs/* 的租户隔离
  H('GET', '/api/autorun/status', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    return autoRunStatus()
  })
  H('GET', '/api/autorun/analytics', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    return autoRunAnalytics()
  })
  // 产品功能清单（28 项/6 模块）：AI 对话首页功能入口 UI 数据源（登录即可读）
  H('GET', '/api/autorun/catalog', (req, res) => {
    return { modules: catalogByModule(), total: FUNCTION_CATALOG.length }
  })
  // 功能模块演示：点击入口 → 向租户工作区会话发送该功能的演示问题并落库
  H('POST', '/api/autorun/feature-ask', async (req, res, { user }) => {
    const b = await readBody(req)
    const r = await runFeatureDemo(Number(b.feature), user)
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'ai', action: '功能模块演示', resourceType: 'feature', after: { feature: r.feature, module: r.module } })
    return r
  })
  H('POST', '/api/autorun/start', async (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    requireFeature(user.tenant_id, 'simulator_center')
    const b = await readBody(req)
    const r = startAutoRun({ rounds: b.rounds, concurrency: b.concurrency, scope: b.scope })
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '启动 AI 自动运行', resourceType: 'autorun', after: { rounds: b.rounds, concurrency: b.concurrency, scope: r.scope, roles: r.roles } })
    return r
  })
  H('POST', '/api/autorun/stop', (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    const r = stopAutoRun()
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '停止 AI 自动运行', resourceType: 'autorun' })
    return r
  })
  H('GET', '/api/autorun/report', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    return jhlReport()
  })
  H('POST', '/api/autorun/report/rerun', async (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '重新生成金汉隆数据报告', resourceType: 'autorun' })
    // 异步执行，立即返回（进度由 /api/autorun/report 的 running 字段反映）
    runJhlReport().catch(() => {})
    return { queued: true }
  })
  H('POST', '/api/autorun/multiagent', async (req, res, { user }) => {
    requirePermission(user, 'simulator:run')
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'simulator', action: '启动多 Agent 协同测试', resourceType: 'autorun' })
    runMultiAgentTest().catch(() => {})
    return { queued: true }
  })
  H('GET', '/api/autorun/executions', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    const url = new URL(req.url, 'http://localhost')
    return recentAutoExecutions(null, url.searchParams.get('limit'))
  })
  H('GET', '/api/autorun/messages', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    const url = new URL(req.url, 'http://localhost')
    return recentAutoMessages(null, url.searchParams.get('limit'))
  })

  // ---- 统计 Dashboard（仅数据库聚合，禁止单独写死统计值 PRD §68）----
  H('GET', '/api/stats/dashboard', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    const one = (sql, p = []) => db.prepare(sql).get(...p)
    const t = user.tenant_id
    return {
      tenants: one('SELECT COUNT(*) c FROM business_tenant').c,
      active_users: one("SELECT COUNT(DISTINCT user_id) c FROM log_login_log WHERE tenant_id=? AND created_at >= datetime('now','-30 days')", [t]).c,
      agent_executions: one('SELECT COUNT(*) c FROM runtime_agent_execution WHERE tenant_id=?', [t]).c,
      scheduled_jobs: one('SELECT COUNT(*) c FROM runtime_scheduled_job WHERE tenant_id=?', [t]).c,
      tool_calls: one('SELECT COUNT(*) c FROM runtime_tool_execution WHERE tenant_id=?', [t]).c,
      success_rate: one("SELECT ROUND(100.0*SUM(status='success')/COUNT(*),2) c FROM runtime_agent_execution WHERE tenant_id=?", [t]).c,
      avg_latency_ms: one('SELECT ROUND(AVG(latency_ms)) c FROM runtime_agent_execution WHERE tenant_id=?', [t]).c,
      total_tokens: one('SELECT COALESCE(SUM(token_input+token_output),0) c FROM runtime_agent_execution WHERE tenant_id=?', [t]).c,
      failed_jobs: one("SELECT COUNT(*) c FROM runtime_scheduled_job WHERE tenant_id=? AND status='failed'", [t]).c,
      simulated_ratio: one("SELECT ROUND(100.0*SUM(data_origin='simulated')/COUNT(*),1) c FROM runtime_agent_execution WHERE tenant_id=?", [t]).c
    }
  })
  H('GET', '/api/stats/trends', (req, res, { user }) => {
    requirePermission(user, 'stats:view')
    const url = new URL(req.url, 'http://x')
    const granularity = url.searchParams.get('granularity') || 'month'
    const from = url.searchParams.get('from') || '2025-12-01'
    const to = url.searchParams.get('to') || '2026-08-31'
    // 上界加 '~' 使 BETWEEN 覆盖 to 当日全部时间
    if (granularity === 'month') {
      return db.prepare(`SELECT substr(started_at,1,7) AS bucket, COUNT(*) AS executions,
        SUM(status='success') AS success, COALESCE(SUM(token_input+token_output),0) AS tokens,
        ROUND(AVG(latency_ms)) AS avg_latency
        FROM runtime_agent_execution WHERE tenant_id=? AND started_at BETWEEN ? AND ? GROUP BY bucket ORDER BY bucket`)
        .all(user.tenant_id, from, to + '~')
    }
    const col = granularity === 'week' ? "strftime('%Y-W%W', started_at)" : 'substr(started_at,1,10)'
    return db.prepare(`SELECT ${col} AS bucket, COUNT(*) AS executions, SUM(status='success') AS success, COALESCE(SUM(token_input+token_output),0) AS tokens
      FROM runtime_agent_execution WHERE tenant_id=? AND started_at BETWEEN ? AND ? GROUP BY bucket ORDER BY bucket`)
      .all(user.tenant_id, from, to + '~')
  })
  H('GET', '/api/stats/agents', (req, res, { user }) => db.prepare(`
    SELECT a.agent_name, COUNT(e.execution_id) AS runs, ROUND(AVG(e.latency_ms)) AS avg_latency,
      ROUND(100.0*SUM(e.status='success')/COUNT(*),1) AS success_rate, COALESCE(SUM(e.token_input+e.token_output),0) AS tokens
    FROM business_agent a LEFT JOIN runtime_agent_execution e ON e.agent_id = a.agent_id
    WHERE a.tenant_id = ? GROUP BY a.agent_id ORDER BY runs DESC`).all(user.tenant_id))
  H('GET', '/api/stats/harness', (req, res, { user }) => {
    const t = user.tenant_id
    const one = (sql, p = []) => db.prepare(sql).get(...p)
    return {
      agent_success_rate: one("SELECT ROUND(100.0*SUM(status='success')/COUNT(*),2) c FROM runtime_agent_execution WHERE tenant_id=?", [t]).c,
      agent_avg_ms: one('SELECT ROUND(AVG(latency_ms)) c FROM runtime_agent_execution WHERE tenant_id=?', [t]).c,
      agent_failures: one("SELECT COUNT(*) c FROM runtime_agent_execution WHERE tenant_id=? AND status='failed'", [t]).c,
      tool_failures: one("SELECT COUNT(*) c FROM runtime_tool_execution WHERE tenant_id=? AND status='failed'", [t]).c,
      tool_pending_confirm: one("SELECT COUNT(*) c FROM runtime_tool_execution WHERE tenant_id=? AND status='pending_confirm'", [t]).c,
      timeouts: one("SELECT COUNT(*) c FROM runtime_agent_execution WHERE tenant_id=? AND error LIKE '%超时%'", [t]).c,
      token_usage: one('SELECT COALESCE(SUM(token_input+token_output),0) c FROM runtime_agent_execution WHERE tenant_id=?', [t]).c
    }
  })

  // ---- 日志中心 ----
  const logList = (table, timeCol) => (req, res, { user }) => {
    requirePermission(user, 'log:view')
    const url = new URL(req.url, 'http://x')
    const filters = ['tenant_id = @tenant']
    const params = { tenant: user.tenant_id }
    for (const [q, col] of [['status', 'status'], ['agent_id', 'agent_id'], ['user_id', 'user_id'], ['tool_name', 'tool_name'], ['trace_id', 'trace_id'], ['origin', 'data_origin'], ['module', 'module'], ['action', 'action'], ['q', null]]) {
      const v = url.searchParams.get(q)
      if (!v) continue
      if (q === 'q') { filters.push('(CAST(input AS TEXT) LIKE @kw OR CAST(output AS TEXT) LIKE @kw OR CAST(failure_reason AS TEXT) LIKE @kw)'); params.kw = `%${v}%` }
      else { filters.push(`${col} = @${q}`); params[q] = v }
    }
    const from = url.searchParams.get('from'); const to = url.searchParams.get('to')
    if (from) { filters.push(`${timeCol} >= @from`); params.from = from }
    if (to) { filters.push(`${timeCol} <= @to`); params.to = to }
    return db.prepare(`SELECT * FROM ${table} WHERE ${filters.join(' AND ')} ORDER BY rowid DESC LIMIT 200`).all(params)
  }
  H('GET', '/api/logs/ai', logList('runtime_agent_execution', 'started_at'))
  H('GET', '/api/logs/tool', logList('runtime_tool_execution', 'created_at'))
  H('GET', '/api/logs/jobs', logList('runtime_scheduled_job', 'scheduled_at'))
  H('GET', '/api/logs/operation', logList('log_operation_log', 'created_at'))
  H('GET', '/api/logs/login', logList('log_login_log', 'created_at'))
  H('GET', '/api/logs/audit', logList('audit_audit_log', 'created_at'))
  H('GET', '/api/logs/amendments', () => db.prepare('SELECT * FROM log_amendment ORDER BY id DESC LIMIT 200').all())
  // Trace Replay
  H('GET', '/api/trace/:traceId', (req, res, { user, params }) => {
    const r = replayTrace(user.tenant_id, params.traceId)
    if (!r) throw Object.assign(new Error('trace 不存在'), { status: 404 })
    return r
  })

  // ---- 数据管理中心（修改留痕 audit_change）----
  H('GET', '/api/data/tables', () => EDITABLE_TABLES)
  H('GET', '/api/data/:table', (req, res, { user, params }) => {
    requirePermission(user, 'data:manage')
    if (!EDITABLE_TABLES.includes(params.table)) throw new PermissionError(`表不在可管理白名单：${params.table}`)
    const scope = params.table === 'business_department' ? '' : 'AND tenant_id = ?'
    const p = params.table === 'business_department' ? [] : [user.tenant_id]
    return db.prepare(`SELECT * FROM ${params.table} WHERE 1=1 ${scope} LIMIT 200`).all(...p)
  })
  H('PUT', '/api/data/:table/:id', async (req, res, { user, params }) => {
    requirePermission(user, 'data:manage')
    if (!EDITABLE_TABLES.includes(params.table)) throw new PermissionError('表不可编辑')
    const b = await readBody(req)
    const before = db.prepare(`SELECT * FROM ${params.table} WHERE id = ?`).get(params.id)
    if (!before) throw Object.assign(new Error('记录不存在'), { status: 404 })
    if (before.tenant_id !== user.tenant_id && user.role !== 'platform_admin') throw new PermissionError('跨租户数据修改被拒绝')
    const cols = Object.keys(b).filter(k => k !== 'id' && k !== 'tenant_id' && !k.startsWith('__'))
    if (cols.length) db.prepare(`UPDATE ${params.table} SET ${cols.map(c => `${c} = ?`).join(', ')} WHERE id = ?`).run(...cols.map(c => b[c]), params.id)
    const after = db.prepare(`SELECT * FROM ${params.table} WHERE id = ?`).get(params.id)
    db.prepare('INSERT INTO audit_change (tenant_id, table_name, record_id, before_json, after_json, operator, reason, created_at) VALUES (?,?,?,?,?,?,?,?)')
      .run(before.tenant_id ?? user.tenant_id, params.table, params.id, JSON.stringify(before), JSON.stringify(after), user.username, b.__reason || '后台数据调整', now())
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'data', action: '修改数据库记录', resourceType: params.table, resourceId: params.id, before, after })
    return { ok: true, after }
  })
  H('DELETE', '/api/data/:table/:id', async (req, res, { user, params }) => {
    requirePermission(user, 'data:manage')
    if (!EDITABLE_TABLES.includes(params.table)) throw new PermissionError('表不可编辑')
    const before = db.prepare(`SELECT * FROM ${params.table} WHERE id = ?`).get(params.id)
    if (!before) throw Object.assign(new Error('记录不存在'), { status: 404 })
    if (before.tenant_id !== user.tenant_id && user.role !== 'platform_admin') throw new PermissionError('跨租户数据删除被拒绝')
    db.prepare(`DELETE FROM ${params.table} WHERE id = ?`).run(params.id)
    db.prepare('INSERT INTO audit_change (tenant_id, table_name, record_id, before_json, after_json, operator, reason, created_at) VALUES (?,?,?,?,?,?,?,?)')
      .run(before.tenant_id ?? user.tenant_id, params.table, params.id, JSON.stringify(before), null, user.username, '后台删除', now())
    return { ok: true }
  })
  // 日志修正：允许修正日志展示数据，但原始值留痕（PRD §49/§50）
  H('POST', '/api/logs/amend', async (req, res, { user }) => {
    requirePermission(user, 'audit:amend')
    const b = await readBody(req)
    const target = db.prepare(`SELECT * FROM ${b.table} WHERE rowid = ?`).get(b.record_id)
    if (!target) throw Object.assign(new Error('目标日志不存在'), { status: 404 })
    db.prepare(`UPDATE ${b.table} SET ${b.field} = ? WHERE rowid = ?`).run(b.value, b.record_id)
    db.prepare('INSERT INTO log_amendment (target_table, record_id, before_json, after_json, operator, reason, created_at) VALUES (?,?,?,?,?,?,?)')
      .run(b.table, String(b.record_id), JSON.stringify({ [b.field]: target[b.field] }), JSON.stringify({ [b.field]: b.value }), user.username, b.reason || '', now())
    logOperation({ tenantId: user.tenant_id, userId: user.id, module: 'log', action: '修正日志', resourceType: b.table, resourceId: b.record_id, before: { [b.field]: target[b.field] }, after: { [b.field]: b.value } })
    return { ok: true }
  })
  H('GET', '/api/audit/changes', (req, res, { user }) => {
    requirePermission(user, 'log:view')
    return db.prepare('SELECT * FROM audit_change WHERE tenant_id = ? ORDER BY id DESC LIMIT 200').all(user.tenant_id)
  })

  return R
}
