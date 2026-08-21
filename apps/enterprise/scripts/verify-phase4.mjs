import assert from 'node:assert/strict'
import { evaluateToolRisk } from '../server/os/risk-control.js'

assert.equal(evaluateToolRisk({ toolName: 'query_orders', sensitive: false }).allowed, true)
assert.equal(evaluateToolRisk({ toolName: 'update_order', sensitive: true, userId: null, confirmed: true }).code, 'AUTOMATION_WRITE_BLOCKED')
assert.equal(evaluateToolRisk({ toolName: 'update_order', sensitive: true, userId: 1, confirmed: false }).code, 'CONFIRM_REQUIRED')
assert.equal(evaluateToolRisk({ toolName: 'update_order', sensitive: true, userId: 1, confirmed: true, writesEnabled: false }).code, 'WRITE_KILL_SWITCH')
assert.equal(evaluateToolRisk({ toolName: 'update_order', sensitive: true, userId: 1, confirmed: true, recentWrites: 20 }).code, 'WRITE_RATE_LIMIT')
assert.equal(evaluateToolRisk({ toolName: 'update_order', sensitive: true, userId: 1, confirmed: true, args: { order_no: 'SO-2026-1001', progress: 101 } }).code, 'INVALID_PROGRESS')
assert.equal(evaluateToolRisk({ toolName: 'update_order', sensitive: true, userId: 1, confirmed: true, args: { order_no: 'SO-2026-1001', progress: 80, risk_level: '黄色' } }).allowed, true)

const nested = { a: { b: { c: { d: { e: { f: { g: true } } } } } } }
assert.equal(evaluateToolRisk({ toolName: 'query_orders', sensitive: false, args: nested }).code, 'ARGUMENT_TOO_DEEP')

console.log('AI-OS Phase 4 verification passed: automation block, confirmation, kill switch, rate limit, argument validation')
