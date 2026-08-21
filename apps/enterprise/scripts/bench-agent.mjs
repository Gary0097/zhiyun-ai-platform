// 单次真实 Agent 执行计时（校准超时参数）
import { init } from '../server/db.js'
init()
import { runAgent } from '../server/harness.js'
const t0 = Date.now()
const r = await runAgent({ agentId: 3, user: null, instruction: '生成今日经营日报', triggerType: 'manual' })
console.log(`状态=${r.status} 耗时=${((Date.now() - t0) / 1000).toFixed(1)}s trace=${r.traceId}`)
console.log('输出:', r.output.slice(0, 300))
process.exit(0)
