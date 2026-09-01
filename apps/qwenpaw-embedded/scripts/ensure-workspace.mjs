// 确保 Workspace 目录结构在插件加载前就绪（fresh install 修复）
// 缺少这些目录时 zhiyun-auth / data-core / enterprise-seeder / branding
// 等插件会在首次启动时崩溃，返回 Internal Server Error。
import { mkdirSync, existsSync, writeFileSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const appRoot = join(scriptsRoot, '..')
const workspace = join(appRoot, 'workspace')

const dirs = [
  'auth',
  'branding',
  'enterprise',
  'workspace/data-core',
  'workspaces/default/logs',
  'workspaces/default/sessions/console',
  'workspaces/default/data',
  'workspaces/default/files',
  'workspaces/default/knowledge',
  'governance',
  'plugin_runtime/install-locks',
  'skill_pool',
]

for (const dir of dirs) {
  const full = join(workspace, dir)
  if (!existsSync(full)) {
    mkdirSync(full, { recursive: true })
    console.log(`  [init] ${dir}/`)
  }
}

// 确保 auth/users.json 存在（空数组也行，zhiyun-auth 插件的 _ensure_admin 会填充 admin）
const usersFile = join(workspace, 'auth', 'users.json')
if (!existsSync(usersFile)) {
  writeFileSync(usersFile, '[]\n', 'utf8')
  console.log('  [init] auth/users.json')
}

// 确保 auth/token_secret.txt 有初始值（后续 zhiyun-auth 会自动生成/覆盖）
const secretFile = join(workspace, 'auth', 'token_secret.txt')
if (!existsSync(secretFile)) {
  const { randomBytes } = await import('node:crypto')
  writeFileSync(secretFile, randomBytes(32).toString('hex') + '\n', 'utf8')
  console.log('  [init] auth/token_secret.txt')
}

// 确保 branding/login-config.json 存在（默认值）
const brandingFile = join(workspace, 'branding', 'login-config.json')
if (!existsSync(brandingFile)) {
  writeFileSync(brandingFile, JSON.stringify({
    brand_name: '灵泽万川智造云',
    enterprise: '灵泽万川智造云',
    background_image: '',
    background_data_url: ''
  }, null, 2) + '\n', 'utf8')
  console.log('  [init] branding/login-config.json')
}

console.log('Workspace 目录结构已就绪。')
