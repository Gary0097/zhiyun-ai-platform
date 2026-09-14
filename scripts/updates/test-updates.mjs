import test from 'node:test'
import assert from 'node:assert/strict'
import { generateKeyPairSync, sign, createHash, createPublicKey } from 'node:crypto'
import { mkdtempSync, readFileSync, existsSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { authenticate, compare, config, download, releaseAsset, small, validateManifest } from './protocol.mjs'
import { track } from './track-upstream.mjs'
import { verifyPublisherKey } from './verify-publisher-key.mjs'

const { privateKey, publicKey } = generateKeyPairSync('ed25519')
const keys = [publicKey.export({ type: 'spki', format: 'pem' })]
const data = Buffer.from('test installer bytes: never executable')
const asset = { platform: 'win32', name: 'zhiyun-ai-os-v2.2.1-setup.exe', size: data.length, sha256: createHash('sha256').update(data).digest('hex') }
const manifest = { schema: 1, product: 'zhiyun-ai-os', version: '2.2.1', commit: 'a'.repeat(40), assets: [asset] }
const raw = Buffer.from(JSON.stringify(manifest))
test('release channel contains distinct valid Ed25519 public trust roots', () => {
  const channel = config(new URL('./channel.json', import.meta.url))
  assert.ok(channel.publicKeys.length > 0, 'Production signing bootstrap requires a public trust root')
  const fingerprints = channel.publicKeys.map(pem => {
    assert.ok(!pem.includes('PRIVATE KEY'), 'Private material must never enter the client channel')
    const key = createPublicKey(pem)
    assert.equal(key.asymmetricKeyType, 'ed25519')
    return createHash('sha256').update(key.export({ format: 'der', type: 'spki' })).digest('hex')
  })
  assert.equal(new Set(fingerprints).size, fingerprints.length)
})
test('publisher verification proves key pairing without publishing an artifact', () => {
  const pem = privateKey.export({ type: 'pkcs8', format: 'pem' })
  assert.match(verifyPublisherKey(keys, pem), /^[a-f0-9]{64}$/)
  assert.throws(() => verifyPublisherKey([], pem))
  assert.throws(() => verifyPublisherKey(keys, generateKeyPairSync('ed25519').privateKey.export({ type: 'pkcs8', format: 'pem' })))
  assert.throws(() => verifyPublisherKey(keys, ''))
})
test('stable version comparison rejects pre-releases and malformed versions', () => {
  assert.equal(compare('2.10.0', '2.2.9'), 1)
  assert.equal(compare('2.2.0', '2.2.0'), 0)
  assert.equal(compare('1.9.9', '2.0.0'), -1)
  for (const v of ['2.2.1-beta', '02.2.1', '../2.2.1', '1.2.3.4', '99999999999999999999.1.0']) assert.throws(() => compare(v, '2.2.0'))
})
test('only matching Ed25519 publisher signature authenticates exact manifest bytes', () => {
  const signature = sign(null, raw, privateKey)
  assert.deepEqual(authenticate(raw, signature, keys, 'v2.2.1'), manifest)
  assert.throws(() => authenticate(raw, signature, [], 'v2.2.1'))
  assert.throws(() => authenticate(Buffer.concat([raw, Buffer.from(' ')]), signature, keys, 'v2.2.1'))
  assert.throws(() => authenticate(raw, signature, keys, 'v2.2.2'))
  assert.throws(() => authenticate(raw, sign(null, raw, generateKeyPairSync('ed25519').privateKey), keys, 'v2.2.1'))
})
test('manifest and source reject wrong products, duplicate platforms and external assets', () => {
  assert.throws(() => validateManifest({ ...manifest, product: 'QwenPaw' }, 'v2.2.1'))
  assert.throws(() => validateManifest({ ...manifest, assets: [asset, asset] }, 'v2.2.1'))
  assert.throws(() => validateManifest({ ...manifest, assets: [{ ...asset, name: '../x.exe' }] }, 'v2.2.1'))
  assert.throws(() => releaseAsset({ tag_name: 'v2.2.1', assets: [{ name: asset.name, browser_download_url: 'https://attacker.example/x' }] }, asset.name, 'Gary0097/zhiyun-ai-platform'))
})
test('streaming download accepts exact digest, cleans up truncation, excess, wrong hash and HTTP failures', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'aios-update-test-'))
  try {
    const target = join(directory, 'installer')
    await download('https://example.invalid', asset, target, async () => new Response(data))
    assert.deepEqual(readFileSync(target), data)
    rmSync(target)
    writeFileSync(target + '.part', 'another download')
    await assert.rejects(download('https://example.invalid', asset, target, async () => new Response(data)))
    assert.equal(readFileSync(target + '.part', 'utf8'), 'another download')
    rmSync(target + '.part')
    for (const response of [new Response(data.subarray(1)), new Response(Buffer.concat([data, data])), new Response(Buffer.alloc(data.length)), new Response('', { status: 503 })]) {
      await assert.rejects(download('https://example.invalid', asset, target, async () => response))
      assert.equal(existsSync(target), false)
      assert.equal(existsSync(target + '.part'), false)
    }
  } finally { rmSync(directory, { recursive: true, force: true }) }
})
test('metadata fetch enforces size and fails closed on network errors', async () => {
  await assert.rejects(small('unused', 2, async () => new Response('123')))
  await assert.rejects(small('unused', 2, async () => { throw Error('offline') }))
})
test('upstream tracking creates one task with precise commit and deduplicates closed tasks', async () => {
  const writes = []; let existing = []
  const api = async (path, body) => {
    if (body) { writes.push(body); return {} }
    if (path.endsWith('/releases/latest')) return { tag_name: 'v2.2.1', prerelease: false, draft: false }
    if (path.includes('/commits/')) return { sha: 'c'.repeat(40) }
    return existing
  }
  await track(api, '2.2.0', 'owner/repo')
  assert.equal(writes.length, 1)
  assert.ok(writes[0].body.includes('c'.repeat(40)))
  existing = [{ body: writes[0].body, state: 'closed' }]
  await track(api, '2.2.0', 'owner/repo')
  assert.equal(writes.length, 1)
  await track(api, '2.2.1', 'owner/repo')
  assert.equal(writes.length, 1)
})
test('upstream beta or unavailable commit never creates an upgrade task', async () => {
  let writes = 0
  await assert.rejects(track(async (path, body) => { if (body) writes++; return { tag_name: 'v2.3.0-beta', prerelease: true } }, '2.2.0', 'owner/repo'))
  assert.equal(writes, 0)
})
