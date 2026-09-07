// 生成单文件 HTML 使用说明书：读取 docs/user-manual/README.md，
// 转换为本仓库文档用到的 Markdown 子集（标题/表格/图片/列表/引用/行内样式），
// 图片以 base64 内嵌，产出可直接分发的独立 HTML。
// 用法：node scripts/make-user-manual-html.mjs
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const mdPath = join(root, 'docs', 'user-manual', 'README.md')
const imgDir = join(root, 'docs', 'user-manual')
const outPath = join(root, 'docs', 'user-manual', '灵泽万川智造云-AI-OS-使用说明书.html')

const md = readFileSync(mdPath, 'utf8')

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

function inline (s) {
  s = esc(s)
  s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (m, alt, p) => {
    const file = join(imgDir, p)
    if (!existsSync(file)) return `<span class="missing">[缺图: ${p}]</span>`
    const b64 = readFileSync(file).toString('base64')
    return `<img src="data:image/png;base64,${b64}" alt="${alt}">`
  })
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, t, u) => {
    const external = /^https?:/.test(u)
    return `<a href="${u}"${external ? ' target="_blank" rel="noreferrer"' : ''}>${t}</a>`
  })
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  return s
}

const lines = md.split(/\r?\n/)
const out = []
let i = 0
while (i < lines.length) {
  const line = lines[i]
  if (/^```/.test(line)) { // 代码块
    const buf = []
    i++
    while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++])
    i++
    out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`)
    continue
  }
  if (/^\|/.test(line) && i + 1 < lines.length && /^\|[\s:-]+\|/.test(lines[i + 1].replace(/[^|\s:-]/g, '').length ? lines[i + 1] : '')) {
    // 表格：第二行是分隔行
    const header = line
    if (/^\|[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      const cells = h => h.replace(/^\||\|\s*$/g, '').split('|').map(c => c.trim())
      const ths = cells(header).map(c => `<th>${inline(c)}</th>`).join('')
      i += 2
      const rows = []
      while (i < lines.length && /^\|/.test(lines[i])) {
        rows.push('<tr>' + cells(lines[i]).map(c => `<td>${inline(c)}</td>`).join('') + '</tr>')
        i++
      }
      out.push(`<table><thead><tr>${ths}</tr></thead><tbody>${rows.join('')}</tbody></table>`)
      continue
    }
  }
  const h = /^(#{1,4})\s+(.*)$/.exec(line)
  if (h) {
    if (h[1] === '#') out.push(`<h1>${inline(h[2])}</h1>`)
    else {
      const level = h[1].length
      const anchor = h[2].replace(/[^\p{L}\p{N}\s-]/gu, '').trim().replace(/\s+/g, '-')
      out.push(`<h${level} id="${anchor}">${inline(h[2])}</h${level}>`)
    }
    i++
    continue
  }
  if (/^---+\s*$/.test(line)) { out.push('<hr>'); i++; continue }
  if (/^>\s?/.test(line)) {
    const buf = []
    while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ''))
    out.push(`<blockquote>${buf.map(b => inline(b)).join('<br>')}</blockquote>`)
    continue
  }
  if (/^\s*[-*]\s+/.test(line)) {
    const items = []
    while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ''))
    out.push(`<ul>${items.map(it => `<li>${inline(it)}</li>`).join('')}</ul>`)
    continue
  }
  if (/^\s*\d+\.\s+/.test(line)) {
    const items = []
    while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s+/, ''))
    out.push(`<ol>${items.map(it => `<li>${inline(it)}</li>`).join('')}</ol>`)
    continue
  }
  if (line.trim() === '') { i++; continue }
  // 普通段落（连续非空行合并）
  const buf = [line]
  i++
  while (i < lines.length && lines[i].trim() !== '' && !/^(#{1,4}\s|```|\||>\s?|\s*[-*]\s|\s*\d+\.\s|---+\s*$)/.test(lines[i])) {
    buf.push(lines[i]); i++
  }
  out.push(`<p>${buf.map(b => inline(b)).join('<br>')}</p>`)
}

const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>灵泽万川智造云 AI-OS 使用说明书</title>
<style>
  body { font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif; max-width: 960px; margin: 0 auto; padding: 24px 20px 80px; color: #1f2328; line-height: 1.75; }
  h1 { font-size: 28px; border-bottom: 2px solid #2f6bff; padding-bottom: 10px; }
  h2 { font-size: 21px; margin-top: 40px; border-left: 4px solid #2f6bff; padding-left: 10px; }
  h3 { font-size: 17px; margin-top: 26px; }
  img { max-width: 100%; border: 1px solid #d8dee4; border-radius: 6px; margin: 8px 0; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
  th, td { border: 1px solid #d8dee4; padding: 7px 10px; text-align: left; vertical-align: top; }
  th { background: #f2f6ff; }
  tr:nth-child(even) td { background: #fafbfc; }
  code { background: #f0f2f5; border-radius: 4px; padding: 1px 5px; font-size: 13px; }
  pre code { display: block; padding: 12px; overflow-x: auto; }
  blockquote { border-left: 4px solid #ffb02e; background: #fffaf0; margin: 12px 0; padding: 8px 14px; }
  a { color: #2f6bff; }
  hr { border: none; border-top: 1px solid #d8dee4; margin: 28px 0; }
  .missing { color: #c00; }
</style>
</head>
<body>
${out.join('\n')}
</body>
</html>`

writeFileSync(outPath, html, 'utf8')
const imgs = (html.match(/data:image\/png;base64,/g) || []).length
console.log(`生成 ${outPath}`)
console.log(`大小 ${(html.length / 1024 / 1024).toFixed(2)} MB，内嵌图片 ${imgs} 张`)
