// 构建一键安装发布包：从干净的 master worktree 导出受控文件 + 版本清单，输出 zip 与 SHA256。
// 前置：发布内容已合并到 master。用法：node scripts/make-release-package.mjs <版本号>
import { createHash } from 'node:crypto'
import { execSync, spawnSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync, existsSync, statSync, rmSync, cpSync } from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const version = process.argv[2] || process.env.RELEASE_VERSION || ''
if (!version) {
  console.error('用法：node scripts/make-release-package.mjs <版本号>，如 1.0.0')
  process.exit(1)
}
const distDir = join(root, 'dist')
const zipName = `zhiyun-ai-os-v${version}-online-installer.zip`
const zipPath = join(distDir, zipName)
const workDir = join(root, '.release-worktree')

function run(cmd, opts = {}) { execSync(cmd, { cwd: root, stdio: 'inherit', ...opts }) }

rmSync(workDir, { recursive: true, force: true })
mkdirSync(distDir, { recursive: true })
const ref = process.env.RELEASE_REF || 'master'
run(`git worktree add --detach "${workDir}" ${ref}`)

// 版本清单：锁定的 PawApp 与运行时版本随包分发，供校验与诊断
const lock = JSON.parse(readFileSync(join(workDir, 'apps', 'qwenpaw-embedded', 'pawapps.lock.json'), 'utf8'))
const manifest = [
  'product: zhiyun-ai-os',
  `version: ${version}`,
  'qwenpaw: 2.1.0',
  `locked_pawapps: ${lock.apps.length}`,
  ...lock.apps.map(a => `  - ${a.id} @ ${a.commit}`),
  'channel: online-installer',
  'note: 首次运行 install-oneclick 时会从 GitHub 拉取以上锁定版本',
]
writeFileSync(join(workDir, 'INSTALLER-VERSION.txt'), manifest.join('\n') + '\n', 'utf8')

// 先移除 worktree 的 .git 指针（文件或目录），避免压缩包泄漏本机绝对路径
const gitEntry = join(workDir, '.git')
if (existsSync(gitEntry)) {
  const st = statSync(gitEntry)
  if (st.isDirectory()) rmSync(gitEntry, { recursive: true, force: true })
  else rmSync(gitEntry, { force: true })
}

// 跨平台压缩
 else {
  run(`cd "${workDir}" && zip -r -q "${zipPath}" . -x '.git/*'`)
}

try {
  // 跨平台压缩
  if (process.platform === 'win32') {
    run(`powershell -NoProfile -Command "Compress-Archive -Path '${join(workDir, '*')}' -DestinationPath '${zipPath}' -Force"`)
  } else {
    run(`cd "${workDir}" && zip -r -q "${zipPath}" . -x '.git'`)
  }
} finally {
  // 无论成败都清理 worktree（失败后 prune，保证下次可重建）
  try { run('git worktree remove --force .release-worktree') } catch { run('git worktree prune'); rmSync(workDir, { recursive: true, force: true }) }
}

const sha256 = createHash('sha256').update(readFileSync(zipPath)).digest('hex')
writeFileSync(`${zipPath}.sha256`, `${sha256}  ${zipName}\n`, 'utf8')
writeFileSync(join(distDir, 'INSTALLER-VERSION.txt'), manifest.join('\n') + '\n', 'utf8')
const sizeMb = (statSync(zipPath).size / 1024 / 1024).toFixed(2)
console.log(`打包完成：dist/${zipName}（${sizeMb} MB）`)
console.log(`SHA256：${sha256}`)
if (!existsSync(zipPath) || statSync(zipPath).size < 50 * 1024) {
  console.error('打包产物异常（过小），请检查压缩步骤。')
  process.exit(1)
}
