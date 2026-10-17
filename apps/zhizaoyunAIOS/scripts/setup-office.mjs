// Install/repair only. Launchers read receipts and never run this provisioner.
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { createReadStream, existsSync, readFileSync, writeFileSync, statSync, realpathSync } from 'node:fs'
import { dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { ensureOfficeDependencies, environmentFingerprint, officeDependencySpec, resolveVenvPython } from './ensure-office-deps.mjs'

export function bundledOffice (repoRoot) {
  const root = join(repoRoot, 'extras', 'libreoffice')
  return { root, manifest: join(root, 'office-bundle.manifest.json'), command: join(root, 'program', 'soffice.com') }
}

export async function verifyOfficePayload (root, manifest) {
  const base = realpathSync(root)
  for (const entry of manifest.files || []) {
    if (!entry.path || entry.path.split('/').some(p => !p || p === '.' || p === '..' || /[\\:\0]/.test(p))) throw new Error('Unsafe office manifest path')
    if (!/^[0-9a-f]{64}$/.test(entry.sha256)) throw new Error('Invalid office file checksum')
    const path = realpathSync(join(root, ...entry.path.split('/')))
    if (!path.startsWith(base + sep)) throw new Error('Office manifest escapes the payload directory')
    const hash = createHash('sha256')
    for await (const bytes of createReadStream(path)) hash.update(bytes)
    if (hash.digest('hex') !== entry.sha256) throw new Error(`Office payload checksum mismatch: ${entry.path}`)
  }
  if (!manifest.files?.length) throw new Error('Empty office payload manifest')
  for (const required of ['program/soffice.exe', 'program/soffice.com', 'LICENSE.html', 'license.txt', 'NOTICE', 'SOURCE-OFFER.txt']) {
    if (!manifest.files.some(f => f.path === required)) throw new Error(`Office manifest missing ${required}`)
  }
}

function installationKey (repoRoot) {
  const appRoot = join(repoRoot, 'apps', 'zhizaoyunAIOS')
  const { python } = resolveVenvPython(appRoot)
  const { hash } = officeDependencySpec(join(repoRoot, 'skills', 'office'))
  const office = bundledOffice(repoRoot)
  const binary = statSync(office.command)
  const manifest = statSync(office.manifest)
  return createHash('sha256').update(JSON.stringify({
    requirements: hash, environment: environmentFingerprint(python),
    officeLock: readFileSync(join(appRoot, 'office-windows.lock.json'), 'utf8'),
    manifest: { size: manifest.size, mtime: manifest.mtimeMs, ctime: manifest.ctimeMs },
    command: office.command, size: binary.size, mtime: binary.mtimeMs, ctime: binary.ctimeMs,
  })).digest('hex')
}

export function officeInstallationReady (repoRoot) {
  try {
    const { runtimeRoot, python } = resolveVenvPython(join(repoRoot, 'apps', 'zhizaoyunAIOS'))
    if (!existsSync(python)) return false
    const receipt = JSON.parse(readFileSync(join(runtimeRoot, 'office-install.ok'), 'utf8'))
    return receipt.key === installationKey(repoRoot)
  } catch { return false }
}

export async function setupOffice ({ repoRoot, offline = false, log = console.log }) {
  if (process.platform !== 'win32') return { status: 'not-windows' }
  if (officeInstallationReady(repoRoot)) {
    log('[office-setup] Office ready; no dependency probe, download or LibreOffice process needed.')
    return { status: 'up-to-date' }
  }
  const appRoot = join(repoRoot, 'apps', 'zhizaoyunAIOS')
  const lock = JSON.parse(readFileSync(join(appRoot, 'office-windows.lock.json'), 'utf8'))
  const office = bundledOffice(repoRoot)
  if (!existsSync(office.manifest) || !existsSync(office.command)) throw new Error('Bundled LibreOffice is missing; use the full Windows office installer or rebuild its payload.')
  const manifest = JSON.parse(readFileSync(office.manifest, 'utf8'))
  if (manifest.version !== lock.version || manifest.msi_sha256 !== lock.sha256) throw new Error('LibreOffice manifest does not match office-windows.lock.json')
  log(`[office-setup] Verifying bundled LibreOffice ${lock.version} (installation only)...`)
  await verifyOfficePayload(office.root, manifest)
  const dependencies = ensureOfficeDependencies({ appRoot, packRoot: join(repoRoot, 'skills', 'office'), offline, log })
  if (!['up-to-date', 'satisfied', 'installed'].includes(dependencies.status)) throw new Error('Office dependencies failed: ' + dependencies.status)
  const { runtimeRoot, python } = resolveVenvPython(appRoot)
  const probe = spawnSync(python, ['-c', 'import docx,openpyxl,pptx,pdfplumber,pypdf,fpdf,pypdfium2,PIL,chardet,markdownify,pandas,rapidocr_onnxruntime; print("office-imports-ok")'], { encoding: 'utf8', timeout: 120000 })
  if (probe.status !== 0) throw new Error('Office import verification failed: ' + (probe.stderr || probe.error?.message || '').slice(0, 300))
  const profile = pathToFileURL(join(runtimeRoot, 'office-profile')).href
  const version = spawnSync(office.command, [`-env:UserInstallation=${profile}`, '--headless', '--version'], { encoding: 'utf8', timeout: 30000 })
  if (version.status !== 0 || !(version.stdout || '').includes('LibreOffice ' + lock.version)) throw new Error('Bundled LibreOffice cannot start')
  writeFileSync(join(runtimeRoot, 'office-install.ok'), JSON.stringify({ schema_version: 1, key: installationKey(repoRoot), libreoffice: lock.version, installed_at: new Date().toISOString() }) + '\n')
  log(`[office-setup] Office installed: LibreOffice ${lock.version}, pinned Python dependencies and local OCR ready.`)
  return { status: 'installed' }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
  try { await setupOffice({ repoRoot, offline: process.argv.includes('--offline') }) }
  catch (e) { console.error('[office-setup] ' + e.message); process.exitCode = 1 }
}
