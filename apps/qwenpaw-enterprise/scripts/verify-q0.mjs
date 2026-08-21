import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const lock = JSON.parse(await readFile(join(root, 'qwenpaw.lock.json'), 'utf8'))
assert.equal(lock.version, '2.1.0')
assert.equal(lock.branch, 'release/v2.1.0')
assert.match(lock.commit, /^[0-9a-f]{40}$/)
assert.equal(lock.license, 'Apache-2.0')

const pluginRoot = join(root, 'plugins', 'zhiyun-brand')
const manifest = JSON.parse(await readFile(join(pluginRoot, 'plugin.json'), 'utf8'))
assert.equal(manifest.id, 'zhiyun-brand')
assert.equal(manifest.type, 'general')
assert.equal(manifest.entry.backend, 'backend/main.py')
assert.equal(manifest.qwenpaw_version.min, '2.1.0')
assert.equal(manifest.qwenpaw_version.max, '2.2.0')

const frontend = await readFile(join(pluginRoot, manifest.entry.frontend), 'utf8')
for (const contract of ['runtime.chat.leftHeader.set', 'runtime.chat.theme.set', 'runtime.chat.welcome.set', 'runtime.chat.sender.set']) {
  assert.ok(frontend.includes(contract), `missing QwenPaw extension contract: ${contract}`)
}
assert.ok(!/api[_-]?key\s*[:=]\s*["'][^"']+/i.test(frontend), 'frontend must not contain an API key')

async function files (dir) {
  const out = []
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, item.name)
    if (item.isDirectory()) out.push(...await files(path))
    else out.push(path)
  }
  return out
}
for (const path of await files(join(root, 'plugins'))) {
  if (!/\.(?:js|mjs|json|md)$/.test(path)) continue
  const content = await readFile(path, 'utf8')
  assert.ok(!/DeepSeek Harness|events\.mux|DSH HTTP/i.test(content), `new QwenPaw integration must not depend on DSH: ${path}`)
}

console.log('AI-OS Phase Q0 verification passed: upstream lock, brand plugin contract, secret check, DSH freeze')
