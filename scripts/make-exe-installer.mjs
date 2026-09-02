// 构建 EXE 安装程序：编译自解压引导器，并把离线 zip 拼接为其载荷。
// 前置：node scripts/make-release-package.mjs <版本> --offline 已产出 dist/*.zip；
//       本机有 .NET Framework 4.x 的 csc.exe（Windows 自带）。
// 用法：node scripts/make-exe-installer.mjs <版本号>
// 产物：dist/zhiyun-ai-os-<版本>-setup.exe（双击 → 选目录 → 解压 → 自动 install-usb.cmd）
import { createHash } from 'node:crypto'
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const version = process.argv[2] || process.env.RELEASE_VERSION || ''
if (!version) {
  console.error('用法：node scripts/make-exe-installer.mjs <版本号>，如 1.3.0')
  process.exit(1)
}
const distDir = join(root, 'dist')
const zipName = `zhiyun-ai-os-v${version}-offline-usb.zip`
const zipPath = join(distDir, zipName)
if (!existsSync(zipPath)) {
  console.error(`未找到离线包 ${zipPath}；请先运行 node scripts/make-release-package.mjs ${version} --offline`)
  process.exit(1)
}

// 1) 定位 .NET Framework csc
const cscCandidates = [
  join(process.env.SystemRoot || 'C:\\Windows', 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe'),
  join(process.env.SystemRoot || 'C:\\Windows', 'Microsoft.NET', 'Framework', 'v4.0.30319', 'csc.exe'),
]
const csc = cscCandidates.find(existsSync)
if (!csc) {
  console.error('未找到 .NET Framework csc.exe，无法编译引导器（需要 Windows + .NET 4.x）。')
  process.exit(1)
}

// 2) 编译 stub（WinExe：无控制台窗口）
const buildDir = join(root, '.exe-build')
rmSync(buildDir, { recursive: true, force: true })
mkdirSync(buildDir, { recursive: true })
const stubPath = join(buildDir, 'stub.exe')
const srcPath = join(root, 'scripts', 'exe-installer', 'bootstrap.cs')
// 版本在编译期打进引导器（卸载项/关于信息使用）
const versionSrc = join(buildDir, 'VersionInfo.cs')
writeFileSync(versionSrc, `// 自动生成：make-exe-installer.mjs
static class VersionInfo { public const string AppVersion = "${version}"; }
`, 'utf8')
execFileSync(csc, [
  '/nologo', '/target:winexe', '/optimize+',
  '/out:' + stubPath,
  '/r:System.IO.Compression.dll',
  '/r:System.IO.Compression.FileSystem.dll',
  '/r:System.Windows.Forms.dll',
  '/r:System.Drawing.dll',
  srcPath,
  versionSrc,
], { stdio: 'inherit' })
if (!existsSync(stubPath)) {
  console.error('引导器编译失败。')
  process.exit(1)
}
console.log(`引导器编译完成：${stubPath}（${(statSync(stubPath).size / 1024).toFixed(0)} KB）`)

// 3) 拼接：stub + 标记 + zip → setup.exe（流式复制，避免整包读入内存）
import { createReadStream } from 'node:fs'
import { openSync as fsOpen, readSync, writeSync, closeSync } from 'node:fs'
const MARKER = Buffer.from('ZYLZWC1!', 'ascii')
const exeName = `zhiyun-ai-os-v${version}-setup.exe`
const exePath = join(distDir, exeName)
const stub = readFileSync(stubPath)
const fd = fsOpen(exePath, 'w')
try {
  writeSync(fd, stub)
  writeSync(fd, MARKER)
  await new Promise((resolve, reject) => {
    const input = createReadStream(zipPath)
    input.on('data', chunk => writeSync(fd, chunk))
    input.on('end', resolve)
    input.on('error', reject)
  })
} finally {
  closeSync(fd)
}
// 4) 定点校验：stub 长度偏移处必须是标记
{
  const vfd = fsOpen(exePath, 'r')
  const probe = Buffer.alloc(MARKER.length)
  readSync(vfd, probe, 0, MARKER.length, stub.length)
  closeSync(vfd)
  if (!probe.equals(MARKER)) {
    console.error('拼接校验失败：载荷标记错位。')
    process.exit(1)
  }
}
rmSync(buildDir, { recursive: true, force: true })
const sha256 = await new Promise((resolve, reject) => {
  const hash = createHash('sha256')
  const input = createReadStream(exePath)
  input.on('data', chunk => hash.update(chunk))
  input.on('end', () => resolve(hash.digest('hex')))
  input.on('error', reject)
})
writeFileSync(`${exePath}.sha256`, `${sha256}  ${exeName}\n`, 'utf8')
const sizeMb = (statSync(exePath).size / 1024 / 1024).toFixed(2)
console.log(`EXE 安装程序构建完成：dist/${exeName}（${sizeMb} MB）`)
console.log(`SHA256：${sha256}`)
console.log('使用方式：双击 → 选择安装目录 → 自动解压并运行 install-usb.cmd（桌面/开始菜单快捷方式 + 控制面板可卸载）')
