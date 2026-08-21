// 智造云平台数据库层：SQLite（node:sqlite），四层数据模型 business_ / runtime_ / log_ / audit_
// 所有核心表绑定 tenant_id；所有可生成数据携带 data_origin（real/simulated/imported/manual）
import { DatabaseSync } from 'node:sqlite'
import { ensureOsSchema } from './os/schema.js'
import { scryptSync, randomBytes } from 'node:crypto'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

export const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'data')
mkdirSync(DATA_DIR, { recursive: true })
export const DB_PATH = join(DATA_DIR, 'zhiyun.sqlite')

export const db = new DatabaseSync(DB_PATH)
db.exec('PRAGMA journal_mode = WAL')
db.exec('PRAGMA foreign_keys = ON')

export function hashPassword (password, salt = randomBytes(16).toString('hex')) {
  return salt + ':' + scryptSync(password, salt, 32).toString('hex')
}

export function verifyPassword (password, stored) {
  const [salt] = String(stored).split(':')
  return hashPassword(password, salt) === stored
}

export const now = () => new Date().toISOString()

const SCHEMA = `
CREATE TABLE IF NOT EXISTS business_tenant (
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', data_origin TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS business_department (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  name TEXT NOT NULL, parent_id INTEGER REFERENCES business_department(id)
);
CREATE TABLE IF NOT EXISTS business_user (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, display_name TEXT NOT NULL,
  dept_id INTEGER REFERENCES business_department(id), title TEXT,
  role TEXT NOT NULL, data_scope TEXT NOT NULL DEFAULT 'self', status TEXT NOT NULL DEFAULT 'active',
  data_origin TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS business_permission (code TEXT PRIMARY KEY, name TEXT NOT NULL, module TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS business_role_permission (role TEXT NOT NULL, permission_code TEXT NOT NULL, PRIMARY KEY(role, permission_code));
CREATE TABLE IF NOT EXISTS business_tenant_feature (
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id), feature_code TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(tenant_id, feature_code)
);
CREATE TABLE IF NOT EXISTS business_feature (code TEXT PRIMARY KEY, name TEXT NOT NULL, module TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS business_customer (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL, tag TEXT, region TEXT,
  owner_id INTEGER, data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_order (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, order_no TEXT NOT NULL, customer_id INTEGER,
  product TEXT, quantity REAL, price REAL, amount REAL, due_date TEXT, status TEXT NOT NULL DEFAULT 'planning',
  current_node TEXT NOT NULL DEFAULT '计划', progress INTEGER NOT NULL DEFAULT 0, delay_hours INTEGER NOT NULL DEFAULT 0,
  owner_id INTEGER, risk_level TEXT NOT NULL DEFAULT '绿色', updated_at TEXT, data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_inventory (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, material TEXT NOT NULL, stock REAL NOT NULL,
  safety_stock REAL NOT NULL, consumption_rate REAL NOT NULL, supplier TEXT, data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_finance (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL,
  month TEXT NOT NULL, note TEXT, data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_after_sale (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, customer_id INTEGER, device TEXT, fault TEXT,
  status TEXT NOT NULL DEFAULT 'open', engineer_id INTEGER, created_at TEXT, data_origin TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS business_agent (
  agent_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, agent_name TEXT NOT NULL, agent_type TEXT NOT NULL,
  system_prompt TEXT NOT NULL, model TEXT NOT NULL DEFAULT 'deepseek-chat', temperature REAL NOT NULL DEFAULT 0.3,
  tool_ids TEXT NOT NULL DEFAULT '[]', skill_ids TEXT NOT NULL DEFAULT '[]', knowledge_ids TEXT NOT NULL DEFAULT '[]',
  permission_scope TEXT NOT NULL DEFAULT 'tenant', status TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1, created_by INTEGER, updated_at TEXT, data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_setting (
  key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS business_invoice (
  invoice_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, invoice_no TEXT NOT NULL,
  invoice_date TEXT NOT NULL, supplier TEXT NOT NULL, category TEXT NOT NULL,
  amount_excl_tax REAL NOT NULL, tax REAL NOT NULL, amount_total REAL NOT NULL,
  source_file TEXT, note TEXT, data_origin TEXT NOT NULL DEFAULT 'imported'
);
CREATE TABLE IF NOT EXISTS business_invoice_item (
  item_id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES business_invoice(invoice_id),
  tenant_id INTEGER NOT NULL, item_name TEXT NOT NULL, spec TEXT, qty REAL, unit_price REAL,
  amount REAL, tax REAL, data_origin TEXT NOT NULL DEFAULT 'imported'
);
CREATE INDEX IF NOT EXISTS idx_invoice_tenant ON business_invoice(tenant_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_invitem_invoice ON business_invoice_item(invoice_id);
CREATE TABLE IF NOT EXISTS business_agent_version (
  id INTEGER PRIMARY KEY, agent_id INTEGER NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL,
  published_at TEXT NOT NULL, published_by INTEGER
);
CREATE TABLE IF NOT EXISTS business_skill (
  skill_id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, kind TEXT NOT NULL,
  data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_tool (
  tool_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, tool_name TEXT NOT NULL, tool_type TEXT NOT NULL,
  description TEXT NOT NULL, sensitive INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
  data_origin TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS business_scheduled_task (
  task_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, agent_id INTEGER NOT NULL, name TEXT NOT NULL,
  trigger_type TEXT NOT NULL, cron TEXT, interval_seconds INTEGER, condition_tool TEXT, condition_expr TEXT,
  input TEXT, timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai', status TEXT NOT NULL DEFAULT 'active',
  max_retry INTEGER NOT NULL DEFAULT 2, timeout_seconds INTEGER NOT NULL DEFAULT 300,
  created_by INTEGER, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS runtime_conversation (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER, agent_id INTEGER,
  title TEXT, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE TABLE IF NOT EXISTS runtime_message (
  id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
  created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE TABLE IF NOT EXISTS runtime_agent_execution (
  execution_id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL, tenant_id INTEGER NOT NULL, user_id INTEGER,
  agent_id INTEGER, agent_version INTEGER, trigger_type TEXT NOT NULL, input TEXT, output TEXT,
  status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, latency_ms INTEGER,
  model TEXT, token_input INTEGER DEFAULT 0, token_output INTEGER DEFAULT 0, error TEXT,
  data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS idx_exec_tenant_time ON runtime_agent_execution(tenant_id, started_at);
CREATE INDEX IF NOT EXISTS idx_exec_trace ON runtime_agent_execution(trace_id);
CREATE TABLE IF NOT EXISTS runtime_tool_execution (
  id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL, execution_id INTEGER, tenant_id INTEGER NOT NULL,
  tool_name TEXT NOT NULL, input TEXT, output TEXT, status TEXT NOT NULL,
  execution_time_ms INTEGER, error TEXT, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS idx_tool_exec_time ON runtime_tool_execution(tenant_id, created_at);
CREATE TABLE IF NOT EXISTS runtime_model_usage (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, execution_id INTEGER, model TEXT NOT NULL,
  token_input INTEGER NOT NULL, token_output INTEGER NOT NULL, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE TABLE IF NOT EXISTS runtime_scheduled_job (
  job_id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, tenant_id INTEGER NOT NULL, execution_id INTEGER,
  scheduled_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, status TEXT NOT NULL DEFAULT 'pending',
  retry_count INTEGER NOT NULL DEFAULT 0, failure_reason TEXT, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS idx_job_time ON runtime_scheduled_job(tenant_id, scheduled_at);

CREATE TABLE IF NOT EXISTS log_login_log (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER, ip TEXT, user_agent TEXT,
  success INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS idx_login_time ON log_login_log(tenant_id, created_at);
CREATE TABLE IF NOT EXISTS log_feature_usage (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER, feature TEXT NOT NULL,
  created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS idx_feature_time ON log_feature_usage(tenant_id, created_at);
CREATE TABLE IF NOT EXISTS log_operation_log (
  log_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER, module TEXT NOT NULL,
  action TEXT NOT NULL, resource_type TEXT, resource_id TEXT, before_data TEXT, after_data TEXT,
  ip TEXT, user_agent TEXT, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS idx_op_time ON log_operation_log(tenant_id, created_at);
CREATE TABLE IF NOT EXISTS log_amendment (
  id INTEGER PRIMARY KEY, target_table TEXT NOT NULL, record_id TEXT NOT NULL, before_json TEXT NOT NULL,
  after_json TEXT NOT NULL, operator TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_audit_log (
  audit_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, category TEXT NOT NULL, trace_id TEXT,
  payload TEXT, created_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'real'
);
CREATE TABLE IF NOT EXISTS audit_change (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, table_name TEXT NOT NULL, record_id TEXT NOT NULL,
  before_json TEXT, after_json TEXT, operator TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL
);

-- 项目（WorkBuddy 式协作容器：任务归属）
CREATE TABLE IF NOT EXISTS business_project (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL,
  name TEXT NOT NULL, description TEXT, status TEXT NOT NULL DEFAULT 'active',
  owner_id INTEGER, created_by INTEGER, created_at TEXT NOT NULL,
  data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_project_tenant ON business_project(tenant_id);

-- 知识库（两级：库 → 条目；knowledge_search 工具的数据源）
CREATE TABLE IF NOT EXISTS business_knowledge (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL,
  name TEXT NOT NULL, description TEXT, status TEXT NOT NULL DEFAULT 'active',
  created_by INTEGER, created_at TEXT NOT NULL,
  data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS business_knowledge_item (
  id INTEGER PRIMARY KEY, knowledge_id INTEGER NOT NULL REFERENCES business_knowledge(id),
  tenant_id INTEGER NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
  tags TEXT, created_by INTEGER, created_at TEXT NOT NULL,
  data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_kitem_tenant ON business_knowledge_item(tenant_id);
CREATE INDEX IF NOT EXISTS idx_kitem_kid ON business_knowledge_item(knowledge_id);

-- 一次性 AI 任务（新建任务：runAgent 真实执行，与 scheduled_task 定时任务互补）
CREATE TABLE IF NOT EXISTS business_work_task (
  id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL,
  title TEXT NOT NULL, instruction TEXT NOT NULL,
  agent_id INTEGER NOT NULL, project_id INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  execution_id INTEGER, trace_id TEXT, output TEXT, error TEXT, latency_ms INTEGER,
  created_by INTEGER, created_at TEXT NOT NULL, finished_at TEXT,
  data_origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_worktask_tenant ON business_work_task(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_worktask_project ON business_work_task(project_id);
`

const FEATURES = [
  ['data_center', '企业数据中心', 'data'], ['order_center', '订单中心', 'order'], ['service_center', '客服售后', 'service'],
  ['purchase_center', '采购中心', 'purchase'], ['crm_center', '销售CRM', 'crm'], ['finance_center', '财务中心', 'finance'],
  ['manage_center', '企业管理', 'manage'], ['ai_center', 'AI中心', 'ai'], ['automation_center', '自动化中心', 'automation'],
  ['simulator_center', '数据模拟中心', 'simulator'], ['log_center', '日志中心', 'log'], ['system_admin', '系统管理', 'system']
]

const PERMISSIONS = [
  ['agent:manage', 'Agent 管理', 'ai'], ['tool:manage', 'Tool 管理', 'ai'], ['task:manage', '自动任务管理', 'automation'],
  ['data:manage', '数据管理', 'system'], ['log:view', '日志查看', 'log'], ['audit:amend', '日志修正', 'log'],
  ['simulator:run', '数据模拟', 'simulator'], ['system:manage', '系统管理', 'system'], ['stats:view', '统计查看', 'data'],
  ['order:view', '订单查看', 'order'], ['finance:view', '财务查看', 'finance'], ['worktask:run', '任务执行', 'automation']
]

// 角色 → 权限（Platform Super Admin 通配）
const ROLE_PERMISSIONS = {
  platform_admin: ['*'],
  tenant_admin: ['agent:manage', 'tool:manage', 'task:manage', 'data:manage', 'log:view', 'audit:amend', 'simulator:run', 'system:manage', 'stats:view', 'order:view', 'finance:view', 'worktask:run'],
  dept_admin: ['agent:manage', 'log:view', 'stats:view', 'order:view', 'worktask:run'],
  employee: ['order:view', 'stats:view', 'worktask:run'],
  auditor: ['log:view', 'audit:amend', 'stats:view']
}

const SKILLS = [
  ['SQL 查询', '按权限域查询业务数据库并结构化返回', 'sql'],
  ['趋势分析', '对关键指标做日/周/月、同比环比与拐点分析', 'analysis'],
  ['风险评分', '综合交期/库存/设备等因素输出风险分与等级', 'analysis'],
  ['报告生成', '按模板生成业务日报/周报结构化结果', 'report'],
  ['通知发送', '将结构化结果推送至通知渠道', 'notification'],
  ['知识检索', '在企业知识库中检索相关条目', 'knowledge'],
  ['OCR 识别', '从图片/PDF 提取文本（模拟）', 'ocr']
]

const TOOLS = [
  ['query_order', 'database', '查询订单（自动注入租户与数据域过滤）', 0],
  ['query_inventory', 'database', '查询库存与安全库存', 0],
  ['query_customer', 'database', '查询客户档案', 0],
  ['query_finance', 'database', '查询财务收支数据', 0],
  ['query_after_sale', 'database', '查询售后工单', 0],
  ['update_order', 'database', '修改订单（敏感，需人工确认）', 1],
  ['create_work_order', 'database', '创建售后工单（敏感，需人工确认）', 1],
  ['send_notification', 'message', '发送通知（企业微信/钉钉/邮件渠道）', 0],
  ['knowledge_search', 'knowledge', '检索企业知识库条目（标题+正文模糊匹配，返回最相关条目）', 0]
]

function seed () {
  const t = now()
  db.exec('DELETE FROM audit_change; DELETE FROM audit_audit_log; DELETE FROM log_amendment; DELETE FROM log_operation_log;')
  db.exec('DELETE FROM log_feature_usage; DELETE FROM log_login_log;')
  db.exec('DELETE FROM runtime_scheduled_job; DELETE FROM runtime_model_usage; DELETE FROM runtime_tool_execution; DELETE FROM runtime_agent_execution; DELETE FROM runtime_message; DELETE FROM runtime_conversation;')
  db.exec('DELETE FROM business_scheduled_task; DELETE FROM business_agent_version; DELETE FROM business_agent; DELETE FROM business_tool; DELETE FROM business_skill;')
  db.exec('DELETE FROM business_after_sale; DELETE FROM business_finance; DELETE FROM business_inventory; DELETE FROM business_order; DELETE FROM business_customer;')
  db.exec('DELETE FROM business_user; DELETE FROM business_department; DELETE FROM business_tenant_feature; DELETE FROM business_feature; DELETE FROM business_role_permission; DELETE FROM business_permission; DELETE FROM business_tenant;')
  const insTenant = db.prepare("INSERT INTO business_tenant (id, code, name, status, data_origin, created_at) VALUES (?,? ,?,'active','manual', ?)")
  insTenant.run(1, 'corp-a', '智造精密科技（企业A）', t)
  insTenant.run(2, 'corp-b', '华越装备制造（企业B）', t)
  insTenant.run(3, 'corp-c', '恒新零部件（企业C）', t)

  const insDept = db.prepare('INSERT INTO business_department (tenant_id, name, parent_id) VALUES (?,?,?)')
  const depts = {}
  for (const [tid, names] of [[1, ['总经办', '生产部', '销售部', '客服部']], [2, ['管理层', '采购部', '财务部']], [3, ['管理部', '订单部']]]) {
    depts[tid] = {}
    for (const n of names) depts[tid][n] = insDept.run(tid, n, null).lastInsertRowid
  }

  const insUser = db.prepare('INSERT INTO business_user (tenant_id, username, password_hash, display_name, dept_id, title, role, data_scope, data_origin, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)')
  const users = [
    [1, 'platform', '平台超级管理员', null, 'CTO', 'platform_admin', 'tenant', 'Platform Super Admin'],
    [1, 'admin.a', '企业A管理员', '总经办', '总经理', 'tenant_admin', 'tenant'],
    [1, 'sales.a', '张销售', '销售部', '销售经理', 'employee', 'dept'],
    [1, 'cs.a', '李客服', '客服部', '客服工程师', 'employee', 'self'],
    [1, 'audit.a', '王审计', null, '审计员', 'auditor', 'tenant'],
    [2, 'admin.b', '企业B管理员', '管理层', '副总', 'tenant_admin', 'tenant'],
    [2, 'purchase.b', '赵采购', '采购部', '采购主管', 'employee', 'dept'],
    [3, 'admin.c', '企业C管理员', '管理部', '经理', 'tenant_admin', 'tenant']
  ]
  const uid = {}
  for (const [tid, uname, disp, dept, title, role, scope] of users) {
    uid[uname] = insUser.run(tid, uname, hashPassword('Zhiyun@2026'), disp, dept ? depts[tid][dept] : null, title, role, scope, 'manual', t).lastInsertRowid
  }

  const insPerm = db.prepare('INSERT INTO business_permission VALUES (?,?,?)')
  for (const [code, name, mod] of PERMISSIONS) insPerm.run(code, name, mod)
  const insRP = db.prepare('INSERT INTO business_role_permission VALUES (?,?)')
  for (const [role, perms] of Object.entries(ROLE_PERMISSIONS)) for (const p of perms) insRP.run(role, p)

  const insFeat = db.prepare('INSERT INTO business_feature VALUES (?,?,?)')
  for (const [code, name, mod] of FEATURES) insFeat.run(code, name, mod)
  const insTF = db.prepare('INSERT INTO business_tenant_feature VALUES (?,?,1)')
  // PRD §60 授权矩阵：企业A 全量；企业B 无采购/HR类(以 purchase/manage 为代表)；企业C 仅订单+财务+基础
  for (const f of FEATURES.map(x => x[0])) insTF.run(1, f)
  for (const f of FEATURES.map(x => x[0])) if (!['purchase_center', 'manage_center'].includes(f)) insTF.run(2, f)
  for (const f of ['order_center', 'finance_center', 'ai_center', 'log_center']) insTF.run(3, f)

  const insSkill = db.prepare('INSERT INTO business_skill (name, description, kind, data_origin) VALUES (?,?,?,?)')
  for (const [n, d, k] of SKILLS) insSkill.run(n, d, k, 'manual')

  const insTool = db.prepare('INSERT INTO business_tool (tenant_id, tool_name, tool_type, description, sensitive, data_origin) VALUES (?,?,?,?,?,?)')
  for (const [name, type, desc, sens] of TOOLS) { insTool.run(1, name, type, desc, sens, 'manual'); insTool.run(2, name, type, desc, sens, 'manual'); insTool.run(3, name, type, desc, sens, 'manual') }

  const insCust = db.prepare('INSERT INTO business_customer (tenant_id, name, tag, region, owner_id, data_origin) VALUES (?,?,?,?,?,?)')
  const custs = {}
  for (const [tid, list] of [[1, ['华南汽车集团|战略客户|华南', '华东重工|潜力客户|华东', '北方轨道交通|普通客户|华北']], [2, ['中西部矿业|战略客户|西南', '南方电力|普通客户|华南']], [3, ['珠三角电子厂|潜力客户|华南']]]) {
    custs[tid] = []
    for (const c of list) { const [n, tag, reg] = c.split('|'); custs[tid].push(insCust.run(tid, n, tag, reg, null, 'manual').lastInsertRowid) }
  }
  const insOrder = db.prepare('INSERT INTO business_order (tenant_id, order_no, customer_id, product, quantity, price, amount, due_date, status, current_node, progress, delay_hours, owner_id, risk_level, updated_at, data_origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
  let ono = 1000
  const orderRows = [
    [1, '主轴组件 S-200', 120, 850, null, '生产', 45, 0, '黄色'],
    [1, '精密齿轮箱 G-50', 40, 3200, null, '质检', 70, 0, '绿色'],
    [1, '伺服支架 X-8', 500, 96, null, '发货', 100, 0, '绿色'],
    [2, '矿用减速机 K-7', 15, 15800, null, '计划', 10, 36, '红色'],
    [2, '高压配电柜 D-3', 8, 42000, null, '包装', 90, 0, '绿色'],
    [3, '冲压模具 M-12', 3, 68000, null, '生产', 55, 12, '黄色']
  ]
  for (const [tid, prod, qty, price, _s, node, prog, delay, risk] of orderRows) {
    ono++
    insOrder.run(tid, `SO-2026-${ono}`, custs[tid][0], prod, qty, price, qty * price,
      '2026-09-15', prog === 100 ? 'done' : 'wip', node, prog, delay, null, risk, t, 'manual')
  }
  const insInv = db.prepare('INSERT INTO business_inventory (tenant_id, material, stock, safety_stock, consumption_rate, supplier, data_origin) VALUES (?,?,?,?,?,?,?)')
  for (const [tid, m, s, ss, cr, sup] of [[1, '42CrMo 圆钢', 320, 200, 45, '宝钢'], [1, 'SKF 轴承 6208', 60, 120, 25, 'SKF 中国'], [2, 'H62 黄铜板', 800, 300, 60, '洛阳铜业'], [3, 'Cr12MoV 模具钢', 45, 60, 8, '东北特钢']]) {
    insInv.run(tid, m, s, ss, cr, sup, 'manual')
  }
  const insFin = db.prepare('INSERT INTO business_finance (tenant_id, category, amount, month, note, data_origin) VALUES (?,?,?,?,?,?)')
  for (const [tid, cat, amt, mon] of [[1, 'income', 5820000, '2026-07'], [1, 'receivable', 1260000, '2026-07'], [1, 'expense', 3980000, '2026-07'], [2, 'income', 2410000, '2026-07'], [2, 'payable', 680000, '2026-07'], [3, 'income', 890000, '2026-07'], [1, 'income', 6110000, '2026-08'], [2, 'income', 2550000, '2026-08']]) {
    insFin.run(tid, cat, amt, mon, null, 'manual')
  }
  const insAS = db.prepare("INSERT INTO business_after_sale (tenant_id, customer_id, device, fault, status, engineer_id, created_at, data_origin) VALUES (?,?,?,?,?,?,?,?)")
  insAS.run(1, custs[1][0], 'CNC-加工中心 VMC850', '主轴异响，加工精度下降', 'open', null, t, 'manual')
  insAS.run(1, custs[1][1], '数控车床 CK6150', '液压系统漏油', 'processing', uid['cs.a'], t, 'manual')

  const insAgent = db.prepare(`INSERT INTO business_agent (tenant_id, agent_name, agent_type, system_prompt, model, temperature, tool_ids, skill_ids, knowledge_ids, permission_scope, status, version, created_by, updated_at, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'manual')`)
  const q = (names) => JSON.stringify(names)
  const agents = [
    [1, '订单监控 Agent', 'dashboard', '你是企业订单监控专家。基于工具返回的订单数据，输出各订单当前节点、完成度、延迟与风险等级。必须输出 JSON：{"orders":[{"order_no":"","current_node":"","progress":0,"delay_hours":0,"risk_level":""}],"summary":""}', q(['query_order']), q(['SQL 查询']), 'tenant', 'published'],
    [1, '交付风险预警 Agent', 'risk', '你是交付风险专家。综合订单进度、延迟、库存与历史交期评估风险。必须输出 JSON：{"risk_score":0,"risk_level":"绿色|黄色|红色","risk_reason":[],"expected_delay_hours":0,"suggestion":""}', q(['query_order', 'query_inventory']), q(['风险评分']), 'tenant', 'published'],
    [1, '企业日报 Agent', 'report', '你是企业经营日报专家。汇总当日订单、销售、应收与售后数据生成日报。必须输出 JSON：{"metrics":{"new_orders":0,"done_orders":0,"delayed_orders":0,"sales_amount":0,"receivable":0,"after_sale_open":0},"summary":""}', q(['query_order', 'query_finance', 'query_after_sale']), q(['报告生成', 'SQL 查询']), 'tenant', 'published'],
    [1, '客服售后 Agent', 'service', '你是售后客服专家。识别客户故障意图，先用工具查询历史工单与客户，再给出处理建议。规则：凡客户报告设备故障且无进行中工单，必须调用 create_work_order 工具创建工单（该工具需人工确认属正常流程，照常调用）。最终必须输出 JSON：{"intent":"","device_match":null,"similar_cases":[],"advice":"","create_work_order":true|false}', q(['query_after_sale', 'query_customer', 'create_work_order']), q(['知识检索']), 'tenant', 'published'],
    [1, '智能采购 Agent', 'purchase', '你是采购专家。结合库存、安全库存、消耗速度与供应商评估补货建议。必须输出 JSON：{"items":[{"material":"","suggest_qty":0,"suggest_supplier":"","risk_level":""}],"reason":""}', q(['query_inventory']), q(['SQL 查询', '风险评分']), 'tenant', 'published'],
    [1, '财务分析 Agent', 'finance', '你是财务分析专家。分析收入/成本/应收/应付并输出趋势判断。必须输出 JSON：{"income":0,"expense":0,"receivable":0,"payable":0,"trend":"上涨|下降|平稳","analysis":""}', q(['query_finance']), q(['趋势分析']), 'tenant', 'published'],
    [2, '企业日报 Agent', 'report', '你是企业经营日报专家。汇总当日订单与财务数据生成日报。必须输出 JSON：{"metrics":{"new_orders":0,"sales_amount":0},"summary":""}', q(['query_order', 'query_finance']), q(['报告生成']), 'tenant', 'published'],
    [2, '采购补货 Agent', 'purchase', '你是采购专家。评估库存与消耗，输出补货建议 JSON：{"items":[],"reason":""}', q(['query_inventory']), q(['SQL 查询']), 'tenant', 'published'],
    [3, '订单监控 Agent', 'dashboard', '你是订单监控专家。输出订单进度与风险 JSON：{"orders":[],"summary":""}', q(['query_order']), q(['SQL 查询']), 'tenant', 'published']
  ]
  const agentIds = {}
  for (const [tid, name, type, prompt, tools, skills, scope, status] of agents) {
    const id = insAgent.run(tid, name, type, prompt, 'deepseek-chat', 0.3, tools, skills, '[]', scope, status, 1, uid['admin.' + (tid === 1 ? 'a' : tid === 2 ? 'b' : 'c')], t).lastInsertRowid
    agentIds[tid + ':' + name] = id
    db.prepare('INSERT INTO business_agent_version (agent_id, version, snapshot, published_at, published_by) VALUES (?,?,?,?,?)')
      .run(id, 1, JSON.stringify({ agent_name: name, system_prompt: prompt, tool_ids: JSON.parse(tools) }), t, 1)
  }

  const insTask = db.prepare(`INSERT INTO business_scheduled_task (tenant_id, agent_id, name, trigger_type, cron, interval_seconds, condition_tool, condition_expr, input, status, max_retry, timeout_seconds, created_by, created_at, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
  insTask.run(1, agentIds['1:企业日报 Agent'], '每日经营日报', 'cron', '50 7 * * *', null, null, null,
    JSON.stringify({ instruction: '生成今日经营日报' }), 'active', 2, 300, uid['admin.a'], t, 'manual')
  insTask.run(1, agentIds['1:交付风险预警 Agent'], '订单风险巡检', 'interval', null, 3600, null, null,
    JSON.stringify({ instruction: '巡检全部在产订单的交付风险' }), 'active', 2, 300, uid['admin.a'], t, 'manual')
  insTask.run(1, agentIds['1:智能采购 Agent'], '库存低于安全线自动补货评估', 'condition', null, null, 'query_inventory', 'stock < safety_stock',
    JSON.stringify({ instruction: '对低于安全库存的物料给出补货建议' }), 'active', 2, 300, uid['admin.a'], t, 'manual')
  insTask.run(2, agentIds['2:企业日报 Agent'], '企业B每日日报', 'cron', '0 8 * * *', null, null, null,
    JSON.stringify({ instruction: '生成今日经营日报' }), 'active', 2, 300, uid['admin.b'], t, 'manual')
  console.log('种子数据完成：3 租户 / 8 用户 / 9 Agent / 9 Tool / 7 Skill / 4 定时任务')
}

/** 存量库迁移：补默认设置与对话型助手 Agent（幂等） */
function ensureMigrations () {
  const defaults = [
    ['brand.name', '智造云企业 AI 智能体平台'],
    ['brand.logo', ''],
    ['brand.primary_color', '#1677ff'],
    ['brand.subtitle', '企业 AI 操作系统'],
    ['qwenpaw.url', 'http://127.0.0.1:8088'],
    ['dsh.url', 'http://127.0.0.1:8308']
  ]
  const upsert = db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO NOTHING')
  for (const [k, v] of defaults) upsert.run(k, v, now())

  // 对话型智能助手：自然语言交流 + 可查业务数据（逐租户补齐，含未来新租户）
  const assistantPrompt = `你是智造云平台的企业智能助手，用简洁专业的中文与用户对话。
- 回答企业业务问题前，先通过工具查询真实数据（订单、库存、客户、售后、发票采购），不得编造。
- 查不到的数据如实说明，并建议用户补充信息。
- 涉及修改订单、创建工单等敏感操作时，先说明你的建议，告知需要人工确认后才会执行。
- 普通闲聊或常识问题直接回答。回答控制在 200 字内，可用列表。`
  const assistantTools = JSON.stringify(['query_order', 'query_inventory', 'query_customer', 'query_after_sale', 'query_finance', 'query_invoice', 'query_invoice_items', 'knowledge_search'])
  for (const t of db.prepare('SELECT id FROM business_tenant').all()) {
    if (db.prepare("SELECT 1 FROM business_agent WHERE tenant_id = ? AND agent_name = '企业智能助手'").get(t.id)) continue
    const id = db.prepare(`INSERT INTO business_agent (tenant_id, agent_name, agent_type, system_prompt, model, temperature, tool_ids, skill_ids, knowledge_ids, permission_scope, status, version, created_by, updated_at, data_origin)
      VALUES (?,?,'assistant',?, 'deepseek-chat', 0.4, ?, ?, '[]', 'tenant','published',1,null,?, 'manual')`)
      .run(t.id, '企业智能助手', assistantPrompt, assistantTools, JSON.stringify(['知识检索']), now()).lastInsertRowid
    db.prepare('INSERT INTO business_agent_version (agent_id, version, snapshot, published_at, published_by) VALUES (?,?,?,?,?)')
      .run(id, 1, JSON.stringify({ agent_name: '企业智能助手', system_prompt: assistantPrompt, tool_ids: JSON.parse(assistantTools) }), now(), 1)
    console.log(`已为租户 ${t.id} 创建「企业智能助手」`)
  }

  // 发票查询工具注册到全部租户（幂等）；对话助手补充发票工具；金汉隆租户建采购分析 Agent
  const INV_TOOLS = [['query_invoice', 'database', '查询进项发票（按供应商/月份/品类过滤，含供应商汇总）', 0], ['query_invoice_items', 'database', '查询发票物料明细（按发票号/物料名）', 0]]
  for (const [name, type, desc, sens] of INV_TOOLS) {
    if (!db.prepare('SELECT 1 FROM business_tool WHERE tool_name = ?').get(name)) {
      for (const t of db.prepare('SELECT id FROM business_tenant').all()) {
        db.prepare('INSERT INTO business_tool (tenant_id, tool_name, tool_type, description, sensitive, data_origin) VALUES (?,?,?,?,?, \'manual\')').run(t.id, name, type, desc, sens)
      }
    }
  }
  // 对话助手追加发票工具（幂等：未含则追加）
  for (const a of db.prepare("SELECT agent_id, tool_ids FROM business_agent WHERE agent_name = '企业智能助手'").all()) {
    const tools = JSON.parse(a.tool_ids)
    const merged = [...new Set([...tools, 'query_invoice', 'query_invoice_items'])]
    if (merged.length !== tools.length) db.prepare('UPDATE business_agent SET tool_ids = ? WHERE agent_id = ?').run(JSON.stringify(merged), a.agent_id)
  }
  // 金汉隆（含发票数据的租户）创建采购分析 Agent
  const jhl = db.prepare("SELECT id FROM business_tenant WHERE code = 'jhl'").get()
  if (jhl && !db.prepare("SELECT 1 FROM business_agent WHERE tenant_id = ? AND agent_name = '采购分析 Agent'").get(jhl.id)) {
    const prompt = `你是采购与供应链数据分析师，基于发票真实数据分析企业采购情况。综合使用工具查询发票头、物料明细与财务汇总。必须输出 JSON：{"total":0,"invoice_count":0,"top_supplier":"","top_supplier_amount":0,"monthly":[{"month":"","amount":0}],"category_dist":[{"category":"","amount":0}],"findings":[""],"suggestion":""}`
    const toolIds = JSON.stringify(['query_invoice', 'query_invoice_items', 'query_finance'])
    const id = db.prepare(`INSERT INTO business_agent (tenant_id, agent_name, agent_type, system_prompt, model, temperature, tool_ids, skill_ids, knowledge_ids, permission_scope, status, version, created_by, updated_at, data_origin)
      VALUES (?,?,'analysis',?, 'deepseek-chat', 0.2, ?, '[]', '[]', 'tenant','published',1,null,?, 'manual')`)
      .run(jhl.id, '采购分析 Agent', prompt, toolIds, now()).lastInsertRowid
    db.prepare('INSERT INTO business_agent_version (agent_id, version, snapshot, published_at, published_by) VALUES (?,?,?,?,?)')
      .run(id, 1, JSON.stringify({ agent_name: '采购分析 Agent', system_prompt: prompt, tool_ids: JSON.parse(toolIds) }), now(), 1)
    console.log('已创建「采购分析 Agent」（金汉隆）')
  }

  // worktask:run 权限码补齐（存量库；主键 (role, permission_code) 幂等）
  db.prepare("INSERT OR IGNORE INTO business_permission VALUES ('worktask:run','任务执行','automation')")
  for (const role of ['tenant_admin', 'dept_admin', 'employee']) {
    db.prepare('INSERT OR IGNORE INTO business_role_permission VALUES (?,?)').run(role, 'worktask:run')
  }

  // knowledge_search 工具描述更新为真知识库检索（幂等：未更新过才写）
  db.prepare("UPDATE business_tool SET description = ? WHERE tool_name = 'knowledge_search' AND description NOT LIKE '%知识库条目%'")
    .run('检索企业知识库条目（标题+正文模糊匹配，返回最相关条目）')

  // 每租户建默认知识库 + 示例条目（幂等：同名库跳过）
  const KB_SAMPLES = [
    ['CNC 主轴异响处理流程', '1) 立即停机，检查主轴轴承温度与润滑状态；2) 听音定位：前端异响多为轴承磨损，后端多为电机联轴器；3) 轴承磨损需更换成对角接触球轴承，装配前测量预紧量；4) 复位后空载运行 30 分钟无异常再投产；5) 每三个月补充主轴润滑脂，建立保养台账。', '设备维修'],
    ['液压系统漏油排查步骤', '1) 确认漏点：擦拭干净后垫白纸定位（接头/油封/油管三处高发）；2) 接头漏油先检查组合垫圈，禁止超扭矩复紧；3) 油封渗漏更换前测量轴径磨损，超过 0.05mm 需镀铬修复；4) 油管渗漏更换时同步更换 O 型圈并按对角顺序紧固；5) 加注原牌号液压油至液位计中线，排气后试运行。', '设备维修'],
    ['订单交付风险升级机制', '黄色风险（延迟 1-48h）：计划员当日与客户沟通调整；红色风险（延迟>48h 或关键物料断供）：升级至生产主管，启动替代料评审并每日报送；连续两单红色风险触发专项会议。所有升级需在订单备注留痕并同步销售。', '管理制度']
  ]
  for (const t of db.prepare('SELECT id FROM business_tenant').all()) {
    if (db.prepare("SELECT 1 FROM business_knowledge WHERE tenant_id = ? AND name = '企业知识库'").get(t.id)) continue
    const kbId = db.prepare('INSERT INTO business_knowledge (tenant_id, name, description, status, created_by, created_at, data_origin) VALUES (?,?,?,\'active\',null,?,\'manual\')')
      .run(t.id, '企业知识库', '平台默认知识库（设备维修、管理制度等企业知识沉淀）', now()).lastInsertRowid
    for (const [title, content, tags] of KB_SAMPLES) {
      db.prepare('INSERT INTO business_knowledge_item (knowledge_id, tenant_id, title, content, tags, created_by, created_at, data_origin) VALUES (?,?,?,?,?,null,?,\'manual\')')
        .run(kbId, t.id, title, content, tags, now())
    }
    console.log(`已为租户 ${t.id} 创建默认「企业知识库」(${KB_SAMPLES.length} 条示例)`)
  }
}

export function init () {
  db.exec(SCHEMA)
  ensureOsSchema(db)
  const count = db.prepare('SELECT COUNT(*) AS c FROM business_tenant').get().c
  if (count === 0 || process.argv.includes('--reset')) seed()
  ensureMigrations()
  return db
}

if (process.argv[1] && process.argv[1].endsWith('db.js')) {
  init()
  if (process.argv.includes('--reset')) console.log('数据库已重置并重新播种：', DB_PATH)
}
