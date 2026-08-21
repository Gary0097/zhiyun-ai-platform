import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const start = readFileSync(join(root, 'apps/qwenpaw-embedded/scripts/start.mjs'), 'utf8')
const cleanup = readFileSync(join(root, 'apps/qwenpaw-embedded/scripts/cleanup-legacy.py'), 'utf8')
const manifest = JSON.parse(readFileSync(join(root, 'plugins/zhiyun-audit/plugin.json'), 'utf8'))

function assert (condition, message) {
  if (!condition) throw new Error(message)
}

assert(start.includes("spawn('qwenpaw', ['app']"), '启动器必须只运行原生 qwenpaw app')
assert(start.includes('cleanup-legacy.py'), '启动器必须清理旧插件和 Tool')
assert(start.includes("'plugins', 'zhiyun-audit'"), '启动器必须安装日志审计插件')
assert(!start.includes('8390'), '默认启动器不得依赖 8390')
assert(!start.includes('zhiyun-brand'), '默认启动器不得安装品牌覆盖插件')
assert(!start.includes('zhiyun-orders'), '默认启动器不得安装业务应用')
assert(cleanup.includes('enterprise_platform_status'), '清理器必须移除 8390 状态 Tool')
assert(cleanup.includes('zhiyun-brand') && cleanup.includes('zhiyun-orders'), '清理器必须停用旧插件')
assert(manifest.entry.backend && !manifest.entry.frontend, '审计插件必须保持无界面')

console.log('S0 静态回归通过：原生 Logo、单进程 8088、无 8390、仅保留日志审计。')
