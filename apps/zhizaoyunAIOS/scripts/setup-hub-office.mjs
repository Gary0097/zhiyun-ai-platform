// Installation only: keep Office inside the upstream Hub's existing read roots.
import { cpSync, copyFileSync, existsSync, readFileSync, writeFileSync, statSync, mkdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { bundledOffice, verifyOfficePayload } from './setup-office.mjs'
import { ensureOfficeDependencies, officeDependencySpec, environmentFingerprint } from './ensure-office-deps.mjs'

export async function setupHubOffice(repoRoot, { offline = false, repair = false } = {}) {
  if (process.platform !== 'win32') return
  const appRoot = join(repoRoot, 'apps', 'zhizaoyunAIOS')
  const runtimeRoot = join(appRoot, 'runtime', 'qwenpaw-hub')
  const venv = join(runtimeRoot, 'venv')
  const python = join(venv, 'Scripts', 'python.exe')
  const wrapper = join(repoRoot, 'extras', 'office', 'soffice.exe')
  const office = bundledOffice(repoRoot)
  if (!existsSync(office.manifest) || !existsSync(wrapper)) throw new Error('Full Windows office payload is required for Hub conversion')
  const manifest = JSON.parse(readFileSync(office.manifest, 'utf8'))
  const lock = JSON.parse(readFileSync(join(appRoot, 'office-windows.lock.json'), 'utf8'))
  if (manifest.version !== lock.version || manifest.msi_sha256 !== lock.sha256) throw new Error('Hub office payload does not match its version lock')
  const target = join(venv, 'aios-libreoffice')
  const entry = join(venv, 'Scripts', 'soffice.exe')
  const receipt = join(runtimeRoot, 'hub-office.ok')
  const packRoot = join(repoRoot, 'skills', 'office')
  const key = () => createHash('sha256').update(JSON.stringify({
    payload: readFileSync(office.manifest, 'utf8'),
    wrapper: readFileSync(wrapper).toString('base64'),
    requirements: officeDependencySpec(packRoot).hash,
    environment: environmentFingerprint(python),
    dependencies: readFileSync(join(runtimeRoot, 'office-deps.ok'), 'utf8'),
    entry: statSync(entry).mtimeMs,
    command: statSync(join(target, 'program', 'soffice.com')).mtimeMs,
    library: statSync(join(target, 'program', 'mergedlo.dll')).mtimeMs,
  })).digest('hex')
  try {
    if (!repair && JSON.parse(readFileSync(receipt, 'utf8')).key === key()) {
      console.log('[hub-office] Ready; no copy, dependency probe or download.')
      return
    }
  } catch { /* first installation or replaced managed venv */ }
  await verifyOfficePayload(office.root, manifest)
  mkdirSync(target, { recursive: true })
  cpSync(office.root, target, { recursive: true, filter: path => !path.toLowerCase().endsWith('.msi') })
  copyFileSync(wrapper, entry)
  const result = ensureOfficeDependencies({ appRoot, packRoot, offline, forceReinstall: repair, runtime: { runtimeRoot, python } })
  if (!['installed', 'satisfied', 'up-to-date'].includes(result.status)) throw new Error('Hub office dependencies failed: ' + result.status)
  const probe = spawnSync(python, ['-c', 'import docx,openpyxl,pptx,pypdf,rapidocr_onnxruntime'], { encoding: 'utf8', timeout: 120000 })
  if (probe.status !== 0) throw new Error('Hub office imports failed')
  const version = spawnSync(entry, ['--headless', '--version'], { encoding: 'utf8', timeout: 30000 })
  if (version.status !== 0 || !version.stdout.includes('LibreOffice')) throw new Error('Hub office wrapper cannot launch')
  const dependencies = join(runtimeRoot, 'office-deps.ok')
  const marker = JSON.parse(readFileSync(dependencies, 'utf8'))
  writeFileSync(dependencies, JSON.stringify({ ...marker, environment: environmentFingerprint(python) }) + '\n')
  writeFileSync(receipt, JSON.stringify({ key: key(), installed_at: new Date().toISOString() }) + '\n')
  console.log('[hub-office] Installed Office inside Hub venv read roots; isolated members discover soffice.exe on their native PATH.')
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { await setupHubOffice(resolve(dirname(fileURLToPath(import.meta.url)), '../../..'), { offline: process.argv.includes('--offline'), repair: process.argv.includes('--repair') }) }
  catch (error) { console.error(error.message); process.exitCode = 1 }
}
