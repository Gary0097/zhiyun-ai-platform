import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const enterprise = join(root, '..', 'enterprise')
const read = (path) => readFile(path, 'utf8')

const manifest = JSON.parse(await read(join(root, 'plugins/zhiyun-brand/plugin.json')))
assert.equal(manifest.version, '0.2.0')
assert.equal(manifest.entry.backend, 'backend/main.py')
assert.equal(manifest.entry.frontend, 'ui/index.js')

const pluginRoot = join(root, 'plugins/zhiyun-brand')
const backend = await read(join(pluginRoot, manifest.entry.backend))
for (const contract of ['PawApp(', 'enterprise_platform_status', '/api/public/brand', '/api/health', 'ZHIYUN_ENTERPRISE_URL']) {
  assert.ok(backend.includes(contract), `missing brand bridge contract: ${contract}`)
}
assert.ok(!/Authorization.*ENTERPRISE|tenant_id.*request/i.test(backend), 'Q1 public bridge must not accept browser identity as trusted enterprise identity')

const frontend = await read(join(pluginRoot, manifest.entry.frontend))
for (const contract of ['/zhiyun-brand/config', 'runtime.slot.replace', 'header.logo', 'applyBrand']) {
  assert.ok(frontend.includes(contract), `missing dynamic branding contract: ${contract}`)
}

const routes = await read(join(enterprise, 'server/routes.js'))
for (const contract of ['/api/health', '/api/public/brand', '/api/settings/qwenpaw', "{ public: true }"]) {
  assert.ok(routes.includes(contract), `missing enterprise integration route: ${contract}`)
}
assert.ok(routes.includes('SVG Logo 包含脚本、事件或外部资源'), 'SVG brand uploads must reject active content')
const server = await read(join(enterprise, 'server/index.js'))
assert.ok(server.includes('!matched.public'), 'public API exposure must be explicit per route')
const ui = await read(join(enterprise, 'public/index.html'))
assert.ok(ui.includes("api('GET','/api/settings/qwenpaw')"), 'enterprise chat entry must use QwenPaw settings')
assert.ok(ui.includes('QwenPaw 2.1 提供原生流式对话'), 'chat acceptance hint must describe QwenPaw path')

console.log('AI-OS Phase Q1 verification passed: public contracts, persistent brand bridge, QwenPaw chat entry, read-only status tool')
