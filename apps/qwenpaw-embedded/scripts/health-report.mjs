const baseUrl = (process.env.AI_OS_URL || 'http://127.0.0.1:8088').replace(/\/$/, '')
const jsonOutput = process.argv.includes('--json')
const checkOnly = process.argv.includes('--check')
const timeoutMs = Number(process.env.AI_OS_HEALTH_TIMEOUT_MS || 45000)

export const endpoints = [
  { id: 'qwenpaw-ui', name: 'QwenPaw 桌面', path: '/', contentType: null },
  { id: 'zhiyun-logo', name: '智造云 Logo', path: '/api/zhiyun-logo/config', contentType: 'application/json' },
  { id: 'zhiyun-app-discovery', name: '应用发现', path: '/api/zhiyun-app-discovery/catalog', contentType: 'application/json' },
  { id: 'zhiyun-data-core', name: 'Data Core', path: '/api/zhiyun-data-core/health', contentType: 'application/json' },
  { id: 'zhiyun-data-studio', name: 'Data Studio', path: '/api/zhiyun-data-studio/health', contentType: 'application/json' },
  { id: 'zhiyun-order-studio', name: 'Order Studio', path: '/api/zhiyun-order-studio/health', contentType: 'application/json' },
]

if (checkOnly) {
  if (endpoints.some(item => !item.path.startsWith('/'))) process.exit(1)
  console.log(`运行健康检查配置通过：${endpoints.length} 个核心端点。`)
  process.exit(0)
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

async function inspect (endpoint) {
  try {
    const response = await fetch(`${baseUrl}${endpoint.path}`, {
      signal: AbortSignal.timeout(2500),
      headers: { accept: endpoint.contentType || '*/*' },
    })
    const actualType = response.headers.get('content-type') || ''
    const validType = !endpoint.contentType || actualType.includes(endpoint.contentType)
    return {
      id: endpoint.id,
      name: endpoint.name,
      status: response.ok && validType ? 'pass' : 'fail',
      http_status: response.status,
      message: !response.ok
        ? `HTTP ${response.status}`
        : (validType ? '可用' : `响应类型异常：${actualType || 'unknown'}`),
    }
  } catch (error) {
    return { id: endpoint.id, name: endpoint.name, status: 'fail', http_status: null, message: error.message }
  }
}

const started = Date.now()
let results = []
while (Date.now() - started < timeoutMs) {
  results = await Promise.all(endpoints.map(inspect))
  if (results.every(item => item.status === 'pass')) break
  await sleep(1000)
}

const failed = results.filter(item => item.status === 'fail')
const report = {
  ok: failed.length === 0,
  base_url: baseUrl,
  elapsed_ms: Date.now() - started,
  passed: results.length - failed.length,
  failed: failed.length,
  checks: results,
}

if (jsonOutput) {
  console.log(JSON.stringify(report, null, 2))
} else {
  console.log('\nAI-OS 运行健康报告')
  for (const item of results) {
    console.log(`${item.status === 'pass' ? '✅' : '❌'} ${item.name}: ${item.message}`)
  }
  console.log(report.ok
    ? `健康检查通过：${report.passed}/${results.length} 个核心端点可用，可开始测试。\n`
    : `健康检查失败：${failed.map(item => item.name).join('、')} 不可用；请保留启动日志并运行诊断。\n`)
}
process.exitCode = report.ok ? 0 : 1
