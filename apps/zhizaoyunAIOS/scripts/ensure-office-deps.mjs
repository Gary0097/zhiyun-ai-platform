// 智造云 AIOS 办公技能包依赖预装（aios-office 分支）
// 目的：把 skills/office/requirements-office.txt 的常用办公依赖
//（文档读写 / PDF / OCR）在启动期幂等安装到项目 venv，避免技能执行期
// 临时 pip install 浪费对话时间。
// 快路径：<runtime>/office-deps.ok 标记（记录 requirements 内容哈希）有效
// → 直接跳过（<50ms）；标记缺失/过期 → python find_spec 探测，全部满足则
// 只刷新标记；有缺失 → uv pip install 补装后复验。
// 失败只告警不阻断启动（技能内仍有按需安装的兜底文案）；离线包标记存在时
// 优先用 --offline 从本地缓存安装。
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const MARKER_NAME = 'office-deps.ok'

// requirements 中参与探测的 import 名（与包名不同的映射在此显式列出；
// 键与查找均按小写比较——pip 包名大小写不敏感，requirements 可能写 Pillow/pillow）
const IMPORT_NAMES = {
  'python-docx': 'docx',
  'python-pptx': 'pptx',
  'pyyaml': 'yaml',
  'pillow': 'PIL',
  'fpdf2': 'fpdf',
  'beautifulsoup4': 'bs4',
  'rapidocr-onnxruntime': 'rapidocr_onnxruntime',
}

function importNameFor (packageName) {
  return IMPORT_NAMES[packageName.toLowerCase()] || packageName.replace(/-/g, '_')
}

export function parseRequirements (text) {
  return text.split(/\r?\n/)
    .map(line => line.replace(/#.*$/, '').trim())
    .filter(line => line && !line.startsWith('-'))
    .map(line => {
      const name = line.split(/[><=!~;\s]/)[0]
      return { raw: line, name }
    })
    .filter(entry => entry.name)
}

export function requirementsHash (text) {
  // 注释行不参与哈希：只有实际依赖集合变化才触发重装
  const effective = text.split(/\r?\n/)
    .map(l => l.replace(/#.*$/, '').trim())
    .filter(Boolean)
    .sort()
    .join('\n')
  return createHash('sha256').update(effective).digest('hex')
}

// 项目 venv 解释器位置（依据 qwenpaw.lock.json 的 runtime_dir，双平台；
// runtime_dir 形如 "runtime/zhizaoyunAIOS"，已含 runtime 前缀，相对 appRoot）
export function resolveVenvPython (appRoot) {
  const lock = JSON.parse(readFileSync(join(appRoot, 'qwenpaw.lock.json'), 'utf8'))
  const runtimeRoot = join(appRoot, ...lock.runtime_dir.split('/'))
  const scripts = process.platform === 'win32'
    ? join(runtimeRoot, 'venv', 'Scripts', 'python.exe')
    : join(runtimeRoot, 'venv', 'bin', 'python')
  return { runtimeRoot, python: scripts }
}

export function ensureOfficeDependencies ({ appRoot, packRoot, log = console.log } = {}) {
  if (!appRoot || !packRoot) throw new Error('ensureOfficeDependencies 需要 appRoot 与 packRoot 参数')
  const reqPath = join(packRoot, 'requirements-office.txt')
  if (!existsSync(reqPath)) { log('  [office-deps] 未找到 requirements-office.txt，跳过依赖预装'); return { status: 'skipped' } }
  const reqText = readFileSync(reqPath, 'utf8')
  const requirements = parseRequirements(reqText)
  const hash = requirementsHash(reqText)
  const { runtimeRoot, python } = resolveVenvPython(appRoot)
  const marker = join(runtimeRoot, MARKER_NAME)

  const markerValid = () => {
    try { return JSON.parse(readFileSync(marker, 'utf8')).hash === hash }
    catch { return false }
  }
  if (markerValid()) return { status: 'up-to-date' }

  if (!existsSync(python)) {
    log('  [office-deps] 项目运行环境未安装（' + python + '），跳过依赖预装；首次 setup 后下次启动自动补装')
    return { status: 'no-runtime' }
  }

  // 探测缺失包（find_spec 只定位不导入，秒级完成）
  const importList = requirements.map(r => importNameFor(r.name))
  const probe = spawnSync(python, ['-c',
    'from importlib.util import find_spec\nimport sys\nmissing=[m for m in sys.argv[1:] if not find_spec(m)]\nprint(",".join(missing))',
    ...importList], { encoding: 'utf8', timeout: 120000 })
  if (probe.status !== 0) {
    log('  [office-deps] 依赖探测失败（' + (probe.stderr || '').trim().slice(0, 120) + '），跳过；技能执行期可自行兜底安装')
    return { status: 'probe-failed' }
  }
  const missing = (probe.stdout || '').trim().split(',').filter(Boolean)
  if (!missing.length) {
    writeFileSync(marker, JSON.stringify({ hash, checkedAt: new Date().toISOString() }) + '\n', 'utf8')
    return { status: 'satisfied' }
  }

  // 补装：优先用项目缓存里的 uv（setup 时落盘），其次 PATH 中的 uv/pip
  const cachedUv = join(appRoot, 'runtime', 'cache', 'bin', process.platform === 'win32' ? 'uv.exe' : 'uv')
  const offlineMode = existsSync(join(appRoot, 'runtime', 'cache', 'OFFLINE-PACKAGE'))
  log(`  [office-deps] 检测到缺失依赖 ${missing.length} 项，开始预装（一次性，约 1-3 分钟）…`)
  let install
  if (existsSync(cachedUv)) {
    const args = ['pip', 'install', '--python', python, '-r', reqPath]
    if (offlineMode) args.push('--offline')
    install = spawnSync(cachedUv, args, { stdio: 'inherit', timeout: 10 * 60 * 1000 })
  } else {
    install = spawnSync(python, ['-m', 'pip', 'install', '-r', reqPath], { stdio: 'inherit', timeout: 10 * 60 * 1000 })
  }
  if (install.status !== 0) {
    log('  [office-deps] 依赖预装失败（不影响启动）；技能执行期会按需安装，或重跑 start-ai-os 重试')
    return { status: 'install-failed', missing }
  }
  // 复验：全部可导入才落标记
  const recheck = spawnSync(python, ['-c',
    'from importlib.util import find_spec\nimport sys\nsys.exit(0 if all(find_spec(m) for m in sys.argv[1:]) else 1)',
    ...importList], { encoding: 'utf8', timeout: 120000 })
  if (recheck.status !== 0) {
    log('  [office-deps] 安装后复验仍有缺失，未写入完成标记；下次启动将重试')
    return { status: 'recheck-failed' }
  }
  writeFileSync(marker, JSON.stringify({ hash, installedAt: new Date().toISOString() }) + '\n', 'utf8')
  log('  [office-deps] 办公依赖预装完成（docx/excel/ppt/pdf/OCR），技能执行无需临时安装')
  return { status: 'installed' }
}

// ---------- CLI ----------
// 用法：node ensure-office-deps.mjs [--app-root <dir>] [--pack-root <dir>] [--check]
// --check：只校验 requirements 与运行环境解析（发布门禁用），不安装。
const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  const args = process.argv.slice(2)
  const argValue = flag => {
    const i = args.indexOf(flag)
    return i >= 0 && args[i + 1] ? args[i + 1] : null
  }
  const scriptRoot = dirname(fileURLToPath(import.meta.url))
  const appRoot = argValue('--app-root') || join(scriptRoot, '..')
  const packRoot = argValue('--pack-root') || join(appRoot, '..', '..', 'skills', 'office')

  if (args.includes('--check')) {
    try {
      const reqText = readFileSync(join(packRoot, 'requirements-office.txt'), 'utf8')
      const entries = parseRequirements(reqText)
      if (!entries.length) throw new Error('requirements-office.txt 为空')
      for (const entry of entries) {
        const importName = importNameFor(entry.name)
        if (!/^[A-Za-z_][\w.-]*$/.test(importName)) throw new Error('非法依赖名：' + entry.raw)
      }
      const { python } = resolveVenvPython(appRoot)
      console.log(`办公依赖清单校验通过：${entries.length} 项，venv 解释器路径解析正常（${existsSync(python) ? '已安装' : '未安装，首次 setup 后生效'}）。`)
    } catch (e) {
      console.error('办公依赖清单校验失败：' + e.message)
      process.exit(1)
    }
  } else {
    ensureOfficeDependencies({ appRoot, packRoot })
  }
}
