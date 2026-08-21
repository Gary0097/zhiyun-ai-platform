import { spawn, spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const scriptsRoot = join(appRoot, 'scripts')
const auditPlugin = join(repoRoot, 'plugins', 'zhiyun-audit')
const logoPlugin = join(repoRoot, 'plugins', 'zhiyun-logo')
const checkOnly = process.argv.includes('--check')
const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')

function run (command, args, hint, capture = false) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: capture ? 'utf8' : undefined,
    stdio: capture ? 'pipe' : 'inherit',
    env: process.env
  })
  if (result.error || result.status !== 0) {
    console.error(`\n${hint}`)
    if (capture && result.stderr) console.error(result.stderr.trim())
    process.exit(result.status || 1)
  }
  return capture ? `${result.stdout || ''}${result.stderr || ''}`.trim() : ''
}

const version = run('qwenpaw', ['--version'], '未检测到 QwenPaw 2.1.0，请先按 README 安装。', true)
if (!version.includes('2.1.0')) {
  console.error(`QwenPaw 版本不匹配：${version}`)
  process.exit(1)
}
console.log(`环境检查通过：${version}`)
if (checkOnly) process.exit(0)

// 本机 qwenpaw 为 Desktop 打包 exe（无可 import 的 Python 包），故用 Node 等价实现清理。
run(process.execPath, [join(scriptsRoot, 'cleanup-legacy.mjs')], '清理旧品牌、应用和企业 Tool 配置失败。')
run('qwenpaw', ['plugin', 'install', auditPlugin, '--force'], '日志审计插件安装失败。')
run('qwenpaw', ['plugin', 'install', logoPlugin, '--force'], 'Logo 配置插件安装失败。')

console.log('\nAI-OS 启动中：http://127.0.0.1:8088')
console.log('运行形态：原生 QwenPaw 单进程；启用独立 Logo 配置；不启动企业服务或业务应用。\n')
const child = spawn('qwenpaw', ['app'], { cwd: repoRoot, stdio: 'inherit', env: process.env })
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
child.on('exit', code => { process.exitCode = code || 0 })
