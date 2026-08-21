// 停用旧品牌/应用插件，并清理 Agent 的遗留企业 Tool。
// 等价于 cleanup-legacy.py，但不依赖 qwenpaw Python 包（本机 qwenpaw 为 Desktop 打包 exe）。
import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync } from 'node:fs'
import { join, normalize } from 'node:path'
import { homedir } from 'node:os'

const QWENPAW_HOME = join(homedir(), '.qwenpaw')
const PLUGINS_DIR = join(QWENPAW_HOME, 'plugins')
const DISABLED_DIR = join(QWENPAW_HOME, 'disabled_plugins')
const LEGACY_PLUGINS = ['zhiyun-brand', 'zhiyun-orders']
const LEGACY_TOOLS = [
  'enterprise_platform_status', 'enterprise_query_orders', 'enterprise_query_inventory',
  'enterprise_query_customers', 'enterprise_search_knowledge', 'orders_query', 'orders_delivery_risk',
]

// 1. 停用旧插件（移动到 disabled_plugins）
mkdirSync(DISABLED_DIR, { recursive: true })
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
for (const pluginId of LEGACY_PLUGINS) {
  const source = join(PLUGINS_DIR, pluginId)
  if (existsSync(source)) {
    const target = join(DISABLED_DIR, `${pluginId}-${stamp}`)
    renameSync(source, target)
    console.log(`已停用旧插件 ${pluginId}（可恢复备份：${target}）`)
  }
}

// 2. 清理 Agent 遗留 Tool
const rootConfig = JSON.parse(readFileSync(join(QWENPAW_HOME, 'config.json'), 'utf8'))
const profiles = (rootConfig.agents && rootConfig.agents.profiles) || {}
for (const [agentId, ref] of Object.entries(profiles)) {
  const workspaceDir = normalize(ref.workspace_dir.replace(/\\/g, '/'))
  const agentPath = join(workspaceDir, 'agent.json')
  if (!existsSync(agentPath)) continue
  const agent = JSON.parse(readFileSync(agentPath, 'utf8'))
  const builtin = (agent.tools && agent.tools.builtin_tools) || {}
  const removed = []
  for (const name of LEGACY_TOOLS) {
    if (builtin[name]) { delete builtin[name]; removed.push(name) }
  }
  if (removed.length) {
    writeFileSync(agentPath, JSON.stringify(agent, null, 2) + '\n', 'utf8')
    console.log(`已清理 Agent ${agentId} 的遗留 Tool：${removed.join(', ')}`)
  }
}
console.log('cleanup 完成')
