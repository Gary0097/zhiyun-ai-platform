import { spawn, spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const scriptsRoot = join(appRoot, 'scripts')
const auditPlugin = join(repoRoot, 'plugins', 'zhiyun-audit')
const logoPlugin = join(repoRoot, 'plugins', 'zhiyun-logo')
const appDiscoveryPlugin = join(repoRoot, 'plugins', 'zhiyun-app-discovery')
const dataCorePlugin = join(repoRoot, 'plugins', 'zhiyun-data-core')
const dataStudioPlugin = join(appRoot, 'runtime', 'pawapps', 'zhiyun-data-studio')

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

run(process.execPath, [join(scriptsRoot, 'doctor.mjs')], '启动诊断未通过；请按上方提示处理后重试。')
if (process.argv.includes('--check')) process.exit(0)

run(python, [join(scriptsRoot, 'cleanup-legacy.py')], '清理旧品牌、应用和企业 Tool 配置失败。')
run('qwenpaw', ['plugin', 'install', auditPlugin, '--force'], '日志审计插件安装失败。')
run('qwenpaw', ['plugin', 'install', logoPlugin, '--force'], 'Logo 配置插件安装失败。')
run('qwenpaw', ['plugin', 'install', appDiscoveryPlugin, '--force'], '应用发现插件安装失败。')
run('qwenpaw', ['plugin', 'install', dataCorePlugin, '--force'], 'Data Core 插件安装失败。')
run(process.execPath, [join(scriptsRoot, 'sync-pawapps.mjs')], '外部 PawApp 同步失败。')
run('qwenpaw', ['plugin', 'install', dataStudioPlugin, '--force'], 'Data Studio 应用安装失败。')

console.log('\nAI-OS 启动中：http://127.0.0.1:8088')
console.log('运行形态：原生 QwenPaw 单进程；启用 Logo、日志审计、应用发现、Data Core 和 Data Studio；不启动企业服务。\n')
const child = spawn('qwenpaw', ['app'], { cwd: repoRoot, stdio: 'inherit', env: process.env })
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
child.on('exit', code => { process.exitCode = code || 0 })
