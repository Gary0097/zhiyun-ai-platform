// 停用旧架构和已确认不兼容的非 AI-OS 插件，并清理 Agent 遗留企业 Tool。
// 仅移动到 disabled_plugins，保留可恢复备份；不删除用户数据。
import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync } from 'node:fs'
import { join, normalize, resolve } from 'node:path'
import { homedir } from 'node:os'

function workingDir () {
  const explicit = process.env.QWENPAW_WORKING_DIR || process.env.COPAW_WORKING_DIR
  if (explicit) return resolve(explicit)
  const current = join(homedir(), '.qwenpaw')
  const legacy = join(homedir(), '.copaw')
  return !existsSync(current) && existsSync(legacy) ? legacy : current
}

const QWENPAW_HOME = workingDir()
const PLUGINS_DIR = join(QWENPAW_HOME, 'plugins')
const DISABLED_DIR = join(QWENPAW_HOME, 'disabled_plugins')
const LEGACY_PLUGINS = ['zhiyun-brand', 'zhiyun-orders']
// qwenpaw-creator 已于 2026-08-30 转为受控产品应用（视频压缩版，见 plugins/qwenpaw-creator），不再隔离
const INCOMPATIBLE_PLUGINS = ['cospaw', 'ai_decision', 'team_chat']
const LEGACY_TOOLS = [
  'enterprise_platform_status', 'enterprise_query_orders', 'enterprise_query_inventory',
  'enterprise_query_customers', 'enterprise_search_knowledge', 'orders_query', 'orders_delivery_risk',
]

mkdirSync(DISABLED_DIR, { recursive: true })
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)

function disablePlugin (pluginId, reason) {
  const source = join(PLUGINS_DIR, pluginId)
  if (!existsSync(source)) return
  const target = join(DISABLED_DIR, `${pluginId}-${stamp}`)
  renameSync(source, target)
  console.log(`已停用${reason}插件 ${pluginId}（可恢复备份：${target}）`)
}

for (const pluginId of LEGACY_PLUGINS) disablePlugin(pluginId, '旧架构')
for (const pluginId of INCOMPATIBLE_PLUGINS) disablePlugin(pluginId, '非 AI-OS 不兼容')

// 清理 Agent 遗留 Tool。
const configPath = join(QWENPAW_HOME, 'config.json')
if (!existsSync(configPath)) {
  console.log('未发现QwenPaw配置，跳过Agent遗留Tool清理（首次初始化后无需旧配置迁移）。')
  process.exit(0)
}
const rootConfig = JSON.parse(readFileSync(configPath, 'utf8'))
const profiles = (rootConfig.agents && rootConfig.agents.profiles) || {}
for (const [agentId, ref] of Object.entries(profiles)) {
  if (!ref || typeof ref.workspace_dir !== 'string') continue
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
