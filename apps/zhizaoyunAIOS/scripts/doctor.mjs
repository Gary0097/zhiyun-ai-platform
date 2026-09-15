import { spawnSync } from 'node:child_process'
import { accessSync, constants, mkdirSync } from 'node:fs'
import net from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveRuntime, runtimeEnvironment } from './runtime-env.mjs'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const runtimeRoot = join(appRoot, 'runtime')
const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const jsonOutput = process.argv.includes('--json')
const checks = []
const runtime = resolveRuntime()
const runtimeEnv = runtimeEnvironment(runtime)

function command (name, args = []) {
  const result = spawnSync(name, args, { cwd: repoRoot, encoding: 'utf8', stdio: 'pipe', env: runtimeEnv })
  return {
    ok: !result.error && result.status === 0,
    output: `${result.stdout || ''}${result.stderr || ''}`.trim(),
    error: result.error?.message || ''
  }
}

function record (id, status, message, remedy = '') {
  checks.push({ id, status, message, remedy })
}

function checkPort (port) {
  return new Promise(resolve => {
    const socket = net.createConnection({ host: '127.0.0.1', port })
    socket.setTimeout(700)
    socket.once('connect', () => { socket.destroy(); resolve(true) })
    socket.once('timeout', () => { socket.destroy(); resolve(false) })
    socket.once('error', () => resolve(false))
  })
}

const nodeMajor = Number(process.versions.node.split('.')[0])
record('node', nodeMajor >= 18 ? 'pass' : 'fail', `Node.js ${process.versions.node}`, '请安装 Node.js 18 或更高版本。')

// Git 不再是启动必需（2.2.0 起无捆绑 PawApp，QwenPaw 安装本体是 pip 包）
const git = command('git', ['--version'])
record('git', git.ok ? 'pass' : 'warn', git.output || git.error || '未找到 Git', '仅开发者工作流需要 Git。')

const qwenpaw = runtime.command ? command(runtime.command, ['--version']) : { ok: false, output: runtime.output, error: '' }
record(
  'qwenpaw-cli',
  qwenpaw.ok && qwenpaw.output.includes(runtime.version) ? 'pass' : 'fail',
  runtime.command ? `${qwenpaw.output}（${runtime.source === 'project' ? `项目运行环境 ${runtime.root}` : '全局安装'}）` : runtime.output,
  `运行 ${runtime.remedy || (process.platform === 'win32' ? '.\\setup-ai-os.ps1' : './setup-ai-os.sh')} 安装项目运行环境。`,
)

const selectedPython = runtime.python || python
const pythonImport = command(selectedPython, ['-c', 'import qwenpaw; print(qwenpaw.__file__)'])
record('python-runtime', pythonImport.ok ? 'pass' : (qwenpaw.ok ? 'warn' : 'fail'), pythonImport.ok ? `${selectedPython} 可导入 qwenpaw` : (qwenpaw.ok ? 'QwenPaw Desktop/CLI 可用，独立 Python 包不可用（不阻断启动）' : (pythonImport.output || pythonImport.error)), 'CLI 可用时无需处理；源码安装模式请设置 PYTHON 为安装了 QwenPaw 的解释器。')

try {
  for (const dir of [runtimeRoot, join(appRoot, 'workspace')]) {
    mkdirSync(dir, { recursive: true })
    accessSync(dir, constants.R_OK | constants.W_OK)
  }
  record('directories', 'pass', '运行目录和工作区可读写')
} catch (error) {
  record('directories', 'fail', error.message, '修复仓库目录权限后重试。')
}

const portInUse = await checkPort(8088)
record('port-8088', portInUse ? 'fail' : 'pass', portInUse ? '127.0.0.1:8088 已有外来服务监听（本平台旧实例已在启动前被自动接管）' : '127.0.0.1:8088 可用于启动', '8088 被 non-AI-OS 进程占用：请确认该端口用途后释放，或修改占用服务的端口。')

const failed = checks.filter(item => item.status === 'fail')
const warned = checks.filter(item => item.status === 'warn')
if (jsonOutput) {
  console.log(JSON.stringify({ ok: failed.length === 0, failed: failed.length, warned: warned.length, checks }, null, 2))
} else {
  const icons = { pass: '✅', warn: '⚠️', fail: '❌' }
  console.log('智造云 AIOS 启动诊断')
  for (const item of checks) {
    console.log(`${icons[item.status]} ${item.id}: ${item.message}`)
    if (item.status !== 'pass' && item.remedy) console.log(`   处理：${item.remedy}`)
  }
  console.log(`\n诊断结果：${failed.length} 个失败，${warned.length} 个提醒。`)
}
process.exitCode = failed.length ? 1 : 0
