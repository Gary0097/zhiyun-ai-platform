import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveRuntime } from './runtime-env.mjs'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const assetsRoot = join(scriptsRoot, '..', '..', '..', 'plugins', 'zhiyun-logo', 'assets')
const gearLogo = join(assetsRoot, 'gear-logo.png')

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
    name: '欢迎页智能体头像（online.svg → qwenpaw.svg）',
    from: 'avatar:"/online.svg"',
    to: 'avatar:"/qwenpaw.svg"',
    patched: 'avatar:"/qwenpaw.svg"',
  },
  {
    name: '默认中文语言',
    from: 'lng:localStorage.getItem("language")||navigator.language||"en"',
    to: 'lng:localStorage.getItem("language")||"zh"',
    patched: 'lng:localStorage.getItem("language")||"zh"',
  },
]

const PROTECTED = [
  'window.QwenPaw',
  'QwenPaw.app',
  'agentscope-ai/QwenPaw',
  'QwenPawRichFile',
  '[QwenPaw audit]',
  '[QwenPaw registry]',
  '[QwenPaw]',
  'cd QwenPaw',
]

// 将用户可见的 QwenPaw 品牌文案替换为“制造云”，同时保护技术标识、URL、日志前缀与
// 操作命令，避免破坏 host API / 仓库地址 / macOS 路径 / 审计日志。
function applyBrand (content) {
  const tokens = PROTECTED.slice().sort((a, b) => b.length - a.length)
  const placeholders = []
  let out = content
  for (const t of tokens) {
    if (!out.includes(t)) continue
    const ph = '\u0001QWP\u0001' + placeholders.length + '\u0001'
    placeholders.push({ ph, t })
    out = out.split(t).join(ph)
  }
  out = out.split('QwenPaw').join('制造云')
  for (const { ph, t } of placeholders) out = out.split(ph).join(t)
  return out
}

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

function workingDir () {
  const explicit = process.env.QWENPAW_WORKING_DIR || process.env.COPAW_WORKING_DIR
  if (explicit) return resolve(explicit)
  const current = join(homedir(), '.qwenpaw')
  const legacy = join(homedir(), '.copaw')
  return !existsSync(current) && existsSync(legacy) ? legacy : current
}

function selectedLogo () {
  const branding = join(workingDir(), 'branding')
  const configPath = join(branding, 'logo.json')
  const allowedMime = new Set(['image/png', 'image/jpeg', 'image/svg+xml', 'image/webp'])
  try {
    const config = JSON.parse(readFileSync(configPath, 'utf8'))
    const path = resolve(String(config.path || ''))
    const mime = String(config.mime || '')
    if (dirname(path) === resolve(branding) && allowedMime.has(mime) && existsSync(path) && statSync(path).isFile() && statSync(path).size > 0) {
      return { path, mime, source: 'Workspace 自定义 Logo' }
    }
  } catch {}
  return { path: gearLogo, mime: 'image/png', source: '内置制造云齿轮 Logo' }
}

function logoSvg (logo) {
  const encoded = readFileSync(logo.path).toString('base64')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><image href="data:${logo.mime};base64,${encoded}" width="512" height="512" preserveAspectRatio="xMidYMid meet"/></svg>\n`
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

function collectBrandableFiles (root) {
  const files = []
  const stack = [root]
  while (stack.length) {
    const dir = stack.pop()
    let entries
    try { entries = readdirSync(dir, { withFileTypes: true }) } catch { continue }
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) { stack.push(full); continue }
      if (entry.name.endsWith('.js') || entry.name.endsWith('.html')) files.push(full)
    }
  }
  return files
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

// 移除 index.html 主 bundle src 上的 ?v= 查询参数。
// QwenPaw console 的懒加载块（如 ACPDrawer）会以不带查询参数的原路径动态 import 入口
// chunk；若 index.html 入口带 ?v=，两者会成为不同的模块标识，导致整个 console 执行两次
// （登录层/PluginLoader/引导浮层全部翻倍，且应用容器互相遮挡）。资源服务端已带 ETag，
// 去掉 ?v= 后浏览器仍会按 ETag 重验证，不会长期吃陈旧缓存。
function ensureCacheBust (consoleDir, bundleContent) {
  const htmlPath = join(consoleDir, 'index.html')
  const html = readFileSync(htmlPath, 'utf8')
  const re = /(src="\/assets\/index-[^"?\s]+\.js)\?v=[^"]*(")/
  if (!re.test(html)) return { changed: false }
  const newHtml = html.replace(re, '$1$2')
  if (newHtml === html) return { changed: false }
  writeFileSync(htmlPath, newHtml, 'utf8')
  return { changed: true }
}

// 同步浏览器 favicon 与聊天智能体头像为当前平台 Logo。
// console 目录被 .gitignore 忽略，因此资源必须于启动时从受控目录复制，
// 否则升级或重新安装运行时后会回退为上游默认图标。
function syncConsoleLogo (consoleDir) {
  if (!existsSync(gearLogo)) {
    fail('受控齿轮 LOGO 资源缺失：' + gearLogo)
  }
  const logo = selectedLogo()
  const svgTarget = join(consoleDir, 'qwenpaw.svg')
  writeFileSync(svgTarget, logoSvg(logo), 'utf8')
  const htmlPath = join(consoleDir, 'index.html')
  const html = readFileSync(htmlPath, 'utf8')
  const nextHtml = html.replace(/<link rel="icon"[^>]*\/>/, '<link rel="icon" type="image/svg+xml" href="/qwenpaw.svg" />')
  if (nextHtml !== html) {
    writeFileSync(htmlPath, nextHtml, 'utf8')
  }
  console.log(`Console favicon 与聊天智能体头像已同步为${logo.source}。`)
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
content = content.split('avatar:"/qwenpaw.png"').join('avatar:"/qwenpaw.svg"')
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

const branded = applyBrand(content)

if (checkMode) {
  if (missing.length) {
    console.error('[patch-console-ui] 检查失败：console bundle 中未找到以下目标：' + missing.join('、') + '。bundle 可能已随上游升级更新。')
    process.exit(1)
  }
  if (branded !== content) {
    console.error('[patch-console-ui] 检查失败：console bundle 中仍存在未替换的 QwenPaw 品牌文案（应替换为 制造云）。')
    process.exit(1)
  }
  // 校验所有可打补丁的 JS/HTML 资源文件均已替换 QwenPaw 品牌文案。
  const unpatchedFiles = []
  for (const file of collectBrandableFiles(consoleDir)) {
    const cc = readFileSync(file, 'utf8')
    if (cc.includes('QwenPaw') && applyBrand(cc) !== cc) unpatchedFiles.push(file)
  }
  if (unpatchedFiles.length) {
    console.error('[patch-console-ui] 检查失败：以下文件仍包含未替换的 QwenPaw 品牌文案（应替换为 制造云）：\n' + unpatchedFiles.join('\n'))
    process.exit(1)
  }
  const htmlTitle = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  if (htmlTitle.includes('QwenPaw')) {
    console.error('[patch-console-ui] 检查失败：index.html 仍包含 QwenPaw 品牌标题（应替换为 制造云）。')
    process.exit(1)
  }
  const html = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  const bundleName = bundlePath.split(/[\\/]/).pop()
  const expected = 'src="/assets/' + bundleName + '"'
  if (!html.includes(expected)) {
    console.error('[patch-console-ui] 检查失败：index.html 未以原路径（不带 ?v= 查询参数）引用主 bundle。带 ?v= 会与懒加载块的动态 import 形成双重模块标识，导致 console 执行两次。')
    process.exit(1)
  }
  if (!existsSync(gearLogo) || statSync(gearLogo).size === 0) {
    console.error('[patch-console-ui] 检查失败：受控齿轮 LOGO 资源缺失：' + gearLogo)
    process.exit(1)
  }
  const consoleSvg = join(consoleDir, 'qwenpaw.svg')
  if (!existsSync(consoleSvg) || statSync(consoleSvg).size === 0) {
    console.error('[patch-console-ui] 检查失败：console 缺少 qwenpaw.svg（未同步当前平台 Logo）。')
    process.exit(1)
  }
  const expectedLogo = logoSvg(selectedLogo())
  if (readFileSync(consoleSvg, 'utf8') !== expectedLogo) {
    console.error('[patch-console-ui] 检查失败：console Logo 与 Workspace 当前配置不一致。')
    process.exit(1)
  }
  const faviconHtml = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  if (!faviconHtml.includes('type="image/svg+xml"') || !faviconHtml.includes('qwenpaw.svg')) {
    console.error('[patch-console-ui] 检查失败：index.html favicon 未指向当前平台 Logo。')
    process.exit(1)
  }
  console.log('Console UI 定制检查通过：' + bundlePath)
  process.exit(0)
}

content = branded

if (content !== original) {
  writeFileSync(bundlePath, content, 'utf8')
  console.log('Console UI 定制已应用：' + bundlePath)
} else {
  console.log('Console UI 定制已是最新状态：' + bundlePath)
}

const cacheBust = ensureCacheBust(consoleDir, content)
if (cacheBust.changed) {
  console.log('Console index.html 已移除主 bundle ?v= 查询参数（避免 console 双重执行）')
}
syncConsoleLogo(consoleDir)

// 对其它 Console 资源（懒加载 chunk / vendor）执行同样的品牌替换。
let extraBranded = 0
for (const file of collectBrandableFiles(consoleDir)) {
  if (file === bundlePath) continue
  const cc = readFileSync(file, 'utf8')
  if (!cc.includes('QwenPaw')) continue
  const out = applyBrand(cc)
  if (out !== cc) {
    writeFileSync(file, out, 'utf8')
    extraBranded++
  }
}
if (extraBranded) console.log('已更新 ' + extraBranded + ' 个额外 Console 资源文件品牌文案。')

if (missing.length) {
  warn('以下目标未找到，bundle 可能已更新：' + missing.join('、'))
}
