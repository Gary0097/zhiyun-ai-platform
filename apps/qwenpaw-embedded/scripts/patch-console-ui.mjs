import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveRuntime } from './runtime-env.mjs'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))

const REPLACEMENTS = [
  {
    name: '文档资料下拉菜单（桌面）',
    from: 'v.length>0&&p.jsx(Gh,{menu:{items:v},children:p.jsxs(Zt,{type:"text",className:Rn.hideOnMobile,children:[i("header.resources")," ",p.jsx(b4,{})]})})',
    to: 'false&&p.jsx(Gh,{menu:{items:v},children:p.jsxs(Zt,{type:"text",className:Rn.hideOnMobile,children:[i("header.resources")," ",p.jsx(b4,{})]})})',
    patched: 'false&&p.jsx(Gh,{menu:{items:v}',
  },
  {
    name: 'GitHub 按钮',
    from: 'p.jsx(Ci,{title:i("header.github"),children:p.jsx(Zt,{type:"text",icon:p.jsx(she,{}),onClick:()=>L(rge),className:Rn.hideOnMobile,children:i("header.github")})})',
    to: 'false&&p.jsx(Ci,{title:i("header.github"),children:p.jsx(Zt,{type:"text",icon:p.jsx(she,{}),onClick:()=>L(rge),className:Rn.hideOnMobile,children:i("header.github")})})',
    patched: 'false&&p.jsx(Ci,{title:i("header.github")',
  },
  {
    name: '文档资料下拉菜单（移动端）',
    from: 'p.jsx(Gh,{menu:{items:y},placement:"bottomRight",children:p.jsx(Zt,{type:"text",icon:p.jsx(ihe,{}),className:Rn.showOnMobile,title:i("header.resources")})})',
    to: 'false&&p.jsx(Gh,{menu:{items:y},placement:"bottomRight",children:p.jsx(Zt,{type:"text",icon:p.jsx(ihe,{}),className:Rn.showOnMobile,title:i("header.resources")})})',
    patched: 'false&&p.jsx(Gh,{menu:{items:y}',
  },
  {
    name: '默认中文语言',
    from: 'lng:localStorage.getItem("language")||navigator.language||"en"',
    to: 'lng:localStorage.getItem("language")||"zh"',
    patched: 'lng:localStorage.getItem("language")||"zh"',
  },
]

function fail (message) {
  console.error('[patch-console-ui] ' + message)
  process.exit(1)
}

function hashOf (value) {
  return createHash('sha1').update(value).digest('hex').slice(0, 8)
}

function locateConsoleDir (runtime) {
  const python = runtime && runtime.python
  if (!python) fail('无法定位 Python 运行环境，不能定制 Console 页面。')
  const res = spawnSync(python, ['-c', 'import qwenpaw, os; print(os.path.join(os.path.dirname(qwenpaw.__file__), "console"))'], { encoding: 'utf8', stdio: 'pipe' })
  if (res.status !== 0) fail('无法定位 QwenPaw Console 目录：' + ((res.stderr || '').trim()))
  const dir = (res.stdout || '').trim().split(/\r?\n/)[0]
  if (!dir || !existsSync(join(dir, 'index.html'))) fail('QwenPaw Console 目录无效：' + dir)
  return dir
}

function findMainBundle (consoleDir) {
  const html = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  const m = html.match(/src="\/assets\/(index-[^"?\s]+\.js)(?:\?v=[^"]*)?"/)
  if (!m) fail('无法在 console index.html 中找到主 bundle。')
  const bundlePath = join(consoleDir, 'assets', m[1])
  if (!existsSync(bundlePath)) fail('Console 主 bundle 不存在：' + bundlePath)
  return bundlePath
}

function findUnpatched (content, from, patched) {
  if (content.includes(patched)) return -1
  let idx = content.indexOf(from)
  while (idx !== -1) {
    const before = content.slice(idx - 7, idx)
    if (before !== 'false&&') return idx
    idx = content.indexOf(from, idx + 1)
  }
  return -1
}

// 给 index.html 中的主 bundle src 追加基于内容的版本号，用于强制浏览器重新拉取已打补丁的 bundle，
// 避免因 bundle 文件名哈希不变导致的陈旧缓存。
function ensureCacheBust (consoleDir, bundleContent) {
  const htmlPath = join(consoleDir, 'index.html')
  const html = readFileSync(htmlPath, 'utf8')
  const version = hashOf(bundleContent)
  const re = /(src="\/assets\/index-[^"?\s]+\.js)(?:\?v=[^"]*)?(")/
  if (!re.test(html)) return { changed: false }
  const newHtml = html.replace(re, '$1?v=' + version + '$2')
  if (newHtml === html) return { changed: false }
  writeFileSync(htmlPath, newHtml, 'utf8')
  return { changed: true }
}

const checkMode = process.argv.includes('--check')
const runtime = resolveRuntime()
const consoleDir = locateConsoleDir(runtime)
const bundlePath = findMainBundle(consoleDir)
const original = readFileSync(bundlePath, 'utf8')
let content = original
const missing = []

for (const r of REPLACEMENTS) {
  if (content.includes(r.patched)) continue
  const idx = findUnpatched(content, r.from, r.patched)
  if (idx !== -1) {
    content = content.slice(0, idx) + r.to + content.slice(idx + r.from.length)
  } else {
    missing.push(r.name)
  }
}

if (checkMode) {
  if (missing.length) {
    console.error('[patch-console-ui] 检查失败：console bundle 中未找到以下目标：' + missing.join('、') + '。bundle 可能已随上游升级更新。')
    process.exit(1)
  }
  const html = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  const bundleName = bundlePath.split(/[\\/]/).pop()
  const expected = 'src="/assets/' + bundleName + '?v=' + hashOf(content) + '"'
  if (!html.includes(expected)) {
    console.error('[patch-console-ui] 检查失败：index.html 未引用已打补丁的 bundle 版本（' + expected + '）。请重新运行以应用缓存失效。')
    process.exit(1)
  }
  console.log('Console UI 定制检查通过：' + bundlePath)
  process.exit(0)
}

if (content !== original) {
  writeFileSync(bundlePath, content, 'utf8')
  console.log('Console UI 定制已应用：' + bundlePath)
} else {
  console.log('Console UI 定制已是最新状态：' + bundlePath)
}

const cacheBust = ensureCacheBust(consoleDir, content)
if (cacheBust.changed) {
  console.log('Console index.html 缓存失效已更新（?v=' + hashOf(content) + '）')
}

if (missing.length) {
  console.warn('[patch-console-ui] 警告：以下目标未找到，bundle 可能已更新：' + missing.join('、'))
}
