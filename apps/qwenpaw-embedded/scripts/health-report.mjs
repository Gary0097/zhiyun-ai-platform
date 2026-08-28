const baseUrl = (process.env.AI_OS_URL || 'http://127.0.0.1:8088').replace(/\/$/, '')
const jsonOutput = process.argv.includes('--json')
const checkOnly = process.argv.includes('--check')
const timeoutMs = Number(process.env.AI_OS_HEALTH_TIMEOUT_MS || 45000)

const pawappHealthIds = [
  'zhiyun-data-studio',
  'zhiyun-order-studio',
  'zhiyun-integration-hub',
  'zhiyun-service-studio',
  'zhiyun-supply-studio',
  'zhiyun-sales-studio',
  'zhiyun-finance-studio',
  'zhiyun-people-studio',
  'zhiyun-chanjet-hub',
]

export const endpoints = [
  { id: 'qwenpaw-ui', name: '智造云 桌面', path: '/', contentType: null },
  { id: 'zhiyun-logo', name: '智造云 Logo', path: '/api/zhiyun-logo/config', contentType: 'application/json' },
  { id: 'zhiyun-app-discovery', name: '应用发现', path: '/api/zhiyun-app-discovery/catalog', contentType: 'application/json' },
  { id: 'zhiyun-data-core', name: 'Data Core', path: '/api/zhiyun-data-core/health', contentType: 'application/json' },
  { id: 'zhiyun-audit', name: '安全审计', path: '/api/zhiyun-audit/integrity', contentType: 'application/json' },
  { id: 'zhiyun-data-studio', name: 'Data Studio', path: '/api/zhiyun-data-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-order-studio', name: 'Order Studio', path: '/api/zhiyun-order-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-integration-hub', name: 'Integration Hub', path: '/api/zhiyun-integration-hub/health', contentType: 'application/json' },
  { id: 'zhiyun-service-studio', name: 'Service Studio', path: '/api/zhiyun-service-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-supply-studio', name: 'Supply Studio', path: '/api/zhiyun-supply-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-sales-studio', name: 'Sales Studio', path: '/api/zhiyun-sales-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-finance-studio', name: 'Finance Studio', path: '/api/zhiyun-finance-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-chanjet-hub', name: 'Chanjet Hub', path: '/api/zhiyun-chanjet-hub/health', contentType: 'application/json' },
  { id: 'zhiyun-people-studio', name: 'People Studio', path: '/api/zhiyun-people-studio/health', contentType: 'application/json' },
]

if (checkOnly) {
  if (endpoints.some(item => !item.path.startsWith('/'))) process.exit(1)
  if (new Set(endpoints.map(item => item.id)).size !== endpoints.length) process.exit(1)
  console.log(`运行健康检查配置通过：${endpoints.length} 个核心端点。`)
  process.exit(0)
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function validatePayload (id, payload) {
  if (id === 'zhiyun-logo') {
    return typeof payload?.logo === 'string' && payload.logo.startsWith('data:image/') && typeof payload?.source === 'string'
      ? '' : 'Logo配置缺少有效图片或来源'
  }
  if (id === 'zhiyun-app-discovery') {
    if (!Array.isArray(payload?.apps)) return '应用目录缺少apps数组'
    const required = [...pawappHealthIds, 'zhiyun-data-core', 'zhiyun-audit', 'zhiyun-logo']
    const byId = new Map(payload.apps.map(app => [app.app_id, app]))
    const missing = required.filter(id => !byId.has(id))
    if (missing.length) return `应用目录缺少：${missing.join('、')}`
    for (const id of pawappHealthIds) {
      const app = byId.get(id)
      if (app.install_status !== 'installed' || app.health !== 'available' || !app.version) return `${id}目录状态不真实`
    }
    const prdCapabilityIds = payload.apps.flatMap(app => (app.capabilities || []))
      .filter(item => !String(item.id || '').startsWith('ext_'))
      .map(item => item.id)
    if (new Set(prdCapabilityIds).size !== 31 || prdCapabilityIds.length !== 31) return `PRD能力台账应为31项，实际${prdCapabilityIds.length}项`
    return ''
  }
  if (id === 'zhiyun-data-core') {
    return payload?.status === 'available' && Number.isInteger(payload?.schema_version) && payload?.schema_version >= 2 && payload?.integrity === 'ok'
      ? '' : 'Data Core状态或schema_version异常'
  }
  if (id === 'zhiyun-audit') {
    return payload?.status === 'available' && ['verified', 'empty'].includes(payload?.integrity)
      ? '' : '审计日志完整性异常'
  }
  if (id === 'zhiyun-data-studio' || id === 'zhiyun-order-studio' || id === 'zhiyun-integration-hub' || pawappHealthIds.includes(id)) {
    return payload?.status === 'available' && typeof payload?.version === 'string' && payload.version.length > 0
      ? '' : '应用状态或版本缺失'
  }
  return ''
}

async function inspect (endpoint) {
  try {
    const response = await fetch(`${baseUrl}${endpoint.path}`, {
      signal: AbortSignal.timeout(2500),
      headers: { accept: endpoint.contentType || '*/*' },
    })
    const actualType = response.headers.get('content-type') || ''
    if (!response.ok) return { id: endpoint.id, name: endpoint.name, status: 'fail', http_status: response.status, message: `HTTP ${response.status}` }
    if (endpoint.contentType && !actualType.includes(endpoint.contentType)) {
      return { id: endpoint.id, name: endpoint.name, status: 'fail', http_status: response.status, message: `响应类型异常：${actualType || 'unknown'}` }
    }
    let payload = null
    if (endpoint.contentType === 'application/json') {
      try {
        payload = await response.json()
      } catch {
        return { id: endpoint.id, name: endpoint.name, status: 'fail', http_status: response.status, message: 'JSON响应无法解析' }
      }
      const validationError = validatePayload(endpoint.id, payload)
      if (validationError) return { id: endpoint.id, name: endpoint.name, status: 'fail', http_status: response.status, message: validationError }
    }
    return { id: endpoint.id, name: endpoint.name, status: 'pass', http_status: response.status, message: '可用', payload }
  } catch (error) {
    return { id: endpoint.id, name: endpoint.name, status: 'fail', http_status: null, message: error.message }
  }
}

function validateContracts (results) {
  const catalog = results.find(item => item.id === 'zhiyun-app-discovery')?.payload
  if (!catalog?.apps) return
  const versions = new Map(catalog.apps.map(app => [app.app_id, app.version]))
  for (const id of pawappHealthIds) {
    const result = results.find(item => item.id === id)
    if (result?.status === 'pass' && result.payload?.version !== versions.get(id)) {
      result.status = 'fail'
      result.message = `运行版本${result.payload?.version}与应用目录${versions.get(id)}不一致`
    }
  }
}

const started = Date.now()
let results = []
while (Date.now() - started < timeoutMs) {
  results = await Promise.all(endpoints.map(inspect))
  validateContracts(results)
  if (results.every(item => item.status === 'pass')) break
  await sleep(1000)
}

const publicResults = results.map(({ payload, ...item }) => item)
const failed = publicResults.filter(item => item.status === 'fail')
const report = {
  ok: failed.length === 0,
  base_url: baseUrl,
  elapsed_ms: Date.now() - started,
  passed: publicResults.length - failed.length,
  failed: failed.length,
  checks: publicResults,
}

if (jsonOutput) {
  console.log(JSON.stringify(report, null, 2))
} else {
  console.log('\nAI-OS 运行健康报告')
  for (const item of publicResults) console.log(`${item.status === 'pass' ? '✅' : '❌'} ${item.name}: ${item.message}`)
  console.log(report.ok
    ? `健康检查通过：${report.passed}/${publicResults.length} 个核心端点可用，版本与31项能力台账一致，可开始测试。\n`
    : `健康检查失败：${failed.map(item => `${item.name}（${item.message}）`).join('、')}。\n`)
}
process.exitCode = report.ok ? 0 : 1
