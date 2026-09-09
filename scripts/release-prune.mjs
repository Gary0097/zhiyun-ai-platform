// dist 历史产物自动清理：安装包（400MB 级）逐版堆积曾把 dist 撑到 7GB
// （2026-09-03 手工清理回收 6.2GB）。本模块供 make-release-package.mjs 在
// 打包成功后调用，只保留最近 N 个版本的产物，其余连同 .sha256 一并删除。
// 非版本命名文件（如 INSTALLER-VERSION.txt）永不触碰。
//
// 独立 CLI：node scripts/release-prune.mjs [--keep N] [--dry-run] [--check]
//   --check     自检（verify-release.mjs 门禁调用，不改动 dist）
//   --keep N    保留最近 N 个版本，默认 2
//   --dry-run   只打印将删除的文件
import assert from 'node:assert/strict'
import { readdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// 与 make-release-package.mjs / make-exe-installer.mjs 的产物命名保持一致
const ARTIFACT_RE = /^zhiyun-ai-os-v(\d+)\.(\d+)\.(\d+)-(?:offline-usb\.zip|setup\.exe|online-installer\.zip)(?:\.sha256)?$/

export function parseVersionedArtifact (name) {
  const m = ARTIFACT_RE.exec(name)
  if (!m) return null
  return { name, key: [Number(m[1]), Number(m[2]), Number(m[3])] }
}

// 计算清理计划：names 中属于将被删除的产物（不在最近 keepVersions 个版本内，
// 且不属于 protectVersion —— 经 --ref 重建旧版本时，本次刚构建的产物必须保留）
export function planPrune (names, keepVersions = 2, protectVersion = '') {
  const versioned = names.map(parseVersionedArtifact).filter(Boolean)
  const versions = [...new Map(versioned.map(v => [v.key.join('.'), v.key])).values()]
    .sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2])
  const keep = new Set(versions.slice(-Math.max(1, keepVersions)).map(k => k.join('.')))
  if (protectVersion) keep.add(String(protectVersion))
  return versioned.filter(v => !keep.has(v.key.join('.'))).map(v => v.name)
}

// 执行清理，返回删除的文件名列表；dryRun 时只返回不删除
export function pruneDist (distDir, { keep = 2, dryRun = false, protect = '' } = {}) {
  const doomed = planPrune(readdirSync(distDir), keep, protect)
  if (!dryRun) for (const name of doomed) rmSync(join(distDir, name), { force: true })
  return doomed
}

function selfCheck () {
  assert.ok(parseVersionedArtifact('zhiyun-ai-os-v1.4.1-setup.exe'))
  assert.ok(parseVersionedArtifact('zhiyun-ai-os-v1.4.1-offline-usb.zip.sha256'))
  assert.ok(parseVersionedArtifact('zhiyun-ai-os-v1.1.0-online-installer.zip'))
  assert.equal(parseVersionedArtifact('INSTALLER-VERSION.txt'), null)
  assert.equal(parseVersionedArtifact('zhiyun-ai-os-v1.4.1-setup.exe.tmp'), null)

  const files = [
    'INSTALLER-VERSION.txt',
    'zhiyun-ai-os-v1.0.0-online-installer.zip',
    'zhiyun-ai-os-v1.0.0-online-installer.zip.sha256',
    'zhiyun-ai-os-v1.9.0-offline-usb.zip',
    'zhiyun-ai-os-v1.10.0-offline-usb.zip',
    'zhiyun-ai-os-v1.10.0-offline-usb.zip.sha256',
    'zhiyun-ai-os-v1.10.1-setup.exe',
    'zhiyun-ai-os-v1.10.1-setup.exe.sha256',
  ]
  // 数值比较：1.10.x > 1.9.x；最近 2 版 = 1.10.0/1.10.1，其余删除，非产物保留
  assert.deepEqual(planPrune(files, 2).sort(), [
    'zhiyun-ai-os-v1.0.0-online-installer.zip',
    'zhiyun-ai-os-v1.0.0-online-installer.zip.sha256',
    'zhiyun-ai-os-v1.9.0-offline-usb.zip',
  ])
  assert.deepEqual(planPrune(files, 1).sort(), [
    'zhiyun-ai-os-v1.0.0-online-installer.zip',
    'zhiyun-ai-os-v1.0.0-online-installer.zip.sha256',
    'zhiyun-ai-os-v1.10.0-offline-usb.zip',
    'zhiyun-ai-os-v1.10.0-offline-usb.zip.sha256',
    'zhiyun-ai-os-v1.9.0-offline-usb.zip',
  ])

  // protect：--ref 重建旧版本时，本次刚构建的产物即使不在最近 N 版也必须保留
  const rebuild = [
    'zhiyun-ai-os-v1.3.0-offline-usb.zip',
    'zhiyun-ai-os-v1.3.0-offline-usb.zip.sha256',
    'zhiyun-ai-os-v1.4.0-offline-usb.zip',
    'zhiyun-ai-os-v1.4.1-offline-usb.zip',
    'zhiyun-ai-os-v1.5.0-offline-usb.zip',
  ]
  assert.deepEqual(planPrune(rebuild, 2, '1.3.0').sort(), [
    'zhiyun-ai-os-v1.4.0-offline-usb.zip',
  ])
  console.log('release-prune self-check OK')
}

// CLI 入口（被 import 时不执行）
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  if (process.argv.includes('--check')) {
    selfCheck()
  } else {
    const argv = process.argv.slice(2)
    const keepIdx = argv.indexOf('--keep')
    const keep = keepIdx !== -1 ? Number(argv[keepIdx + 1]) : 2
    const protectIdx = argv.indexOf('--protect')
    const protect = protectIdx !== -1 ? argv[protectIdx + 1] : ''
    const dryRun = argv.includes('--dry-run')
    const distDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
    for (const name of pruneDist(distDir, { keep, dryRun, protect })) {
      console.log(`${dryRun ? '[dry-run] ' : ''}清理历史产物：${name}`)
    }
  }
}
