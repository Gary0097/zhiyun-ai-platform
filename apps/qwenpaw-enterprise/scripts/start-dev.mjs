import { spawn, spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const qwenRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(qwenRoot, '..', '..')
const brand = join(qwenRoot, 'plugins', 'zhiyun-brand')
const orders = join(repoRoot, 'pawapps', 'zhiyun-orders')
const checkOnly = process.argv.includes('--check')

function run (command, args, hint, capture = false) {
  const result = spawnSync(command, args, { cwd: repoRoot, encoding: capture ? 'utf8' : undefined, stdio: capture ? 'pipe' : 'inherit', env: process.env })
  if (result.status !== 0) {
    console.error(hint)
    if (capture && result.stderr) console.error(result.stderr.trim())
    process.exit(result.status || 1)
  }
  return capture ? (result.stdout || result.stderr || '').trim() : ''
}

const version = run('qwenpaw', ['--version'], '未检测到 QwenPaw 2.1.0', true)
if (!version.includes('2.1.0')) { console.error(`QwenPaw 版本不匹配：${version}`); process.exit(1) }
console.log(`运行环境检查通过：${version}`)
if (checkOnly) process.exit(0)

run('qwenpaw', ['plugin', 'install', brand, '--force'], '品牌 PawApp 安装失败')
run('qwenpaw', ['plugin', 'install', orders, '--force'], '订单 PawApp 安装失败')
run(process.env.PYTHON || 'python', [join(repoRoot, 'apps/qwenpaw-embedded/scripts/enable-r1-tools.py')], '订单 Tool 启用失败；请确认已经执行 qwenpaw init')

const child = spawn('qwenpaw', ['app'], { cwd: repoRoot, stdio: 'inherit', env: process.env })
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
child.on('exit', code => { process.exitCode = code || 0 })
console.log('智造云 AI-OS 启动中：http://127.0.0.1:8088（单一 QwenPaw 进程，无外部企业服务）')
