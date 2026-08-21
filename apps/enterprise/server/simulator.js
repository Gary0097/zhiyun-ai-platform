// 历史数据模拟器（Data Simulator）：生成 2025-12-01 ~ 2026-08-31 系统使用数据
// 规律：工作日/周末差异、分时段权重、月度增长曲线（试运行→春节回落→快速增长→稳定→自动任务增长）
// 所有生成数据 data_origin = 'simulated'；数据链 User→Agent→Tool→Log 完整关联，看板只做数据库聚合
import { db } from './db.js'
import { randomUUID } from 'node:crypto'

// 月度增长系数（PRD §36）
const MONTH_FACTOR = { '2025-12': 0.25, '2026-01': 0.5, '2026-02': 0.18, '2026-03': 0.85, '2026-04': 1.0, '2026-05': 1.05, '2026-06': 1.1, '2026-07': 1.35, '2026-08': 1.4 }
// 时段权重（PRD §35）
const HOUR_WEIGHTS = [[8, 10, 3.0], [10, 12, 2.2], [12, 13.5, 0.5], [14, 17, 2.6], [17, 18, 1.0], [18, 24, 0.5], [0, 8, 0.1]]
const WEEKEND_RATE = 0.25

function mulberry32 (seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed)
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}

function weightedHour (rnd) {
  const total = HOUR_WEIGHTS.reduce((s, [, , w]) => s + w, 0)
  let r = rnd() * total
  for (const [from, to, w] of HOUR_WEIGHTS) {
    if ((r -= w) <= 0) return from + Math.floor(rnd() * (to - from))
  }
  return 10
}

const pick = (rnd, arr) => arr[Math.floor(rnd() * arr.length)]

/**
 * @param {object} cfg {start:'2025-12-01', end:'2026-08-31', dailyBase, failRate, toolCallRate, scheduledRatio, seed, tenants?}
 */
export function simulate (cfg = {}) {
  const start = new Date(cfg.start || '2025-12-01T00:00:00')
  const end = new Date(cfg.end || '2026-08-31T23:59:59')
  if (end < start) throw new Error('结束时间早于开始时间')
  const dailyBase = cfg.dailyBase ?? 480
  const failRate = cfg.failRate ?? 0.035
  const toolCallRate = cfg.toolCallRate ?? 0.78
  const scheduledRatioBase = cfg.scheduledRatio ?? 0.18
  const rnd = mulberry32(cfg.seed ?? 20260831)

  const tenantIds = (cfg.tenants?.length ? cfg.tenants : db.prepare('SELECT id FROM business_tenant WHERE status = \'active\'').all().map(r => r.id))
  const tenants = tenantIds.map(id => {
    const users = db.prepare("SELECT id FROM business_user WHERE tenant_id = ? AND status = 'active'").all(id).map(r => r.id)
    const agents = db.prepare("SELECT agent_id, agent_name, model, version FROM business_agent WHERE tenant_id = ? AND status = 'published'").all(id)
    const tools = JSON.parse(db.prepare('SELECT tool_ids FROM business_agent WHERE tenant_id = ? AND status = \'published\' LIMIT 1').get(id)?.tool_ids || '[]')
    const features = db.prepare('SELECT feature_code FROM business_tenant_feature WHERE tenant_id = ? AND enabled = 1').all(id).map(r => r.feature_code)
    const tasks = db.prepare("SELECT task_id, agent_id, name FROM business_scheduled_task WHERE tenant_id = ? AND status = 'active'").all(id)
    return { id, users, agents, tools, features, tasks, weight: 0.5 + rnd() }
  }).filter(t => t.agents.length && t.users.length)

  // 预编译语句
  const insExec = db.prepare(`INSERT INTO runtime_agent_execution (trace_id, tenant_id, user_id, agent_id, agent_version, trigger_type, input, output, status, started_at, finished_at, latency_ms, model, token_input, token_output, error, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'simulated')`)
  const insToolExec = db.prepare(`INSERT INTO runtime_tool_execution (trace_id, execution_id, tenant_id, tool_name, input, output, status, execution_time_ms, error, created_at, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?, 'simulated')`)
  const insMsg = db.prepare('INSERT INTO runtime_message (conversation_id, role, content, created_at, data_origin) VALUES (?,?,?,?, \'simulated\')')
  const insConv = db.prepare('INSERT INTO runtime_conversation (tenant_id, user_id, agent_id, title, created_at, data_origin) VALUES (?,?,?,?,?, \'simulated\')')
  const insLogin = db.prepare('INSERT INTO log_login_log (tenant_id, user_id, ip, user_agent, success, created_at, data_origin) VALUES (?,?,?,?,?,?, \'simulated\')')
  const insFeature = db.prepare('INSERT INTO log_feature_usage (tenant_id, user_id, feature, created_at, data_origin) VALUES (?,?,?,?, \'simulated\')')
  const insOp = db.prepare('INSERT INTO log_operation_log (tenant_id, user_id, module, action, resource_type, resource_id, ip, user_agent, created_at, data_origin) VALUES (?,?,?,?,?,?,?,?,?, \'simulated\')')
  const insJob = db.prepare(`INSERT INTO runtime_scheduled_job (task_id, tenant_id, execution_id, scheduled_at, started_at, finished_at, status, retry_count, failure_reason, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?, 'simulated')`)
  const insUsage = db.prepare('INSERT INTO runtime_model_usage (tenant_id, execution_id, model, token_input, token_output, created_at, data_origin) VALUES (?,?,?,?,?,?, \'simulated\')')

  const OUT_SAMPLES = {
    日报: '{"metrics":{"new_orders":3,"done_orders":1,"delayed_orders":0,"sales_amount":986000},"summary":"经营平稳"}',
    风险: '{"risk_score":42,"risk_level":"黄色","risk_reason":["进度略慢"],"expected_delay_hours":8,"suggestion":"跟催排期"}',
    订单: '{"orders":[{"order_no":"SO-2026-1001","progress":60,"risk_level":"绿色"}],"summary":"整体受控"}',
    客服: '{"intent":"售后故障","advice":"建议检测主轴轴承","create_work_order":false}',
    采购: '{"items":[{"material":"轴承","suggest_qty":120}],"reason":"低于安全库存"}',
    财务: '{"income":520000,"expense":380000,"trend":"上涨","analysis":"回款正常"}'
  }
  const outFor = (name) => Object.keys(OUT_SAMPLES).find(k => name.includes(k)) || '订单'

  const summary = { days: 0, agentExecutions: 0, toolExecutions: 0, conversations: 0, messages: 0, logins: 0, featureUsage: 0, operationLogs: 0, scheduledJobs: 0 }
  const BATCH = 4000
  let pending = 0
  db.exec('BEGIN')
  const commitIfDue = () => { if (++pending >= BATCH) { db.exec('COMMIT'); db.exec('BEGIN'); pending = 0 } }

  for (let day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
    const y = day.getFullYear(); const m = String(day.getMonth() + 1).padStart(2, '0'); const d = String(day.getDate()).padStart(2, '0')
    const monthKey = `${y}-${m}`
    const factor = MONTH_FACTOR[monthKey] ?? 1
    const weekday = day.getDay() !== 0 && day.getDay() !== 6
    const dowFactor = weekday ? 1 : WEEKEND_RATE
    // 自动任务占比自 2026-07 起明显上升（PRD §36）
    const scheduledRatio = monthKey >= '2026-07' ? scheduledRatioBase * 1.8 : scheduledRatioBase * Math.min(1, factor * 2)
    const dayVolume = Math.round(dailyBase * factor * dowFactor)
    summary.days++

    for (const t of tenants) {
      const tShare = Math.max(1, Math.round(dayVolume * t.weight / tenants.reduce((s, x) => s + x.weight, 0)))
      // 登录：工作日每活跃用户 1-3 次
      if (weekday || rnd() < 0.4) {
        for (const uid of t.users) {
          const n = weekday ? 1 + Math.floor(rnd() * 2.2) : 1
          for (let i = 0; i < n; i++) {
            insLogin.run(t.id, uid, `10.8.${t.id}.${1 + Math.floor(rnd() * 200)}`, pick(rnd, ['Chrome/WebView', 'Edge', 'dsh-web', 'Mobile']), rnd() > 0.02 ? 1 : 0,
              new Date(y, day.getMonth(), day.getDate(), weightedHour(rnd), Math.floor(rnd() * 60)).toISOString())
            summary.logins++; commitIfDue()
          }
        }
      }
      // Agent 执行（手动 + 自动）
      for (let i = 0; i < tShare; i++) {
        const hour = weightedHour(rnd)
        const ts = new Date(y, day.getMonth(), day.getDate(), hour, Math.floor(rnd() * 60), Math.floor(rnd() * 60))
        const isScheduled = rnd() < scheduledRatio
        const agent = pick(rnd, t.agents)
        const user = isScheduled ? null : pick(rnd, t.users)
        const failed = rnd() < failRate
        const traceId = randomUUID()
        const latency = 400 + Math.floor(rnd() * 8000)
        const tokIn = 600 + Math.floor(rnd() * 4200)
        const tokOut = 120 + Math.floor(rnd() * 1400)
        const finished = new Date(ts.getTime() + latency)
        const execId = insExec.run(traceId, t.id, user, agent.agent_id, agent.version,
          isScheduled ? 'scheduled:scheduler' : 'manual',
          JSON.stringify({ instruction: isScheduled ? `${agent.agent_name} 定时执行` : `${agent.agent_name} 手动调用` }),
          failed ? null : OUT_SAMPLES[outFor(agent.agent_name)],
          failed ? 'failed' : 'success', ts.toISOString(), finished.toISOString(), latency, agent.model, tokIn, tokOut,
          failed ? pick(rnd, ['模型超时', 'JSON 解析异常', '权限不足', '数据为空', '网络异常']) : null).lastInsertRowid
        summary.agentExecutions++; commitIfDue()
        insUsage.run(t.id, Number(execId), agent.model, tokIn, tokOut, ts.toISOString()); commitIfDue()

        // 手动执行形成会话与消息（User → Agent 数据链）
        if (!isScheduled && rnd() < 0.6) {
          const convId = insConv.run(t.id, user, agent.agent_id, `${agent.agent_name} · ${monthKey}-${d}`, ts.toISOString()).lastInsertRowid
          insMsg.run(Number(convId), 'user', '请处理今天的业务数据', ts.toISOString())
          insMsg.run(Number(convId), 'assistant', failed ? '{"error":"执行失败"}' : OUT_SAMPLES[outFor(agent.agent_name)], finished.toISOString())
          summary.conversations++; summary.messages += 2; commitIfDue()
        }
        // Tool 调用链（数据查询为主）
        if (rnd() < toolCallRate) {
          const nTools = 1 + Math.floor(rnd() * 2.4)
          for (let k = 0; k < nTools; k++) {
            const tool = pick(rnd, t.tools.length ? t.tools : ['query_order'])
            const tLat = 20 + Math.floor(rnd() * 900)
            const tFailed = rnd() < failRate * 0.6
            insToolExec.run(traceId, Number(execId), t.id, tool, '{}', tFailed ? '{"error":"查询失败"}' : '{"count":3}', tFailed ? 'failed' : 'success', tLat,
              tFailed ? '数据库繁忙' : null, new Date(ts.getTime() + 50 + k * tLat).toISOString())
            summary.toolExecutions++; commitIfDue()
          }
        }
        // 页面功能使用
        if (!isScheduled && rnd() < 0.5 && t.features.length) {
          insFeature.run(t.id, user, pick(rnd, t.features), ts.toISOString()); summary.featureUsage++; commitIfDue()
        }
      }
      // 定时任务执行记录（有任务的租户；按任务日粒度生成）
      if (weekday || rnd() < 0.3) {
        for (const task of t.tasks) {
          if (rnd() < 0.12) continue
          const scheduledAt = new Date(y, day.getMonth(), day.getDate(), 7, 50)
          if (scheduledAt > end) continue
          const jFailed = rnd() < failRate * 0.8
          const jLat = 2000 + Math.floor(rnd() * 20000)
          insJob.run(task.task_id, t.id, null, scheduledAt.toISOString(),
            new Date(scheduledAt.getTime() + 30000).toISOString(),
            new Date(scheduledAt.getTime() + 30000 + jLat).toISOString(),
            jFailed ? 'failed' : 'success', jFailed ? 1 + Math.floor(rnd() * 2) : 0,
            jFailed ? pick(rnd, ['模型超时', '工具执行失败', '数据为空']) : null)
          summary.scheduledJobs++; commitIfDue()
        }
      }
      // 管理操作日志（稀疏）
      if (rnd() < 0.25 && t.users.length) {
        insOp.run(t.id, pick(rnd, t.users), pick(rnd, ['ai', 'automation', 'system']), pick(rnd, ['运行Agent', '修改Agent', '创建任务', '上传文件', '修改用户']),
          'agent', String(1 + Math.floor(rnd() * 9)), '10.8.0.5', 'Chrome', new Date(y, day.getMonth(), day.getDate(), weightedHour(rnd)).toISOString())
        summary.operationLogs++; commitIfDue()
      }
    }
  }
  db.exec('COMMIT')
  return summary
}

/** 清空指定范围的模拟数据（按 data_origin + 时间；end 含当日全天） */
export function clearSimulated ({ start = '1970-01-01', end = '2999-12-31', tenantId = null } = {}) {
  // 纯日期补全到当日末尾，避免 BETWEEN 漏掉结束日白天的数据
  const s = new Date(start.length === 10 ? start + 'T00:00:00' : start).toISOString()
  const e = new Date(end.length === 10 ? end + 'T23:59:59' : end).toISOString()
  const t = tenantId ? 'AND tenant_id = ?' : ''
  const p = tenantId ? [tenantId] : []
  let removed = 0
  for (const [table, col] of [['runtime_agent_execution', 'started_at'], ['runtime_tool_execution', 'created_at'], ['runtime_conversation', 'created_at'], ['runtime_model_usage', 'created_at'], ['runtime_scheduled_job', 'scheduled_at'], ['log_login_log', 'created_at'], ['log_feature_usage', 'created_at'], ['log_operation_log', 'created_at']]) {
    // 会话先删消息
    if (table === 'runtime_conversation') {
      const ids = db.prepare(`SELECT id FROM runtime_conversation WHERE data_origin='simulated' AND created_at BETWEEN ? AND ? ${t}`).all(s, e, ...p).map(r => r.id)
      if (ids.length) { db.prepare(`DELETE FROM runtime_message WHERE conversation_id IN (${ids.map(() => '?').join(',')})`).run(...ids); removed += ids.length }
    }
    const r = db.prepare(`DELETE FROM ${table} WHERE data_origin='simulated' AND ${col} BETWEEN ? AND ? ${t}`).run(s, e, ...p)
    removed += r.changes
  }
  return removed
}
