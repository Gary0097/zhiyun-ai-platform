import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, extname, join, resolve } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const defaultLogo = join(scriptsRoot, '..', '..', '..', 'plugins', 'zhiyun-logo', 'assets', 'default-logo.png')
const mimeByExtension = new Map([
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.svg', 'image/svg+xml'],
  ['.webp', 'image/webp'],
])
const maxBytes = 2 * 1024 * 1024

function workingDir () {
  const explicit = process.env.QWENPAW_WORKING_DIR || process.env.COPAW_WORKING_DIR
  if (explicit) return resolve(explicit)
  const current = join(homedir(), '.qwenpaw')
  const legacy = join(homedir(), '.copaw')
  return !existsSync(current) && existsSync(legacy) ? legacy : current
}

function fail (message) {
  console.error(message)
  process.exit(1)
}

if (process.argv.includes('--check')) {
  if (!existsSync(defaultLogo) || statSync(defaultLogo).size === 0) fail('默认 Logo 资源缺失。')
  console.log(`Logo 配置检查通过：${defaultLogo}`)
  process.exit(0)
}

const argument = process.argv[2]
if (!argument) fail('用法：node set-logo.mjs <png|jpg|svg|webp>，或加 --reset 恢复默认。')

const branding = join(workingDir(), 'branding')
const config = join(branding, 'logo.json')
mkdirSync(branding, { recursive: true })

if (argument === '--reset') {
  rmSync(config, { force: true })
  console.log('Logo 已恢复为项目默认值，重启 AI-OS 后生效。')
  process.exit(0)
}

const source = resolve(argument)
const extension = extname(source).toLowerCase()
const mime = mimeByExtension.get(extension)
if (!existsSync(source) || !statSync(source).isFile() || !mime) fail('请选择有效的 PNG、JPG、SVG 或 WebP Logo 文件。')
if (statSync(source).size > maxBytes) fail('Logo 文件不能超过 2 MB。')

const target = join(branding, `ai-os-logo${extension}`)
copyFileSync(source, target)
writeFileSync(config, `${JSON.stringify({ path: target, mime }, null, 2)}\n`, 'utf8')
const saved = JSON.parse(readFileSync(config, 'utf8'))
if (saved.path !== target || saved.mime !== mime) fail('Logo 配置写入后校验失败。')
console.log(`Logo 已更新：${target}；重启 AI-OS 后生效。`)
