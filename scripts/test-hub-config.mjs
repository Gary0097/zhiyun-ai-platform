import assert from 'node:assert/strict'
import { lanAddress, renderHubConfig } from '../apps/zhizaoyunAIOS/scripts/hub-config.mjs'

const net = (address, internal = false) => ({ address, internal, family: 'IPv4' })
assert.equal(lanAddress({ lo: [net('127.0.0.1', true)], eth: [net('172.20.1.9')] }), '172.20.1.9')
assert.equal(lanAddress({ eth: [net('169.254.1.3')] }), '127.0.0.1')
assert.equal(lanAddress({ eth: [net('172.32.0.1')] }), '127.0.0.1')
const source = 'control_plane:\r\n  public_base_url: http://127.0.0.1:8000 # 回调\r\n  registration:\r\n    enabled: false\r\n'
assert.equal(renderHubConfig(source, '192.168.1.2'), source.replace('127.0.0.1', '192.168.1.2'))
const custom = source.replace('http://127.0.0.1:8000', 'https://aios.example.com')
assert.equal(renderHubConfig(custom, '192.168.1.2'), custom)
console.log('Hub configuration: private networks, CRLF, custom URLs and registration preservation passed')
