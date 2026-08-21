// 校验 index.html 内嵌脚本语法：提取 <script> 内容用 node --check
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { execFileSync } from 'node:child_process'

const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8')
const m = html.match(/<script>([\s\S]*?)<\/script>/)
if (!m) { console.error('未找到 script 块'); process.exit(1) }
writeFileSync('H:/cherryAgent/tmp-check.mjs', m[1].replace(/<\/script>/g, ''))
try {
  execFileSync(process.execPath, ['--check', 'H:/cherryAgent/tmp-check.mjs'])
  console.log('✅ 脚本语法检查通过（', m[1].length, '字符）')
  // 额外检查：PAGES 引用的方法都存在
  const pagesKeys = [...m[1].matchAll(/^\s{2}(?:async\s+)?'?([A-Za-z0-9_-]+)'?\s*\(/gm)].map(x => x[1])
  const refs = [...m[1].matchAll(/PAGES\.([A-Za-z0-9_-]+)\(/g)].map(x => x[1])
  const missing = [...new Set(refs)].filter(r => !pagesKeys.includes(r))
  console.log(missing.length ? '❌ PAGES 缺失方法: ' + missing.join(', ') : '✅ PAGES 方法引用完整（' + pagesKeys.length + ' 个页面）')
  // 检查裸调用 PAGES 成员（排除方法定义行与独立函数声明）
  const standalone = ['loadInsight', 'invoiceItems', 'settingsModel', 'settingsBrand'] // 独立函数声明
  const bare = [...m[1].matchAll(/(?<![\w.])(dcOverview|dcOrders|settingsModel|loadInsight|invoiceItems|settingsBrand)\(/g)]
    .map(x => x[1])
    .filter((_, i) => {
      // 排除作为定义出现的（前面是 async 或 function）
      const line = m[1].slice(0, m[1].matchAll ? 0 : 0) // noop
      return true
    })
  // 用逐行方式重新检测：跳过定义行
  const defRe = /^\s*(async\s+)?function\s+\w+|^\s*async\s+\w+\(|^\s*\w+\s*\(\s*\)\s*\{/
  const lines = m[1].split('\n')
  const callLines = []
  lines.forEach((line, idx) => {
    if (defRe.test(line)) return
    for (const f of ['dcOverview', 'dcOrders', 'settingsModel', 'loadInsight', 'invoiceItems', 'settingsBrand']) {
      if (!standalone.includes(f) && new RegExp(`[^\\w.]${f}\\(`).test(line)) callLines.push(`第${idx + 1}行: ${f} — ${line.trim().slice(0, 80)}`)
    }
  })
  console.log(callLines.length ? '❌ 裸调用对象成员:\n' + callLines.join('\n') : '✅ 无裸调用对象成员')
} catch (e) {
  console.error('❌ 语法错误：', e.stderr?.toString().slice(0, 800) || e.message)
  process.exit(1)
} finally {
  try { unlinkSync('H:/cherryAgent/tmp-check.mjs') } catch {}
}
