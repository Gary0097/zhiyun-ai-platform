import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync, readdirSync } from 'node:fs'
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

const checkMode = process.argv.includes('--check')

function warn (message) {
  console.warn('[patch-console-ui] ' + message)
}

// In --check mode a mismatch is a hard failure so the release gate can catch upstream
// bundle updates. In normal (startup) mode console customization is cosmetic and must
// never block AI-OS startup, so we warn and exit 0 instead.
function fail (message) {
  if (checkMode) {
    console.error('[patch-console-ui] ' + message)
    process.exit(1)
  }
  warn(message + '（已跳过，不影响启动）')
  process.exit(0)
}

function hashOf (value) {
  return createHash('sha1').update(value).digest('hex').slice(0, 8)
}

// 依据项目运行环境目录推导常见 venv 布局下的 QwenPaw Console 路径，避免依赖
// “python -c import qwenpaw”。在 Windows Desktop / CLI-only 场景下运行时 Python
// 可能并不是安装了 QwenPaw 的解释器，从而导致 import 失败、误伤启动。此处的候选路径
// 覆盖 Windows（venv/Lib/site-packages）与 Linux（venv/lib/pythonX.Y/site-packages）布局。
function candidateConsoleDirs (runtime) {
  if (!runtime || !runtime.root) return []
  const root = runtime.root
  const dirs = [
    join(root, 'venv', 'Lib', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'Lib', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'venv', 'lib', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'lib', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'venv', 'lib', 'python3.13', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'venv', 'lib', 'python3.12', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'venv', 'lib', 'python3.11', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'venv', 'lib', 'python3.10', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'lib', 'python3.13', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'lib', 'python3.12', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'lib', 'python3.11', 'site-packages', 'qwenpaw', 'console'),
    join(root, 'lib', 'python3.10', 'site-packages', 'qwenpaw', 'console'),
  ]
  return [...new Set(dirs)]
}

// 递归兜底：在运行环境目录下寻找任何 <...>/qwenpaw/console/index.html，以覆盖非标准布局。
function findConsoleUnder (root, maxDepth = 8) {
  if (!root || !existsSync(root)) return null
  const stack = [{ dir: root, depth: 0 }]
  while (stack.length) {
    const { dir, depth } = stack.pop()
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const full = join(dir, entry.name)
      if (entry.name === 'console' && existsSync(join(full, 'index.html'))) return full
      if (depth < maxDepth) stack.push({ dir: full, depth: depth + 1 })
    }
  }
  return null
}

function findConsoleDir (runtime) {
  for (const dir of candidateConsoleDirs(runtime)) {
    if (existsSync(join(dir, 'index.html'))) return dir
  }
  return findConsoleUnder(runtime && runtime.root)
}

function locateConsoleDir (runtime) {
  const derived = findConsoleDir(runtime)
  if (derived) return derived
  const python = runtime && runtime.python
  if (python) {
    const res = spawnSync(python, ['-c', 'import qwenpaw, os; print(os.path.join(os.path.dirname(qwenpaw.__file__), "console"))'], { encoding: 'utf8', stdio: 'pipe' })
    if (res.status === 0) {
      const dir = (res.stdout || '').trim().split(/\r?\n/)[0]
      if (dir && existsSync(join(dir, 'index.html'))) return dir
    }
  }
  return null
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

const runtime = resolveRuntime()
const consoleDir = locateConsoleDir(runtime)

if (!consoleDir) {
  if (checkMode) {
    console.log('Console UI 定制检查跳过：未找到可用的 QwenPaw Console 目录。')
    process.exit(0)
  }
  warn('Console UI 定制跳过：未找到可用的 QwenPaw Console 目录（CLI-only 或无本地控制台），不影响启动。')
  process.exit(0)
}

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
  warn('以下目标未找到，bundle 可能已更新：' + missing.join('、'))
}
