import { spawnSync } from 'node:child_process'
import { accessSync, constants, existsSync, mkdirSync, readFileSync } from 'node:fs'
import net from 'node:net'
import { dirname, join } from 'node:path'
import { pawappsAllMaterialized } from './pawapp-materialized.mjs'
import { fileURLToPath } from 'node:url'
import { resolveRuntime, runtimeEnvironment } from './runtime-env.mjs'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const runtimeRoot = join(appRoot, 'runtime')
const lockPath = join(appRoot, 'pawapps.lock.json')
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

// Git 只在需要在线拉取 PawApp 时才是必需的（QwenPaw 官方安装本体是 pip 包，
// 不依赖 git）。U 盘离线包随身携带全部锁定 PawApp，此时缺 git 只降级为提醒。
const git = command('git', ['--version'])
const gitOptional = pawappsAllMaterialized(appRoot)
record(
  'git',
  git.ok ? 'pass' : (gitOptional ? 'warn' : 'fail'),
  git.output || git.error || '未找到 Git',
  gitOptional
    ? '锁定 PawApp 已全部就绪，无需 Git；仅在线拉取应用更新时才需要。'
    : '请安装 Git 并确保 git 在 PATH 中。',
)

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

try {
  const lockCheck = command(process.execPath, [join(appRoot, 'scripts', 'sync-pawapps.mjs'), '--check'])
  record('pawapps-lock', lockCheck.ok ? 'pass' : 'fail', lockCheck.output || 'PawApp 锁文件检查失败', '修复 apps/zhizaoyunAIOS/pawapps.lock.json。')
  const lock = JSON.parse(readFileSync(lockPath, 'utf8'))
  const missing = lock.apps.filter(app => !existsSync(join(runtimeRoot, 'pawapps', app.install_dir, 'plugin.json')))
  record('pawapps', missing.length ? 'warn' : 'pass', missing.length ? `${missing.length} 个外部 PawApp 尚未同步：${missing.map(app => app.id).join('、')}` : `${lock.apps.length} 个外部 PawApp 已落盘`, '首次启动会自动同步；若失败，请检查 GitHub 网络访问。')
} catch (error) {
  if (!checks.some(item => item.id === 'pawapps-lock')) record('pawapps-lock', 'fail', `无法读取 PawApp 锁文件：${error.message}`, '修复 apps/zhizaoyunAIOS/pawapps.lock.json。')
}

const portInUse = await checkPort(8088)
record('port-8088', portInUse ? 'fail' : 'pass', portInUse ? '127.0.0.1:8088 已有服务监听；为避免重复实例和插件文件冲突，本次启动已停止' : '127.0.0.1:8088 可用于启动', '先访问页面确认是否为旧 AI-OS；需要升级或重启时，请先停止旧进程再运行启动脚本。')

const failed = checks.filter(item => item.status === 'fail')
const warned = checks.filter(item => item.status === 'warn')
if (jsonOutput) {
  console.log(JSON.stringify({ ok: failed.length === 0, failed: failed.length, warned: warned.length, checks }, null, 2))
} else {
  const icons = { pass: '✅', warn: '⚠️', fail: '❌' }
  console.log('AI-OS 启动诊断')
  for (const item of checks) {
    console.log(`${icons[item.status]} ${item.id}: ${item.message}`)
    if (item.status !== 'pass' && item.remedy) console.log(`   处理：${item.remedy}`)
  }
  console.log(`\n诊断结果：${failed.length} 个失败，${warned.length} 个提醒。`)
}
process.exitCode = failed.length ? 1 : 0
