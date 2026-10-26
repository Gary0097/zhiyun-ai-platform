// Local attachment is explicit and contains paths only, never provider secrets.
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, copyFileSync } from 'node:fs'
import { join, resolve, dirname, delimiter } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawn } from 'node:child_process'
import net from 'node:net'
import { resolveRuntime, runtimeEnvironment, listenPort } from './runtime-env.mjs'
import { provisionOfficeSkills } from './provision-office-skills.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
export const profilePath = join(root, 'apps/zhizaoyunAIOS/runtime/local-instance.json')
export function readLocalProfile(path = profilePath) {
  if (!existsSync(path)) return null
  const p = JSON.parse(readFileSync(path, 'utf8'))
  if (p.schema_version !== 1 || !p.workspace || !p.secret_dir || !existsSync(join(p.workspace, 'config.json')) || !existsSync(p.secret_dir)) throw Error('本地接入配置无效，请恢复备份或重新接入。')
  return p
}
function copyTree(source, target) {
  mkdirSync(target, { recursive: true })
  for (const e of readdirSync(source, { withFileTypes: true })) {
    if (e.isSymbolicLink()) throw Error('不支持链接形式的品牌源文件')
    const a = join(source, e.name), b = join(target, e.name)
    if (e.isDirectory()) copyTree(a, b)
    else if (e.isFile()) copyFileSync(a, b)
  }
}
export function attachLocalInstance({ workspace, secretDir, localNoAuth = false }) {
  const profile = { schema_version: 1, workspace: resolve(workspace), secret_dir: resolve(secretDir), auth_enabled: !localNoAuth }
  if (localNoAuth && existsSync(join(profile.secret_dir, 'auth.json'))) throw Error('已有原生账号，不能切换为免登录。')
  if (!existsSync(join(profile.workspace, 'config.json')) || !existsSync(profile.secret_dir)) throw Error('接入必须指向已有工作区和凭据目录；不会新建或移动用户数据。')
  if (existsSync(profilePath)) {
    const old = readLocalProfile()
    if (old.workspace !== profile.workspace || old.secret_dir !== profile.secret_dir) throw Error('已接入其他工作区，请先备份并移开本地接入配置。')
  }
  const brandSource = join(root, 'plugins/aios-brand')
  const brandTarget = join(profile.workspace, 'plugins/aios-brand')
  // Only our named plugin is synchronized, not the user's other plugins.
  copyTree(brandSource, brandTarget)
  provisionOfficeSkills({ workspace: profile.workspace, packRoot: join(root, 'skills/office'), preservePrompts: true })
  mkdirSync(dirname(profilePath), { recursive: true })
  writeFileSync(profilePath, JSON.stringify(profile, null, 2) + '\n')
  console.log('本地接入完成：沿用现有工作区和凭据，保留原提示词、模型及智能体设置。')
  return profile
}
export async function startLocalInstance(profile = readLocalProfile()) {
  if (!profile) throw Error('尚未配置本地接入')
  if (profile.auth_enabled === false && existsSync(join(profile.secret_dir, 'auth.json'))) throw Error('检测到已有原生账号，请恢复登录模式。')
  const port = listenPort(process.env.AIOS_PORT)
  const busy = await new Promise(done => {
    const socket = net.createConnection({ host: '127.0.0.1', port })
    socket.setTimeout(500)
    socket.once('connect', () => { socket.destroy(); done(true) })
    socket.once('error', () => done(false))
    socket.once('timeout', () => { socket.destroy(); done(false) })
  })
  if (busy) throw Error(`端口 ${port} 已有服务。请先停止原实例；不会终止其他程序。`)
  const runtime = resolveRuntime({ allowGlobal: false })
  if (!runtime.command) throw Error(runtime.output)
  const env = runtimeEnvironment(runtime)
  Object.assign(env, {
    QWENPAW_HOME: profile.workspace, QWENPAW_WORKING_DIR: profile.workspace,
    QWENPAW_SECRET_DIR: profile.secret_dir, QWENPAW_AUTH_ENABLED: profile.auth_enabled === false ? 'false' : 'true',
    PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8',
    NODE_PATH: existsSync(join(root, 'extras/office-node/node_modules')) ? join(root, 'extras/office-node/node_modules') : join(root, 'apps/zhizaoyunAIOS/runtime/office-node/node_modules'),
    PATH: [join(root, 'extras/node'), env.PATH].join(delimiter),
  })
  // Existing native accounts are reused. Authentication remains enabled;
  // an originally unauthenticated installation registers its first account.
  console.log(`本地办公版启动：http://127.0.0.1:${port}；不安装、不下载、不重复预置。`)
  const child = spawn(runtime.python, ['-m', 'qwenpaw', 'app', '--host', '127.0.0.1', '--port', String(port)], { cwd: root, env, stdio: 'inherit' })
  process.on('SIGINT', () => child.kill('SIGINT'))
  process.on('SIGTERM', () => child.kill('SIGTERM'))
  return await new Promise((done, fail) => { child.once('error', fail); child.once('exit', code => done(code ?? 1)) })
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2), wi = args.indexOf('--workspace'), si = args.indexOf('--secret-dir')
    if (wi >= 0 && si >= 0) attachLocalInstance({ workspace: args[wi + 1], secretDir: args[si + 1], localNoAuth: args.includes('--local-no-auth') })
    else process.exitCode = await startLocalInstance()
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
