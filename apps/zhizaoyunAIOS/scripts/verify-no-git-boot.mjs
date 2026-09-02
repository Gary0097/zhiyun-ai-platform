// 无 Git 环境启动回归测试：U 盘离线包的核心保障。
// 场景 A（PawApp 全部物化 + PATH 无 git）→ sync-pawapps 必须成功并提示跳过 bundle 缓存；
//      doctor 的 git 检查必须可降级（pawappsAllMaterialized 为 true）。
// 场景 B（PawApp 缺失 + PATH 无 git）→ git 属必需，pawappsAllMaterialized 必须为 false。
// 运行：node apps/zhizaoyunAIOS/scripts/verify-no-git-boot.mjs
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { pawappsAllMaterialized } from './pawapp-materialized.mjs'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))

// 受控 PATH：剔除一切含 git 的目录；若 git 仍藏在保留目录里
// （如 ubuntu runner 的 /usr/bin），降级为空目录 PATH——子进程只需要
// 绝对路径 node 与（不存在的）git，无需其他系统命令。
function gitlessPath () {
  const sep = process.platform === 'win32' ? ';' : ':'
  const keep = (process.env.PATH || '')
    .split(sep)
    .filter(entry => entry && !/git/i.test(entry))
  let candidate
  if (process.platform === 'win32') {
    candidate = [join(process.env.SystemRoot || 'C:\Windows', 'System32'), ...keep.filter(e => !/nodejs/i.test(e)), dirname(process.execPath)].join(';')
  } else {
    candidate = keep.join(':')
  }
  if (spawnSync('git', ['--version'], { env: { ...process.env, PATH: candidate } }).status === 0) {
    return mkdtempSync(join(tmpdir(), 'gitless-path-'))
  }
  return candidate
}
const NO_GIT_ENV = { ...process.env, PATH: gitlessPath() }
assert.notEqual(spawnSync('git', ['--version'], { env: NO_GIT_ENV }).status, 0, '受控 PATH 中不应存在 git')

function fixture (materialized) {
  const root = mkdtempSync(join(tmpdir(), 'no-git-boot-'))
  const app = { id: 'demo-app', repository: 'https://github.com/example/demo-app.git', commit: 'a'.repeat(40), install_dir: 'demo-app' }
  mkdirSync(join(root, 'runtime', 'pawapps', 'demo-app'), { recursive: true })
  mkdirSync(join(root, 'runtime', 'cache'), { recursive: true })
  writeFileSync(join(root, 'pawapps.lock.json'), JSON.stringify({ schema_version: 1, apps: [app] }, null, 2))
  writeFileSync(join(root, 'runtime', 'pawapps', 'demo-app', 'plugin.json'), JSON.stringify({ id: 'demo-app', version: '1.0.0' }))
  if (materialized) {
    writeFileSync(join(root, 'runtime', 'pawapps', 'demo-app', '.pawapp-commit'), app.commit + '\n')
  }
  return root
}

// ── 场景 A：物化 + 无 git ────────────────────────────────────────────
const materializedRoot = fixture(true)
try {
  assert.equal(pawappsAllMaterialized(materializedRoot), true, '物化场景应判定无需 git')

  const sync = spawnSync(process.execPath, [join(scriptsRoot, 'sync-pawapps.mjs')], {
    env: { ...NO_GIT_ENV, AI_OS_EMBEDDED_ROOT: materializedRoot },
    encoding: 'utf8',
  })
  assert.equal(sync.status, 0, `无 git 时同步物化应用应成功：\n${sync.stdout}\n${sync.stderr}`)
  assert.ok(sync.stdout.includes('PawApp 已就绪：demo-app'), '应报告应用已就绪')
  assert.ok(sync.stdout.includes('跳过 demo-app 的离线 bundle 缓存'), '应提示跳过 bundle 缓存')
} finally {
  rmSync(materializedRoot, { recursive: true, force: true })
}

// ── 场景 B：未物化 + 无 git ──────────────────────────────────────────
const missingRoot = fixture(false)
try {
  assert.equal(pawappsAllMaterialized(missingRoot), false, '未物化场景必须仍要求 git')

  const sync = spawnSync(process.execPath, [join(scriptsRoot, 'sync-pawapps.mjs')], {
    env: { ...NO_GIT_ENV, AI_OS_EMBEDDED_ROOT: missingRoot },
    encoding: 'utf8',
  })
  assert.notEqual(sync.status, 0, '未物化且无 git 时必须失败（在线拉取不可用）')
} finally {
  rmSync(missingRoot, { recursive: true, force: true })
}

console.log('无 Git 启动回归通过：物化应用可免 git 启动，缺失应用仍要求 git。')
