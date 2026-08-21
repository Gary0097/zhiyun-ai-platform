// Tool 工具中心：Agent 不直接操作数据库；调用链 Agent → Harness → Tool Registry → Permission Guard → Tool → DB
import { db, now } from './db.js'
import { enforceToolRisk } from './os/risk-control.js'
import { dataScope, logOperation } from './auth.js'

class ToolDenied extends Error { constructor (msg) { super(msg); this.status = 403; this.denied = true } }

// 每个 Tool 声明 schema（模型可见）、执行器（自动注入 tenant_id + 数据域）、是否敏感
const TOOL_IMPLS = {
  query_order: {
    schema: { type: 'object', properties: { order_no: { type: 'string', description: '订单号，可省略' }, status: { type: 'string' } } },
    mockArgs: {},
    run (ctx, args) {
      const scope = ctx.scopeFor('business_order')
      const rows = db.prepare(`SELECT order_no, product, quantity, amount, due_date, status, current_node, progress, delay_hours, risk_level FROM business_order WHERE tenant_id = ? ${scope.clause} ${args.order_no ? 'AND order_no = ?' : ''} LIMIT 50`)
        .all(ctx.tenantId, ...scope.params, ...(args.order_no ? [args.order_no] : []))
      return { count: rows.length, orders: rows }
    }
  },
  query_inventory: {
    schema: { type: 'object', properties: { material: { type: 'string' } } },
    mockArgs: {},
    run (ctx, args) {
      const rows = db.prepare(`SELECT material, stock, safety_stock, consumption_rate, supplier FROM business_inventory WHERE tenant_id = ? ${args.material ? 'AND material LIKE ?' : ''} LIMIT 50`)
        .all(ctx.tenantId, ...(args.material ? [`%${args.material}%`] : []))
      return { count: rows.length, items: rows, low_stock: rows.filter(r => r.stock < r.safety_stock) }
    }
  },
  query_customer: {
    schema: { type: 'object', properties: { name: { type: 'string' } } },
    mockArgs: {},
    run (ctx, args) {
      const rows = db.prepare('SELECT name, tag, region FROM business_customer WHERE tenant_id = ? LIMIT 50').all(ctx.tenantId)
      return { count: rows.length, customers: args.name ? rows.filter(r => r.name.includes(args.name)) : rows }
    }
  },
  query_finance: {
    schema: { type: 'object', properties: { month: { type: 'string', description: 'YYYY-MM' } } },
    mockArgs: {},
    run (ctx, args) {
      const rows = db.prepare('SELECT category, amount, month FROM business_finance WHERE tenant_id = ? LIMIT 100').all(ctx.tenantId)
      return { items: args.month ? rows.filter(r => r.month === args.month) : rows }
    }
  },
  query_after_sale: {
    schema: { type: 'object', properties: { status: { type: 'string' } } },
    mockArgs: {},
    run (ctx, args) {
      const rows = db.prepare('SELECT id, device, fault, status, created_at FROM business_after_sale WHERE tenant_id = ? LIMIT 50').all(ctx.tenantId)
      return { count: rows.length, tickets: args.status ? rows.filter(r => r.status === args.status) : rows }
    }
  },
  query_invoice: {
    schema: { type: 'object', properties: { supplier: { type: 'string', description: '供应商名称（可模糊）' }, month: { type: 'string', description: 'YYYY-MM' }, category: { type: 'string', description: '品类：机械零件/气动元件/减速电机/塑料制品/金属制品' } } },
    mockArgs: {},
    run (ctx, args) {
      const rows = db.prepare('SELECT invoice_no, invoice_date, supplier, category, amount_excl_tax, tax, amount_total FROM business_invoice WHERE tenant_id = ? LIMIT 100').all(ctx.tenantId)
      let out = rows
      if (args.supplier) out = out.filter(r => r.supplier.includes(args.supplier))
      if (args.month) out = out.filter(r => r.invoice_date.startsWith(args.month))
      if (args.category) out = out.filter(r => r.category === args.category)
      const bySupplier = {}
      for (const r of rows) bySupplier[r.supplier] = (bySupplier[r.supplier] || 0) + r.amount_total
      return {
        count: out.length, invoices: out,
        supplier_summary: Object.entries(bySupplier).map(([s, v]) => ({ supplier: s, total: Math.round(v) })).sort((a, b) => b.total - a.total)
      }
    }
  },
  query_invoice_items: {
    schema: { type: 'object', properties: { invoice_no: { type: 'string' }, item_name: { type: 'string', description: '物料名称（可模糊）' } } },
    mockArgs: {},
    run (ctx, args) {
      let sql = 'SELECT i.invoice_no, i.supplier, t.item_name, t.spec, t.qty, t.unit_price, t.amount FROM business_invoice_item t JOIN business_invoice i ON i.invoice_id = t.invoice_id WHERE t.tenant_id = ?'
      const params = [ctx.tenantId]
      if (args.invoice_no) { sql += ' AND i.invoice_no = ?'; params.push(args.invoice_no) }
      sql += ' ORDER BY t.amount DESC LIMIT 80'
      let rows = db.prepare(sql).all(...params)
      if (args.item_name) rows = rows.filter(r => r.item_name.includes(args.item_name))
      return { count: rows.length, items: rows }
    }
  },
  // ---- 敏感 Tool：写操作，必须人工确认后才实际执行（PRD §59 AI建议→人工确认→执行）----
  update_order: {
    sensitive: true,
    schema: { type: 'object', properties: { order_no: { type: 'string' }, progress: { type: 'number' }, risk_level: { type: 'string' } }, required: ['order_no'] },
    mockArgs: { order_no: 'SO-2026-1001', progress: 50 },
    run (ctx, args) {
      const info = db.prepare('UPDATE business_order SET progress = COALESCE(?, progress), risk_level = COALESCE(?, risk_level), updated_at = ? WHERE tenant_id = ? AND order_no = ?')
        .run(args.progress ?? null, args.risk_level ?? null, now(), ctx.tenantId, args.order_no)
      return { updated: info.changes, note: '已执行（人工确认通过）' }
    }
  },
  create_work_order: {
    sensitive: true,
    schema: { type: 'object', properties: { device: { type: 'string' }, fault: { type: 'string' } }, required: ['device', 'fault'] },
    mockArgs: { device: 'CNC-加工中心 VMC850', fault: '主轴异响' },
    run (ctx, args) {
      const id = db.prepare("INSERT INTO business_after_sale (tenant_id, device, fault, status, created_at, data_origin) VALUES (?,?,?,'open',?, 'manual')").run(ctx.tenantId, args.device, args.fault, now()).lastInsertRowid
      return { work_order_id: Number(id) }
    }
  },
  send_notification: {
    schema: { type: 'object', properties: { channel: { type: 'string' }, content: { type: 'string' } }, required: ['content'] },
    mockArgs: { channel: 'wecom', content: '日报已生成' },
    run (ctx, args) {
      // 通知渠道对接点（企业微信/钉钉/飞书/邮件）；此处记录投递事实
      db.prepare("INSERT INTO audit_audit_log (tenant_id, category, trace_id, payload, created_at, data_origin) VALUES (?, 'notification', ?, ?, ?, 'real')")
        .run(ctx.tenantId, ctx.traceId, JSON.stringify({ channel: args.channel || 'wecom', content: String(args.content).slice(0, 200) }), now())
      return { delivered: true, channel: args.channel || 'wecom' }
    }
  },
  knowledge_search: {
    schema: {
      type: 'object',
      properties: { query: { type: 'string', description: '检索关键词（设备/故障/流程/制度等，匹配知识条目标题与正文；多关键词用空格分隔，任一命中即返回）' } },
      required: ['query'],
    },
    mockArgs: { query: '主轴异响 处理' },
    run (ctx, args) {
      // 空格分词：任一关键词命中即计入（LLM 常传「主轴 异响 维修」式多词查询，整串 LIKE 会漏）
      const keywords = [...new Set(String(args.query || '').split(/\s+/).map(w => w.trim()).filter(w => w.length > 1))].slice(0, 6)
      if (keywords.length === 0) return { count: 0, matches: [] }
      const clauses = []; const params = []
      for (const kw of keywords) {
        clauses.push('(i.title LIKE ? OR i.content LIKE ?)')
        params.push(`%${kw.slice(0, 50)}%`, `%${kw.slice(0, 50)}%`)
      }
      const rows = db.prepare(`
        SELECT k.name AS kb_name, i.title, i.content FROM business_knowledge_item i
        JOIN business_knowledge k ON k.id = i.knowledge_id
        WHERE i.tenant_id = ? AND (${clauses.join(' OR ')})
        ORDER BY i.id DESC LIMIT 5`).all(ctx.tenantId, ...params)
      return {
        count: rows.length,
        matches: rows.map(r => ({ kb: r.kb_name, title: r.title, snippet: String(r.content).slice(0, 200) })),
      }
    }
  }
}

/** Permission Guard：Agent 工具白名单 + Tool 启用状态 + 敏感操作确认 */
export function guardToolCall ({ tenantId, agentToolIds, toolName, confirmed = false, userId = null, module = 'ai' }) {
  const toolRow = db.prepare('SELECT * FROM business_tool WHERE tenant_id = ? AND tool_name = ?').get(tenantId, toolName)
  if (!toolRow) throw new ToolDenied(`工具不存在或未对本企业开放：${toolName}`)
  if (!toolRow.enabled) throw new ToolDenied(`工具已停用：${toolName}`)
  if (agentToolIds && !agentToolIds.includes(toolName)) throw new ToolDenied(`Agent 未被授权调用工具：${toolName}`)
  return toolRow
}

/** 执行工具并写入 runtime_tool_execution 与审计 */
export function executeTool ({ tenantId, userId, traceId, executionId, toolName, args, agentToolIds, confirmed = false, scope }) {
  const started = Date.now()
  const impl = TOOL_IMPLS[toolName]
  let status = 'success'; let output; let error = null
  try {
    if (!impl) throw new ToolDenied(`未知工具：${toolName}`)
    const toolRow = guardToolCall({ tenantId, agentToolIds, toolName, confirmed })
    enforceToolRisk({ database: db, now, tenantId, userId, traceId, toolName, sensitive: Boolean(toolRow.sensitive), args: args || {}, confirmed })
    const ctx = {
      tenantId, userId, traceId, scope,
      // 订单表支持 owner 数据域；其余表默认租户全域（演示数据域对订单生效）
      scopeFor: (table) => table === 'business_order' && scope ? scope : { clause: '', params: [] }
    }
    output = impl.run(ctx, args || {})
  } catch (e) {
    status = e.status === 202 ? 'pending_confirm' : 'failed'
    error = e.message
    output = { error: e.message }
  }
  const ms = Date.now() - started
  db.prepare(`INSERT INTO runtime_tool_execution (trace_id, execution_id, tenant_id, tool_name, input, output, status, execution_time_ms, error, created_at, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?, 'real')`)
    .run(traceId, executionId, tenantId, toolName, JSON.stringify(args || {}), JSON.stringify(output), status, ms, error, now())
  if (error) { const e = new Error(error); e.status = status === 'pending_confirm' ? 202 : 500; e.output = output; throw e }
  return output
}

/** 供模型可见的工具清单（含 schema） */
export function toolSchemasFor (tenantId, agentToolIds) {
  return agentToolIds
    .map(name => ({ name, description: '', impl: TOOL_IMPLS[name] }))
    .filter(t => t.impl)
    .map(t => ({ name: t.name, description: toolDesc(tenantId, t.name), schema: t.impl.schema, mockArgs: t.impl.mockArgs }))
}

function toolDesc (tenantId, name) {
  return db.prepare('SELECT description FROM business_tool WHERE tenant_id = ? AND tool_name = ?').get(tenantId, name)?.description || name
}

/** 条件触发评估：condition_tool + condition_expr（字面量或字段比较，如 stock < safety_stock / stock < 100） */
export function evaluateCondition (tenantId, conditionTool, conditionExpr) {
  const impl = TOOL_IMPLS[conditionTool]
  if (!impl) return { met: false, detail: `未知条件工具 ${conditionTool}` }
  const out = impl.run({ tenantId, scopeFor: () => ({ clause: '', params: [] }) }, {})
  const m = conditionExpr?.match(/^(\w+)\s*(<|>|<=|>=)\s*(\w+)$/)
  if (m && out.items?.length) {
    const [, field, op, ref] = m
    const cmp = (v, r) => op === '<' ? v < r : op === '>' ? v > r : op === '<=' ? v <= r : v >= r
    // 右侧为数字字面量，或与左侧同为记录字段（如 stock < safety_stock）
    const refNum = Number(ref)
    const isLiteral = !Number.isNaN(refNum) && /^\d+(\.\d+)?$/.test(ref)
    const met = out.items.some(it => {
      const v = it[field]
      if (typeof v !== 'number') return false
      const r = isLiteral ? refNum : it[ref]
      return typeof r === 'number' ? cmp(v, r) : false
    })
    const hit = met ? out.items.filter(it => typeof it[field] === 'number' && cmp(it[field], isLiteral ? refNum : it[ref])).map(it => it.material || JSON.stringify(it).slice(0, 60)) : []
    return { met, detail: met ? `满足条件 ${conditionExpr}（${hit.slice(0, 3).join('、')}）` : `不满足 ${conditionExpr}`, data: out }
  }
  return { met: JSON.stringify(out).length > 10, detail: '默认评估', data: out }
}
