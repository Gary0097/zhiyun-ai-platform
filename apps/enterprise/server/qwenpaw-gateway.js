// QwenPaw -> 企业控制平面可信网关：HMAC 服务认证、服务端身份映射、只读工具白名单。
import { createHash, createHmac, randomUUID, timingSafeEqual } from 'node:crypto'
import { db, now } from './db.js'
import { dataScope } from './auth.js'
import { executeTool } from './tools.js'

export const QWENPAW_READ_TOOLS = new Set(['query_order', 'query_inventory', 'query_customer', 'knowledge_search'])
const MAX_SKEW_MS = 60_000
const usedNonces = new Map()

const fail = (message, status = 401) => { const e = new Error(message); e.status = status; throw e }
const digest = (value) => createHash('sha256').update(value).digest('hex')

export function signaturePayload ({ method, path, timestamp, nonce, identity, body }) {
  return [method.toUpperCase(), path, timestamp, nonce, identity, digest(body)].join('\n')
}

function pruneNonces (at) {
  for (const [nonce, expires] of usedNonces) if (expires <= at) usedNonces.delete(nonce)
}

export function verifyQwenPawRequest (req, body) {
  const secret = process.env.ZHIYUN_GATEWAY_SECRET || ''
  if (secret.length < 32) fail('企业 Tool Gateway 未配置安全密钥', 503)
  const service = String(req.headers['x-zhiyun-service'] || '')
  const timestamp = String(req.headers['x-zhiyun-timestamp'] || '')
  const nonce = String(req.headers['x-zhiyun-nonce'] || '')
  const identity = String(req.headers['x-zhiyun-identity'] || '')
  const signature = String(req.headers['x-zhiyun-signature'] || '')
  if (service !== 'qwenpaw' || !timestamp || !nonce || !identity || !signature) fail('QwenPaw 服务认证信息不完整')
  if (!/^[A-Za-z0-9._:@-]{1,128}$/.test(identity) || !/^[a-f0-9-]{16,64}$/i.test(nonce)) fail('QwenPaw 身份或 nonce 格式无效')
  const at = Date.now(); const sentAt = Number(timestamp)
  if (!Number.isFinite(sentAt) || Math.abs(at - sentAt) > MAX_SKEW_MS) fail('QwenPaw 请求已过期')
  pruneNonces(at)
  if (usedNonces.has(nonce)) fail('QwenPaw 请求 nonce 已使用')
  const path = new URL(req.url, 'http://localhost').pathname
  const payload = signaturePayload({ method: req.method, path, timestamp, nonce, identity, body })
  const expected = createHmac('sha256', secret).update(payload).digest('hex')
  const a = Buffer.from(expected); const b = Buffer.from(signature)
  if (a.length !== b.length || !timingSafeEqual(a, b)) fail('QwenPaw 请求签名无效')
  usedNonces.set(nonce, at + MAX_SKEW_MS)
  return identity
}

export function resolveQwenPawIdentity (externalIdentity) {
  const row = db.prepare(`SELECT u.* FROM integration_identity_map m
    JOIN business_user u ON u.id = m.user_id AND u.tenant_id = m.tenant_id
    WHERE m.provider = 'qwenpaw' AND m.external_user_id = ? AND m.status = 'active' AND u.status = 'active'`).get(externalIdentity)
  if (!row) fail(`QwenPaw 身份未映射：${externalIdentity}`, 403)
  return row
}

export function runQwenPawReadTool ({ externalIdentity, toolName, args }) {
  if (!QWENPAW_READ_TOOLS.has(toolName)) fail(`Tool Gateway 仅允许只读工具：${toolName}`, 403)
  const user = resolveQwenPawIdentity(externalIdentity)
  const traceId = `qwp-${randomUUID()}`
  const startedAt = now()
  const executionId = Number(db.prepare(`INSERT INTO runtime_agent_execution
    (trace_id, tenant_id, user_id, agent_id, trigger_type, input, status, started_at, model, data_origin)
    VALUES (?,?,?,null,'qwenpaw_tool',?,'running',?,'qwenpaw-2.1.0','real')`)
    .run(traceId, user.tenant_id, user.id, JSON.stringify({ toolName, args: args || {} }), startedAt).lastInsertRowid)
  try {
    const output = executeTool({
      tenantId: user.tenant_id, userId: user.id, traceId, executionId, toolName,
      args: args || {}, agentToolIds: [...QWENPAW_READ_TOOLS], confirmed: false, scope: dataScope(user)
    })
    db.prepare("UPDATE runtime_agent_execution SET output=?, status='success', finished_at=?, latency_ms=? WHERE execution_id=?")
      .run(JSON.stringify(output), now(), Date.now() - Date.parse(startedAt), executionId)
    return { ok: true, traceId, executionId, tool: toolName, data: output }
  } catch (error) {
    db.prepare("UPDATE runtime_agent_execution SET status='failed', error=?, finished_at=?, latency_ms=? WHERE execution_id=?")
      .run(error.message, now(), Date.now() - Date.parse(startedAt), executionId)
    error.traceId = traceId
    throw error
  }
}

