import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { verifyOfficePayload, officeInstallationReady } from './setup-office.mjs'

const temp = mkdtempSync(join(tmpdir(), 'aios-office-payload-'))
try {
  const paths = ['program/soffice.exe', 'program/soffice.com', 'LICENSE.html', 'license.txt', 'NOTICE', 'SOURCE-OFFER.txt']
  mkdirSync(join(temp, 'program'))
  const manifest = { files: paths.map(path => {
    writeFileSync(join(temp, path), path)
    return { path, sha256: createHash('sha256').update(path).digest('hex') }
  }) }
  await verifyOfficePayload(temp, manifest)
  writeFileSync(join(temp, 'program', 'soffice.exe'), 'corrupt')
  await assert.rejects(verifyOfficePayload(temp, manifest), /checksum mismatch/)
  await assert.rejects(verifyOfficePayload(temp, { files: [{ path: '../outside', sha256: '0'.repeat(64) }] }), /Unsafe/)
  await assert.rejects(verifyOfficePayload(temp, { files: [] }), /Empty/)
  assert.equal(officeInstallationReady(temp), false)
  console.log('Office payload: checksum verification, corrupt/missing payload and traversal rejection passed.')
} finally { rmSync(temp, { recursive: true, force: true }) }
