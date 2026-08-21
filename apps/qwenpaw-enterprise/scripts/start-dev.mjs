import { spawn, spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomBytes } from 'node:crypto'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const enterprise = join(root, '..', 'enterprise')
const plugin = join(root, 'plugins', 'zhiyun-brand')
const checkOnly = process.argv.includes('--check')
const gatewaySecret = process.env.ZHIYUN_GATEWAY_SECRET || randomBytes(32).toString('hex')
const qwenpawIdentity = process.env.ZHIYUN_QWENPAW_IDENTITY || 'local-admin'
const qwenpawUsername = process.env.ZHIYUN_QWENPAW_USERNAME || 'admin.a'

function requireCommand (command, args, hint) {
  const result = spawnSync(command, args, { encoding: 'utf8' })
  if (result.status !== 0) {
    console.error(hint)
    if (result.stderr) console.error(result.stderr.trim())
    process.exit(1)
  }
  return (result.stdout || result.stderr || '').trim()
}

const nodeVersion = requireCommand(process.execPath, ['--version'], '需要 Node.js 24 或更高版本')
const qwenpawVersion = requireCommand('qwenpaw', ['--version'], '未检测到 QwenPaw。请先执行：pip install qwenpaw==2.1.0')
if (!qwenpawVersion.includes('2.1.0')) {
  console.error(`QwenPaw 版本不匹配：${qwenpawVersion}；本项目锁定 2.1.0`)
  process.exit(1)
}
console.log(`运行环境检查通过：Node ${nodeVersion}；${qwenpawVersion}`)
if (checkOnly) process.exit(0)

const installed = spawnSync('qwenpaw', ['plugin', 'install', plugin, '--force'], {
  stdio: 'inherit',
})
if (installed.status !== 0) process.exit(installed.status || 1)

const children = [
  spawn(process.execPath, ['start.mjs'], {
    cwd: enterprise,
    stdio: 'inherit',
    env: { ...process.env, PORT: process.env.ENTERPRISE_PORT || '8390', ZHIYUN_GATEWAY_SECRET: gatewaySecret, ZHIYUN_QWENPAW_IDENTITY: qwenpawIdentity, ZHIYUN_QWENPAW_USERNAME: qwenpawUsername },
  }),
  spawn('qwenpaw', ['app'], {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      ZHIYUN_ENTERPRISE_URL: process.env.ZHIYUN_ENTERPRISE_URL || 'http://127.0.0.1:8390',
      ZHIYUN_GATEWAY_SECRET: gatewaySecret,
      ZHIYUN_QWENPAW_IDENTITY: qwenpawIdentity,
    },
  }),
]

let stopping = false
function stop (signal) {
  if (stopping) return
  stopping = true
  for (const child of children) {
    if (!child.killed) child.kill(signal)
  }
}
process.on('SIGINT', () => stop('SIGINT'))
process.on('SIGTERM', () => stop('SIGTERM'))

for (const child of children) {
  child.on('exit', (code) => {
    if (!stopping) {
      console.error(`子服务异常退出（code=${code ?? 'unknown'}），正在停止另一服务`)
      stop('SIGTERM')
      process.exitCode = code || 1
    }
  })
}

console.log('智造云 AI-OS 开发环境启动中：QwenPaw http://127.0.0.1:8088 · 企业服务 http://127.0.0.1:8390')
