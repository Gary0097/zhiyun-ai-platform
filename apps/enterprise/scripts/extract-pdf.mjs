// PDF 文本提取（单文件版）：限制流大小，避免大内容正则回溯卡死
import { readFileSync } from 'node:fs'
import { inflateSync } from 'node:zlib'

const file = process.argv[2]
const buf = readFileSync(file)
const raw = buf.toString('latin1')
const out = []
const re = /stream\r?\n?/g
let m
while ((m = re.exec(raw))) {
  const start = m.index + m[0].length
  const end = raw.indexOf('endstream', start)
  if (end < 0 || end - start > 20 * 1024 * 1024) continue
  const chunk = Buffer.from(raw.slice(start, end), 'latin1')
  try { out.push(inflateSync(chunk).toString('latin1')) } catch { out.push(chunk.toString('latin1')) }
}
const strings = []
for (const content of out) {
  if (content.length > 5 * 1024 * 1024) continue
  // 逐段简单匹配括号字符串（避免复杂正则回溯）
  for (let i = 0; i < content.length; i++) {
    if (content[i] !== '(') continue
    // 简单括号扫描（处理转义）
    let s = ''; let j = i + 1
    while (j < content.length && content[j] !== ')') {
      if (content[j] === '\\') { s += content[j] + (content[j + 1] || ''); j += 2; continue }
      s += content[j]; j++
    }
    if (j < content.length && s.trim() && s.length < 500) {
      strings.push(s.replace(/\\([nrt()\\])/g, (_, c) => ({ n: '\n', r: '', t: '', '(': '(', ')': ')', '\\': '\\' }[c] ?? '')))
    }
    i = j
  }
}
console.log(strings.join('\n').slice(0, 3000))
