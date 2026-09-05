import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { delimiter, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const lockPath = join(appRoot, 'qwenpaw.lock.json')

export function runtimeLock () {
  const lock = JSON.parse(readFileSync(lockPath, 'utf8'))
  if (lock.schema_version !== 1 || lock.package !== 'qwenpaw' || !/^\d+\.\d+\.\d+(b\d+)?$/.test(lock.version)) {
    throw new Error('qwenpaw.lock.json 缺少有效的 schema_version、package 或 version')
  }
  if (!/^[0-9a-f]{40}$/.test(lock.commit)) throw new Error('QwenPaw 必须锁定完整 Commit SHA')
  return lock
}

export function projectRuntimeRoot (lock = runtimeLock()) {
  return resolve(appRoot, lock.runtime_dir)
}

export function runtimeCandidates (root, platform) {
  if (platform === 'win32') {
    return [
      { command: join(root, 'venv', 'Scripts', 'qwenpaw.exe'), python: join(root, 'venv', 'Scripts', 'python.exe'), layout: 'managed' },
      { command: join(root, 'Scripts', 'qwenpaw.exe'), python: join(root, 'Scripts', 'python.exe'), layout: 'venv' },
    ]
  }
  return [
    { command: join(root, 'venv', 'bin', 'qwenpaw'), python: join(root, 'venv', 'bin', 'python'), layout: 'managed' },
    { command: join(root, 'bin', 'qwenpaw'), python: join(root, 'bin', 'python'), layout: 'venv' },
  ]
}

function versionOf (command, cwd, env = process.env) {
  const result = spawnSync(command, ['--version'], { cwd, env, encoding: 'utf8', stdio: 'pipe', shell: false })
  return {
    ok: !result.error && result.status === 0,
    output: `${result.stdout || ''}${result.stderr || ''}`.trim(),
    error: result.error?.message || '',
  }
}

export function matchesVersion (output, expected) {
  const numericExpected = expected.replace(/b\d+$/, '')
  const match = String(output).match(/(?:version\s+|v)(\d+\.\d+\.\d+)/i)
  return match?.[1] === numericExpected
}

export function resolveRuntime ({
  env = process.env,
  platform = process.platform,
  allowGlobal = true,
  root: rootOverride,
  exists = existsSync,
  probe = versionOf,
} = {}) {
  const lock = runtimeLock()
  const root = rootOverride || projectRuntimeRoot(lock)
  for (const candidate of runtimeCandidates(root, platform)) {
    if (!exists(candidate.command) || !exists(candidate.python)) continue
    const result = probe(candidate.command, appRoot, {
      ...env,
      QWENPAW_HOME: join(appRoot, 'workspace'),
      QWENPAW_WORKING_DIR: join(appRoot, 'workspace'),
    })
    if (result.ok && matchesVersion(result.output, lock.version)) {
      return { ...candidate, root, source: 'project', version: lock.version, output: result.output, lock }
    }
  }

  if (allowGlobal) {
    const result = probe('qwenpaw', appRoot, env)
    if (result.ok && matchesVersion(result.output, lock.version)) {
      return {
        command: 'qwenpaw',
        python: env.PYTHON || (platform === 'win32' ? 'python' : 'python3'),
        root: null,
        source: 'global',
        version: lock.version,
        output: result.output,
        lock,
      }
    }
  }

  return {
    command: null,
    python: null,
    root,
    source: 'missing',
    version: lock.version,
    output: `未找到 QwenPaw ${lock.version}`,
    remedy: platform === 'win32' ? '.\\setup-ai-os.ps1' : './setup-ai-os.sh',
    lock,
  }
}

export function runtimeEnvironment (runtime, env = process.env) {
  if (!runtime.command) return { ...env }
  const commandDir = runtime.command === 'qwenpaw' ? null : dirname(runtime.command)
  return {
    ...env,
    ...(runtime.python ? { PYTHON: runtime.python } : {}),
    ...(runtime.root ? {
      QWENPAW_PROJECT_RUNTIME: runtime.root,
      QWENPAW_HOME: join(appRoot, 'workspace'),
      QWENPAW_WORKING_DIR: join(appRoot, 'workspace'),
    } : {}),
    PATH: commandDir ? `${commandDir}${delimiter}${env.PATH || ''}` : (env.PATH || ''),
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const runtime = resolveRuntime()
  if (process.argv.includes('--json')) console.log(JSON.stringify(runtime, null, 2))
  else if (runtime.command) console.log(`${runtime.command}\n${runtime.python || ''}`)
  else console.error(`${runtime.output}；运行 ${runtime.remedy}`)
  process.exitCode = runtime.command ? 0 : 1
}
