import assert from 'node:assert/strict'
import { normalizeBaseUrl, providerConfig, mergeModels, requestMessage, discoveryMessage, newProviderId } from '../plugins/aios-brand/dist/model-setup.mjs'

assert.equal(normalizeBaseUrl(' http://127.0.0.1:8888/v1/chat/completions '), 'http://127.0.0.1:8888/v1')
assert.equal(normalizeBaseUrl('https://example.test/custom/v1/models/'), 'https://example.test/custom/v1')
assert.equal(normalizeBaseUrl('https://example.test/v1/responses'), 'https://example.test/v1')
for (const unsafe of ['file:///C:/secret', 'javascript:alert(1)', 'https://user:password@example.test/v1', 'https://example.test/v1?api_key=secret', 'https://example.test/v1#secret', 'not a URL']) {
  assert.throws(() => normalizeBaseUrl(unsafe))
}
const form = { name: ' Local ', url: 'http://localhost:8888/v1/', protocol: 'OpenAIChatModel', key: '' }
assert.equal(Object.hasOwn(providerConfig(form, true), 'api_key'), false, 'Editing with a blank field must not clear a stored credential')
assert.equal(providerConfig({ ...form, key: ' synthetic-only ' }, true).api_key, 'synthetic-only')
assert.equal(providerConfig(form, false).api_key, '')
assert.equal(providerConfig(form, true).auto_discover, false, 'Explicit discovery must not also trigger a background duplicate')
assert.equal(Object.hasOwn(providerConfig(form, true), 'custom_headers'), false, 'Advanced headers must not be overwritten')
assert.equal(Object.hasOwn(providerConfig(form, true), 'generate_kwargs'), false)
assert.throws(() => providerConfig({ ...form, name: ' ' }, false))
assert.deepEqual(mergeModels({ models: [{ id: 'a', name: 'A', api_key: 'must-not-retain' }], discovered_models: [{ id: 'a', name: 'Updated' }, { id: 'b', name: 'B' }] }), [{ id: 'a', name: 'Updated' }, { id: 'b', name: 'B' }])
assert.match(requestMessage(401), /登录/)
assert.match(requestMessage(403), /权限/)
assert.match(discoveryMessage('authentication'), /密钥/)
assert.match(discoveryMessage('network'), /服务是否启动/)
assert.match(discoveryMessage('unsupported'), /手填/)
assert.match(newProviderId(), /^aios-[0-9a-f]{20}$/)
assert.notEqual(newProviderId(), newProviderId())
console.log('PASS model setup: endpoint parsing, credential preservation, bounded metadata and Chinese error classification')
