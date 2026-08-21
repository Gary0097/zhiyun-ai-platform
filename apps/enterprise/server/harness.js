// DeepSeek Harness Runtime：Context Builder → 权限校验 → Agent Loop → Model Adapter → Tool Call → Guard → 结构化输出 → Trace
import { randomUUID } from 'node:crypto'
import { db, now } from './db.js'
import { chat, modelInfo } from './llm.js'
import { toolSchemasFor, executeTool } from './tools.js'
import { dataScope, PermissionError } from './auth.js'

const MAX_STEPS = 6

/** Context Builder：动态组装最小必要上下文（禁止全量企业数据塞入 Prompt，PRD §4.1） */
export function buildContext ({ agent, user, tenant, instruction }) {
  const toolIds = JSON.parse(agent.tool_ids || '[]')
  const skillIds = JSON.parse(agent.skill_ids || '[]')
  const skills = skillIds.length
    ? db.prepare(`SELECT name, description FROM business_skill WHERE name IN (${skillIds.map(() => '?').join(',')})`).all(...skillIds)
    : []
  const sections = [
    `# 角色与任务\n${agent.system_prompt}`,
    `# 企业上下文\n当前企业：${tenant.name}（tenant_id=${tenant.id}）。所有数据访问自动限定本企业。`,
    user ? `# 当前用户\n${user.display_name}（${user.title || '员工'}，角色 ${user.role}，数据域 ${user.data_scope}）` : '# 当前用户\n系统自动任务（无交互用户）',
    skills.length ? `# 可用技能\n${skills.map(s => `- ${s.name}：${s.description}`).join('\n')}` : '',
    toolIds.length ? `# 可用工具\n${toolIds.join('、')}。业务数据必须通过工具获取，不得凭空编造。` : '# 可用工具\n无。',
    // 对话型助手自然语言交流；业务 Agent 维持 JSON 结构化输出契约
    agent.agent_type === 'assistant'
      ? '# 输出要求\n直接用简洁中文回答用户，不要输出 JSON 或多余包装。'
      : '# 输出要求\n最终回复必须是符合系统提示词约定的单个 JSON 对象，不要输出多余文本。'
  ]
  return { systemPrompt: sections.filter(Boolean).join('\n\n'), toolIds }
}

/**
 * 执行一次 Agent 运行（手动或调度触发），全链路写入 runtime_* 并关联 trace_id
 * @returns {Promise<{executionId:number, traceId:string, status:string, output:string, latencyMs:number, pendingConfirm:*}>}
 */
export async function runAgent ({ agentId, user, instruction, triggerType = 'manual', confirmedTool = null }) {
  const agent = db.prepare('SELECT * FROM business_agent WHERE agent_id = ?').get(agentId)
  if (!agent) throw Object.assign(new Error('Agent 不存在'), { status: 404 })
  if (agent.status !== 'published') throw Object.assign(new Error(`Agent 状态为 ${agent.status}，仅 published 可执行`), { status: 400 })
  if (user && user.tenant_id !== agent.tenant_id) throw new PermissionError('不得跨租户执行 Agent')

  const tenant = db.prepare('SELECT * FROM business_tenant WHERE id = ?').get(agent.tenant_id)
  const traceId = randomUUID()
  const started = Date.now()
  const executionId = db.prepare(`INSERT INTO runtime_agent_execution (trace_id, tenant_id, user_id, agent_id, agent_version, trigger_type, input, status, started_at, model, data_origin)
    VALUES (?,?,?,?,?,?,?, 'running', ?, ?, 'real')`)
    .run(traceId, agent.tenant_id, user?.id || null, agent.agent_id, agent.version, triggerType,
      JSON.stringify({ instruction }), now(), agent.model).lastInsertRowid

  db.prepare("INSERT INTO audit_audit_log (tenant_id, category, trace_id, payload, created_at, data_origin) VALUES (?, 'trace.span', ?, ?, ?, 'real')")
    .run(agent.tenant_id, traceId, JSON.stringify({ span: 'context.build', agent: agent.agent_name, trigger: triggerType, user: user?.display_name || 'system' }), now())

  let status = 'success'; let output = ''; let error = null
  let tokenIn = 0; let tokenOut = 0
  const scope = user ? dataScope(user) : { clause: '', params: [] }
  const { systemPrompt, toolIds } = buildContext({ agent, user, tenant, instruction })
  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: String(instruction || '请执行你的职责。') }
  ]
  const schemas = toolSchemasFor(agent.tenant_id, toolIds)

  try {
    for (let step = 0; step < MAX_STEPS; step++) {
      db.prepare("INSERT INTO audit_audit_log (tenant_id, category, trace_id, payload, created_at, data_origin) VALUES (?, 'trace.span', ?, ?, ?, 'real')")
        .run(agent.tenant_id, traceId, JSON.stringify({ span: `llm.request.step${step + 1}`, model: agent.model, tools: toolIds }), now())
      const res = await chat(messages, schemas)
      tokenIn += res.tokenInput; tokenOut += res.tokenOutput

      if (res.toolCalls?.length) {
        for (const call of res.toolCalls) {
          db.prepare("INSERT INTO audit_audit_log (tenant_id, category, trace_id, payload, created_at, data_origin) VALUES (?, 'trace.span', ?, ?, ?, 'real')")
            .run(agent.tenant_id, traceId, JSON.stringify({ span: 'tool.call', tool: call.name, args: call.args }), now())
          try {
            const out = executeTool({
              tenantId: agent.tenant_id, userId: user?.id || null, traceId, executionId,
              toolName: call.name, args: call.args, agentToolIds: toolIds,
              confirmed: confirmedTool === call.name, scope
            })
            messages.push({ role: 'assistant', content: '', tool_calls: [{ id: call.name, type: 'function', function: { name: call.name, arguments: JSON.stringify(call.args) } }] })
            messages.push({ role: 'tool', name: call.name, content: JSON.stringify(out).slice(0, 4000) })
          } catch (e) {
            if (e.status === 202) {
              // 敏感操作：AI 建议已生成，挂起等待人工确认（PRD §59）
              messages.push({ role: 'assistant', content: '', tool_calls: [{ id: call.name, type: 'function', function: { name: call.name, arguments: JSON.stringify(call.args) } }] })
              messages.push({ role: 'tool', name: call.name, content: JSON.stringify({ pending_confirm: true, message: e.message }) })
            } else throw e
          }
        }
        continue
      }
      output = extractJson(res.content) || res.content
      break
    }
    if (!output) { output = JSON.stringify({ note: '达到最大步数未产出最终结果' }); status = 'failed'; error = 'max_steps' }
  } catch (e) {
    status = 'failed'; error = e.message; output = JSON.stringify({ error: e.message })
  }

  const latency = Date.now() - started
  db.prepare(`UPDATE runtime_agent_execution SET output = ?, status = ?, finished_at = ?, latency_ms = ?, token_input = ?, token_output = ?, error = ? WHERE execution_id = ?`)
    .run(typeof output === 'string' ? output : JSON.stringify(output), status, now(), latency, tokenIn, tokenOut, error, executionId)
  db.prepare('INSERT INTO runtime_model_usage (tenant_id, execution_id, model, token_input, token_output, created_at, data_origin) VALUES (?,?,?,?,?,?, \'real\')')
    .run(agent.tenant_id, executionId, agent.model, tokenIn, tokenOut, now())
  db.prepare("INSERT INTO audit_audit_log (tenant_id, category, trace_id, payload, created_at, data_origin) VALUES (?, 'trace.span', ?, ?, ?, 'real')")
    .run(agent.tenant_id, traceId, JSON.stringify({ span: 'execution.end', status, latency_ms: latency, tokens: tokenIn + tokenOut }), now())

  return { executionId: Number(executionId), traceId, status, output: typeof output === 'string' ? output : JSON.stringify(output), latencyMs: latency }
}

function extractJson (text) {
  if (!text) return null
  try { return JSON.parse(text) } catch {}
  const m = text.match(/\{[\s\S]*\}/)
  if (m) { try { return JSON.parse(m[0]) } catch {} }
  return null
}

/** Trace Replay：按 trace_id 还原完整链路（PRD §69） */
export function replayTrace (tenantId, traceId) {
  const execution = db.prepare('SELECT * FROM runtime_agent_execution WHERE tenant_id = ? AND trace_id = ?').get(tenantId, traceId)
  if (!execution) return null
  const tools = db.prepare('SELECT tool_name, input, output, status, execution_time_ms, created_at FROM runtime_tool_execution WHERE trace_id = ? ORDER BY id').all(traceId)
  const spans = db.prepare("SELECT payload, created_at FROM audit_audit_log WHERE trace_id = ? AND category = 'trace.span' ORDER BY audit_id").all(traceId)
  const agent = db.prepare('SELECT agent_name, system_prompt, version FROM business_agent WHERE agent_id = ?').get(execution.agent_id)
  const user = execution.user_id ? db.prepare('SELECT display_name, role FROM business_user WHERE id = ?').get(execution.user_id) : null
  return {
    trace_id: traceId,
    user: user || { display_name: '系统自动任务', role: 'system' },
    agent: agent ? { name: agent.agent_name, version: agent.version, system_prompt: agent.system_prompt } : null,
    execution, tool_calls: tools,
    timeline: spans.map(s => ({ at: s.created_at, ...JSON.parse(s.payload) }))
  }
}
