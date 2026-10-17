// Build-time only: verify the official MSI, extract without system installation,
// retain notices and hash the portable payload. Never called by the launcher.
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { createReadStream, existsSync, mkdirSync, readFileSync, readdirSync, copyFileSync, renameSync, writeFileSync } from 'node:fs'
import { join, resolve, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { pipeline } from 'node:stream/promises'
import { createWriteStream } from 'node:fs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const lock = JSON.parse(readFileSync(join(root, 'apps/zhizaoyunAIOS/office-windows.lock.json')))
const args = process.argv.slice(2)
const value = flag => args.includes(flag) ? args[args.indexOf(flag) + 1] : null
const build = join(root, 'apps/zhizaoyunAIOS/runtime/office-build')
const target = join(build, `libreoffice-${lock.version}`)
const msi = resolve(value('--msi') || join(build, `LibreOffice_${lock.version}.msi`))
export async function sha256 (path) {
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(path)) hash.update(chunk)
  return hash.digest('hex')
}
if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('Requires a Windows x64 build host')
mkdirSync(build, { recursive: true })
if (!existsSync(msi)) {
  const response = await fetch(lock.url)
  if (!response.ok) throw new Error(`LibreOffice download failed: HTTP ${response.status}`)
  await pipeline(response.body, createWriteStream(msi + '.part'))
  renameSync(msi + '.part', msi)
}
if (await sha256(msi) !== lock.sha256) throw new Error('LibreOffice MSI checksum mismatch; refusing to extract')
if (existsSync(target)) throw new Error(`Build directory already exists: ${target}; use its verified manifest or a new clean build directory`)
mkdirSync(target)
execFileSync('msiexec.exe', ['/a', msi, '/qn', `TARGETDIR=${target}`, '/l*v', join(build, 'libreoffice-extract.log')], { stdio: 'inherit', timeout: 600000 })
// MSI carries the x64 VC runtime as installer components. App-local deployment
// avoids a separate redistributable install and does not touch System32.
for (const file of readdirSync(join(target, 'System64'))) {
  if (file.endsWith('.dll')) copyFileSync(join(target, 'System64', file), join(target, 'program', file))
}
for (const name of ['program/soffice.exe', 'program/soffice.com', 'LICENSE.html', 'license.txt', 'NOTICE']) {
  if (!existsSync(join(target, name))) throw new Error(`Incomplete LibreOffice payload: ${name}`)
}
writeFileSync(join(target, 'SOURCE-OFFER.txt'), `Unmodified LibreOffice ${lock.version} binaries from The Document Foundation.\nSource code and component source archives: ${lock.source_url}\nLicenses: ${lock.license_url}\nOriginal LICENSE.html, license.txt and NOTICE are included.\nMSI SHA-256: ${lock.sha256}\n`)
const files = []
async function walk (dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isSymbolicLink()) throw new Error('Symlinks are not supported in the office payload')
    if (entry.isDirectory()) await walk(path)
    else if (!entry.name.endsWith('.msi')) files.push({ path: relative(target, path).replaceAll('\\', '/'), sha256: await sha256(path) })
  }
}
await walk(target)
writeFileSync(join(target, 'office-bundle.manifest.json'), JSON.stringify({ schema_version: 1, version: lock.version, msi_sha256: lock.sha256, files }, null, 2) + '\n')
console.log(`Verified LibreOffice ${lock.version}: ${files.length} files. Payload: ${target}`)
