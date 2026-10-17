// 办公技能包依赖预装测试（aios-office 分支）
// 覆盖：requirements 解析/哈希、venv 解释器解析（双平台布局）、
// 标记快路径、探测命令、ensure-workspace 挂接、CLI --check。
// 真实安装路径不在此模拟（无 venv 的临时目录返回 no-runtime 跳过），
// 由本机完整启动做端到端验证。
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const scriptsRoot = fileURLToPath(new URL('.', import.meta.url))
const repoRoot = join(scriptsRoot, '..', '..', '..')
const packRoot = join(repoRoot, 'skills', 'office')
const { parseRequirements, requirementsHash, resolveVenvPython, ensureOfficeDependencies, environmentFingerprint, probeOfficeDependencies, officeDependencySpec } =
  await import(pathToFileURL(join(scriptsRoot, 'ensure-office-deps.mjs')).href)

const temp = mkdtempSync(join(tmpdir(), 'aios-office-deps-'))
const quiet = () => {}
try {
  // ---------- 1) requirements 解析与哈希 ----------
  const reqText = readFileSync(join(packRoot, 'requirements-office.txt'), 'utf8')
  const markerHash = officeDependencySpec(packRoot).hash
  const entries = parseRequirements(reqText)
  assert.ok(entries.length >= 10, '依赖清单应包含核心办公包')
  assert.ok(entries.some(e => e.name === 'python-docx'), '应包含 python-docx')
  assert.ok(entries.some(e => e.name === 'rapidocr-onnxruntime'), '应包含本地 OCR 包')
  // 注释变化不影响哈希；依赖集合变化影响哈希
  const h1 = requirementsHash(reqText)
  const h2 = requirementsHash(reqText.replace(/^#.*$/gm, '# 注释变化'))
  const h3 = requirementsHash(reqText + '\nnew-package>=1.0\n')
  assert.equal(h1, h2, '注释变化不应触发重装')
  assert.notEqual(h1, h3, '新增依赖必须触发重装')

  // ---------- 2) venv 解释器解析（路径拼接规则随平台） ----------
  {
    const appRoot = join(temp, 'app-probe')
    mkdirSync(join(appRoot, 'runtime', 'zhizaoyunAIOS'), { recursive: true })
    writeFileSync(join(appRoot, 'qwenpaw.lock.json'), JSON.stringify({ runtime_dir: 'runtime/zhizaoyunAIOS' }))
    const { python } = resolveVenvPython(appRoot)
    const layout = process.platform === 'win32' ? ['venv', 'Scripts', 'python.exe'] : ['venv', 'bin', 'python']
    assert.ok(python.endsWith(join(appRoot, 'runtime', 'zhizaoyunAIOS', ...layout)),
      'venv 解释器路径必须依据 lock 的 runtime_dir 与平台布局解析')
  }

  // ---------- 3) 无 venv：优雅跳过（no-runtime） ----------
  const bareRoot = join(temp, 'bare-app')
  mkdirSync(join(bareRoot, 'runtime', 'zhizaoyunAIOS'), { recursive: true })
  writeFileSync(join(bareRoot, 'qwenpaw.lock.json'), JSON.stringify({ runtime_dir: 'zhizaoyunAIOS' }))
  const result = ensureOfficeDependencies({ appRoot: bareRoot, packRoot, log: quiet })
  assert.equal(result.status, 'no-runtime', '运行环境缺失时必须跳过而不是报错')

  // requirements 缺失：skipped
  const noReqRoot = join(temp, 'no-req-app')
  mkdirSync(noReqRoot, { recursive: true })
  assert.equal(ensureOfficeDependencies({ appRoot: noReqRoot, packRoot: join(temp, 'no-such-pack'), log: quiet }).status, 'skipped')

  // ---------- 4) 标记快路径：有效标记直接 up-to-date（不触碰 python） ----------
  // Hermetic fake environment: tests must never touch the installed runtime marker.
  const realAppRoot = join(temp, 'marker-app')
  mkdirSync(realAppRoot, { recursive: true })
  writeFileSync(join(realAppRoot, 'qwenpaw.lock.json'), JSON.stringify({ runtime_dir: 'runtime/test' }))
  const { runtimeRoot } = resolveVenvPython(realAppRoot)
  const { python: markerPython } = resolveVenvPython(realAppRoot)
  mkdirSync(join(markerPython, '..'), { recursive: true })
  writeFileSync(markerPython, 'fake-python')
  const markerPath = join(runtimeRoot, 'office-deps.ok')
  let existedMarker = null
  try { existedMarker = readFileSync(markerPath, 'utf8') } catch { /* 首次运行无标记 */ }
  try {
    writeFileSync(markerPath, JSON.stringify({ hash: markerHash, environment: environmentFingerprint(markerPython) }) + '\n', 'utf8')
    assert.equal(ensureOfficeDependencies({ appRoot: realAppRoot, packRoot, log: quiet }).status, 'up-to-date')
    writeFileSync(markerPath, JSON.stringify({ hash: markerHash }))
    assert.equal(ensureOfficeDependencies({ appRoot: realAppRoot, packRoot, log: quiet }).status, 'probe-failed', '旧标记不能绕过环境复验')
    // 哈希不匹配的标记无效 → 必须重新探测。用 venv 自带依赖构造临时清单，
    // 避免测试触发真实下载安装（无 venv 环境则返回 no-runtime，同样合法）。
    const stubPack = join(temp, 'stub-pack')
    mkdirSync(stubPack, { recursive: true })
    writeFileSync(join(stubPack, 'requirements-office.txt'), 'pydantic>=2\npyyaml>=6\n')
    writeFileSync(markerPath, JSON.stringify({ hash: 'stale' }) + '\n', 'utf8')
    const recheck = ensureOfficeDependencies({ appRoot: realAppRoot, packRoot: stubPack, log: quiet })
    assert.equal(recheck.status, 'probe-failed', '过期标记必须探测，假解释器不能成功')
    writeFileSync(markerPath, JSON.stringify({ hash: markerHash, environment: environmentFingerprint(markerPython) }))
    writeFileSync(markerPython, 'rebuilt-python-environment')
    assert.equal(ensureOfficeDependencies({ appRoot: realAppRoot, packRoot, log: quiet, allowInstall: false }).status, 'repair-required', '启动阶段禁止启动损坏的解释器或下载安装')
    assert.equal(ensureOfficeDependencies({ appRoot: realAppRoot, packRoot, log: quiet }).status, 'probe-failed')
    rmSync(markerPython)
    assert.equal(ensureOfficeDependencies({ appRoot: realAppRoot, packRoot, log: quiet }).status, 'no-runtime')
  } finally {
    // 还原真实标记（后续端到端启动还会用到）
    if (existedMarker !== null) writeFileSync(markerPath, existedMarker, 'utf8')
    else rmSync(markerPath, { force: true })
  }

  // Optional real interpreter regression: module presence must not hide an old version.
  if (process.env.OFFICE_TEST_PYTHON) {
    const probe = probeOfficeDependencies(process.env.OFFICE_TEST_PYTHON, parseRequirements('python-docx>=999\nopenpyxl>=3.1\n'))
    assert.equal(probe.status, 0, probe.stderr)
    assert.deepEqual(JSON.parse(probe.stdout), ['python-docx>=999'])
  }

  // ---------- 5) ensure-workspace 挂接与 CLI --check ----------
  const ensureSrc = readFileSync(join(scriptsRoot, 'ensure-workspace.mjs'), 'utf8')
  assert.ok(ensureSrc.includes('ensure-office-deps'), 'ensure-workspace.mjs must hook office deps preinstall')
  const check = spawnSync(process.execPath, [join(scriptsRoot, 'ensure-office-deps.mjs'), '--check'], { encoding: 'utf8' })
  assert.equal(check.status, 0, check.stderr || 'ensure-office-deps --check 必须通过')

  console.log('办公依赖预装测试通过：清单解析/哈希稳定性/venv 解析/无环境跳过/标记快路径/启动挂接/CLI 校验。')
} finally {
  assert.ok(temp.includes(join('aios-office-deps-')))
  rmSync(temp, { recursive: true, force: true })
}
