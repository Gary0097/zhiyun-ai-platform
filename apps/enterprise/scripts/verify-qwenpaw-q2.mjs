import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const read = (path) => readFileSync(join(root, path), 'utf8')
const checks = [
  ['HMAC 网关', read('enterprise/server/qwenpaw-gateway.js').includes('timingSafeEqual')],
  ['防重放 nonce', read('enterprise/server/qwenpaw-gateway.js').includes('usedNonces.has(nonce)')],
  ['服务端身份映射', read('enterprise/server/db.js').includes('integration_identity_map')],
  ['只读工具白名单', read('enterprise/server/qwenpaw-gateway.js').includes("'knowledge_search'")],
  ['统一 Trace', read('enterprise/server/qwenpaw-gateway.js').includes('runtime_agent_execution')],
  ['QwenPaw 订单工具', read('qwenpaw-enterprise/plugins/zhiyun-brand/backend/main.py').includes('enterprise_query_orders')],
  ['QwenPaw 库存工具', read('qwenpaw-enterprise/plugins/zhiyun-brand/backend/main.py').includes('enterprise_query_inventory')],
  ['QwenPaw 客户工具', read('qwenpaw-enterprise/plugins/zhiyun-brand/backend/main.py').includes('enterprise_query_customers')],
  ['QwenPaw 知识工具', read('qwenpaw-enterprise/plugins/zhiyun-brand/backend/main.py').includes('enterprise_search_knowledge')],
]
for (const [name, ok] of checks) console.log(`${ok ? '✓' : '✗'} ${name}`)
if (checks.some(([, ok]) => !ok)) process.exit(1)
console.log(`Q2 验收通过：${checks.length}/${checks.length}`)
