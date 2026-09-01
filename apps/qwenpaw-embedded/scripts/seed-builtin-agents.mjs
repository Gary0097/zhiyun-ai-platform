// 内置智能体种子：把仓库 agent-seeds/ 下的官方数字员工装进工作区（幂等）。
// 首次启动时创建 workspaces/<id>/（agent.json + 提示词 + 技能 + 知识 + 记忆）
// 并在 config.json 的 agents.profiles 注册；已存在则整份跳过，绝不覆盖用户修改。
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = process.env.AI_OS_EMBEDDED_ROOT
  ? resolve(process.env.AI_OS_EMBEDDED_ROOT)
  : join(dirname(fileURLToPath(import.meta.url)), '..')
// 业务数字员工种子由 zhiyun-enterprise-seeder 系统插件持有（版本随 plugin.json），
// 本脚本只负责把它装进工作区，不拥有业务内容本身。
const seedsRoot = join(appRoot, '..', '..', 'plugins', 'zhiyun-enterprise-seeder', 'agent_seeds')
const workspacesRoot = join(appRoot, 'workspace', 'workspaces')
const configFile = join(appRoot, 'workspace', 'config.json')

if (!existsSync(seedsRoot)) {
  console.log('内置智能体种子：无种子目录，跳过。')
  process.exit(0)
}

let config = existsSync(configFile)
  ? JSON.parse(readFileSync(configFile, 'utf8'))
  : { agents: { active_agent: 'default', agent_order: ['default'], profiles: {} } }
config.agents ??= {}
config.agents.profiles ??= {}
config.agents.agent_order ??= []

let changed = false
for (const entry of readdirSync(seedsRoot, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue
  const seedDir = join(seedsRoot, entry.name)
  const manifest = join(seedDir, 'agent.json')
  if (!existsSync(manifest)) continue
  const agent = JSON.parse(readFileSync(manifest, 'utf8'))
  const id = agent.id
  if (!id || !/^[a-z0-9][a-z0-9_+-]*$/.test(id)) {
    console.warn(`内置智能体种子 ${entry.name}：id 非法，跳过。`)
    continue
  }
  const target = join(workspacesRoot, id)
  if (existsSync(join(target, 'agent.json'))) {
    console.log(`内置智能体已就绪：${agent.name}（${id}）`)
    continue
  }

  mkdirSync(target, { recursive: true })
  // agent.json 是“种子完成”标记（上方的就绪检查以它为准），必须最后写入：
  // 中途中断时目录不完整，下次启动会重新安装而不是带着残缺跳过。
  for (const f of ['AGENTS.md', 'PROFILE.md', 'SOUL.md', 'skill.json']) {
    const src = join(seedDir, f)
    if (existsSync(src)) cpSync(src, join(target, f))
  }
  for (const part of ['skills', 'files', 'memory']) {
    const src = join(seedDir, part)
    if (existsSync(src)) cpSync(src, join(target, part), { recursive: true })
  }
  // 基础运行目录（与官方 _initialize_agent_workspace 对齐）
  for (const d of ['sessions', 'checkpoints']) mkdirSync(join(target, d), { recursive: true })
  const jobs = join(target, 'jobs.json')
  if (!existsSync(jobs)) writeFileSync(jobs, JSON.stringify({ version: 1, jobs: [] }, null, 2), 'utf8')

  agent.workspace_dir = target
  writeFileSync(join(target, 'agent.json'), JSON.stringify(agent, null, 2), 'utf8') // 完成标记
  if (!config.agents.profiles[id]) {
    config.agents.profiles[id] = {
      id,
      name: agent.name,
      description: agent.description || '',
      workspace_dir: target,
      enabled: true,
      pinned: false,
    }
    if (!config.agents.agent_order.includes(id)) config.agents.agent_order.push(id)
    changed = true
  }
  console.log(`内置智能体已安装：${agent.name}（${id}）`)
}

if (changed) writeFileSync(configFile, JSON.stringify(config, null, 2), 'utf8')
