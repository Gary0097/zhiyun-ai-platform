import assert from 'node:assert/strict'
import http from 'node:http'
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const scripts = dirname(fileURLToPath(import.meta.url))
const healthScript = join(scripts, 'health-report.mjs')

function catalog () {
  return {
    apps: [
      { app_id: 'zhiyun-data-studio', version: '0.8.0', install_status: 'installed', health: 'available', capabilities: Array.from({ length: 31 }, (_, index) => ({ id: index + 1 })) },
      { app_id: 'zhiyun-order-studio', version: '0.6.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-integration-hub', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-service-studio', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-supply-studio', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-sales-studio', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-finance-studio', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-people-studio', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [] },
      { app_id: 'zhiyun-chanjet-hub', version: '0.1.0', install_status: 'installed', health: 'available', capabilities: [{ id: 'ext_chanjet_fetch' }] },
      { app_id: 'zhiyun-data-core', version: '0.5.0', capabilities: [] },
      { app_id: 'zhiyun-audit', version: '1.1.1', capabilities: [] },
      { app_id: 'zhiyun-logo', version: '1.0.0', capabilities: [] },
    ],
  }
}

async function scenario (overrides = {}) {
  const server = http.createServer((request, response) => {
    response.statusCode = 200
    if (request.url === '/') {
      response.setHeader('content-type', 'text/html')
      response.end('<html>QwenPaw</html>')
      return
    }
    response.setHeader('content-type', 'application/json')
    const bodies = {
      '/api/zhiyun-logo/config': { logo: 'data:image/png;base64,AA==', source: 'default-logo.png' },
      '/api/zhiyun-app-discovery/catalog': catalog(),
      '/api/zhiyun-data-core/health': { status: 'available', schema_version: 2, integrity: 'ok' },
      '/api/zhiyun-audit/integrity': { status: 'available', integrity: 'verified', events: 2 },
      '/api/zhiyun-data-studio/health': { status: 'available', version: '0.8.0' },
      '/api/zhiyun-order-studio/health': { status: 'available', version: '0.6.0' },
      '/api/zhiyun-integration-hub/health': { status: 'available', version: '0.1.0' },
      '/api/zhiyun-service-studio/health': { status: 'available', version: '0.1.0' },
      '/api/zhiyun-supply-studio/health': { status: 'available', version: '0.1.0' },
      '/api/zhiyun-sales-studio/health': { status: 'available', version: '0.1.0' },
      '/api/zhiyun-finance-studio/health': { status: 'available', version: '0.1.0' },
      '/api/zhiyun-people-studio/health': { status: 'available', version: '0.1.0' },
      '/api/zhiyun-chanjet-hub/health': { status: 'available', version: '0.1.0' },
      '/api/qwenpaw-creator/capabilities': { name: 'QwenPaw Creator · 视频压缩', presets: ['极速', '高速', '均衡', '高画质'], environment: { ready: true, encoders: [{ key: 'CPU H.264 / AVC (libx264)', label: 'CPU H.264 / AVC (libx264)', available: true }] } },
      '/api/agent-kanban/issues': { issues: [] },
      '/api/qwenpaw-creator-studio/health': { status: 'ok', runtime: 'creator-filesystem', dependencies: { status: 'ok' } },
      '/api/zhiyun-data-insights/health': { status: 'available', app: 'zhiyun-data-insights' },
      '/api/qwenpaw-creator-mixcut/capabilities': { name: 'QwenPaw Creator · 智能混剪', transitions: ['交叉溶解'], resolutions: ['1080p 横屏'], environment: { ready: true } },
      ...overrides,
    }
    response.end(JSON.stringify(bodies[request.url] || {}))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const { port } = server.address()
  const result = await new Promise(resolve => {
    const child = spawn(process.execPath, [healthScript, '--json'], {
      env: { ...process.env, AI_OS_URL: `http://127.0.0.1:${port}`, AI_OS_HEALTH_TIMEOUT_MS: '100' },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', chunk => { stdout += chunk })
    child.stderr.on('data', chunk => { stderr += chunk })
    child.on('exit', code => resolve({ code, stdout, stderr }))
  })
  await new Promise(resolve => server.close(resolve))
  return result
}

const healthy = await scenario()
assert.equal(healthy.code, 0, healthy.stderr || healthy.stdout)
const healthyReport = JSON.parse(healthy.stdout)
assert.equal(healthyReport.ok, true)
assert.equal(healthyReport.passed, healthyReport.checks.length)

const mismatched = await scenario({
  '/api/zhiyun-data-studio/health': { status: 'available', version: '0.6.0' },
})
assert.equal(mismatched.code, 1)
const mismatchReport = JSON.parse(mismatched.stdout)
assert.equal(mismatchReport.ok, false)
assert.ok(mismatchReport.checks.some(item => item.id === 'zhiyun-data-studio' && item.message.includes('版本')))

const hollow = await scenario({
  '/api/zhiyun-data-core/health': {},
})
assert.equal(hollow.code, 1)
const hollowReport = JSON.parse(hollow.stdout)
assert.ok(hollowReport.checks.some(item => item.id === 'zhiyun-data-core' && item.message.includes('schema_version')))

const tampered = await scenario({
  '/api/zhiyun-audit/integrity': { status: 'degraded', integrity: 'broken', line: 2 },
})
assert.equal(tampered.code, 1)
const tamperedReport = JSON.parse(tampered.stdout)
assert.ok(tamperedReport.checks.some(item => item.id === 'zhiyun-audit' && item.message.includes('完整性')))

console.log('运行健康语义回归通过：真实响应、版本漂移和空壳JSON均被正确判定。')
