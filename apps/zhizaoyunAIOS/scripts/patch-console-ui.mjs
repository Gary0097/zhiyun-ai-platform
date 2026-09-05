import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { brotliCompressSync, gzipSync } from 'node:zlib'
import { existsSync, readFileSync, writeFileSync, readdirSync, renameSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveRuntime } from './runtime-env.mjs'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const assetsRoot = join(scriptsRoot, '..', '..', '..', 'branding')
const gearLogo = join(assetsRoot, 'gear-logo.png')
const brandLogo = join(assetsRoot, 'brand-logo.png')
const defaultLogo = join(assetsRoot, 'default-logo.png')

const REPLACEMENTS = [
  {
    name: '文档资料下拉菜单（桌面）',
    optional: true,
    from: 'v.length>0&&p.jsx(Gh,{menu:{items:v},children:p.jsxs(Zt,{type:"text",className:Rn.hideOnMobile,children:[i("header.resources")," ",p.jsx(b4,{})]})})',
    to: 'false&&p.jsx(Gh,{menu:{items:v},children:p.jsxs(Zt,{type:"text",className:Rn.hideOnMobile,children:[i("header.resources")," ",p.jsx(b4,{})]})})',
    patched: 'false&&p.jsx(Gh,{menu:{items:v}',
  },
  {
    name: 'GitHub 按钮',
    optional: true,
    from: 'p.jsx(Ci,{title:i("header.github"),children:p.jsx(Zt,{type:"text",icon:p.jsx(she,{}),onClick:()=>L(rge),className:Rn.hideOnMobile,children:i("header.github")})})',
    to: 'false&&p.jsx(Ci,{title:i("header.github"),children:p.jsx(Zt,{type:"text",icon:p.jsx(she,{}),onClick:()=>L(rge),className:Rn.hideOnMobile,children:i("header.github")})})',
    patched: 'false&&p.jsx(Ci,{title:i("header.github")',
  },
  {
    name: '文档资料下拉菜单（移动端）',
    optional: true,
    from: 'p.jsx(Gh,{menu:{items:y},placement:"bottomRight",children:p.jsx(Zt,{type:"text",icon:p.jsx(ihe,{}),className:Rn.showOnMobile,title:i("header.resources")})})',
    to: 'false&&p.jsx(Gh,{menu:{items:y},placement:"bottomRight",children:p.jsx(Zt,{type:"text",icon:p.jsx(ihe,{}),className:Rn.showOnMobile,title:i("header.resources")})})',
    patched: 'false&&p.jsx(Gh,{menu:{items:y}',
  },
  {
    name: '欢迎页智能体头像（online.svg → qwenpaw.svg）',
    optional: true,
    from: 'avatar:"/online.svg"',
    to: 'avatar:"/qwenpaw.svg"',
    patched: 'avatar:"/qwenpaw.svg"',
  },
  // ---- QwenPaw 2.2.0 bundle（index-C6K6UUCj.js）----
  {
    name: '2.2.0 文档菜单 → 本地内嵌文档',
    optional: true,
    from: 'UM=e=>`https://qwenpaw.agentscope.io/docs/intro?lang=${Mo(e)}`',
    to: 'UM=e=>"/aios-docs.html#tutorial"',
    patched: 'UM=e=>"/aios-docs.html#tutorial"',
  },
  {
    name: '2.2.0 功能演示 → 本地内嵌文档（视频教程待开发）',
    optional: true,
    from: 'GM=e=>`https://qwenpaw.agentscope.io/docs/functiondemo?lang=${Mo(e)}`',
    to: 'GM=e=>"/aios-docs.html#demo"',
    patched: 'GM=e=>"/aios-docs.html#demo"',
  },
  {
    name: '2.2.0 更新日志 → 本地内嵌文档',
    optional: true,
    from: 'pd=e=>`https://qwenpaw.agentscope.io/release-notes?lang=${Mo(e)}`',
    to: 'pd=e=>"/aios-docs.html#changelog"',
    patched: 'pd=e=>"/aios-docs.html#changelog"',
  },
  {
    name: '2.2.0 常见问题 → 本地内嵌文档',
    optional: true,
    from: 'jM=e=>`https://qwenpaw.agentscope.io/docs/faq?lang=${Mo(e)}`',
    to: 'jM=e=>"/aios-docs.html#faq"',
    patched: 'jM=e=>"/aios-docs.html#faq"',
  },
  {
    name: '2.2.0 GitHub 按钮隐藏',
    optional: true,
    from: 'c.jsx(mt,{title:e("header.github"),children:c.jsx(ct,{type:"text",icon:c.jsx(Js,{}),onClick:()=>L(ud),className:F.hideOnMobile,children:e("header.github")})})',
    to: 'false&&c.jsx(mt,{title:e("header.github"),children:c.jsx(ct,{type:"text",icon:c.jsx(Js,{}),onClick:()=>L(ud),className:F.hideOnMobile,children:e("header.github")})})',
    patched: 'false&&c.jsx(mt,{title:e("header.github")',
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
  'QwenPaw Desktop',
  'QwenPaw-Tauri',
  'QwenPaw-Flash',
  'QwenPaw_QA',
  'QwenPawQA',
]

// 将用户可见的 QwenPaw 品牌文案替换为“智造云 AIOS”，同时保护技术标识、URL、日志前缀与
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
  out = out.split('QwenPaw').join('智造云AIOS')
  // 旧品牌名归一：bundle 可能已按历史品牌（灵泽万川智造云）打过补丁，
  // 重品牌化时一并替换，保证跨版本幂等
  out = out.split('灵泽万川智造云').join('智造云AIOS')
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

// uv 以硬链接方式安装包文件，直接 writeFileSync 会连 uv 缓存里的原始副本一起改写，
// 之后任何重装都会把“已定制”的旧内容带回来（曾导致 制造云 旧品牌在重装后复活）。
// Windows 上 Node 的 statSync().nlink 不可靠（硬链接也可能报 1），无法据此
// 判断，因此一律走“临时文件 + rename 原子替换”：每次写入都落成新文件，
// 从物理上保证绝不写穿 uv 缓存里的硬链接副本。
function writeIndependent (file, data) {
  const tmp = file + '.zy-tmp'
  writeFileSync(tmp, data)
  renameSync(tmp, file)
}

// 写入静态资产并同步刷新同名的 .br / .gz 预压缩副本。console 静态服务支持
// Content-Encoding 协商，若只改原文件，旧压缩副本仍会被优先返回，导致改动“看不见”。
function writeAssetWithSiblings (file, data) {
  writeIndependent(file, data)
  for (const ext of ['.br', '.gz']) {
    const sibling = file + ext
    if (!existsSync(sibling)) continue
    const compressed = ext === '.br'
      ? brotliCompressSync(data)
      : gzipSync(data)
    writeIndependent(sibling, compressed)
  }
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
  // 默认使用灵泽万川品牌 Logo（上传版优先，其次旧字标）；缺失时回退齿轮 Logo。
  for (const [path, source] of [[brandLogo, '内置灵泽万川品牌 Logo（上传版）'], [defaultLogo, '内置灵泽万川品牌 Logo'], [gearLogo, '内置智造云 AIOS 齿轮 Logo']]) {
    if (existsSync(path) && statSync(path).size > 0) return { path, mime: 'image/png', source }
  }
  return { path: gearLogo, mime: 'image/png', source: '内置智造云 AIOS 齿轮 Logo' }
}

// 读取 PNG IHDR 的真实宽高，让生成的 SVG 保持 Logo 原始纵横比。
// 若统一用 512x512 方形 viewBox，横版字标会被大块透明边距居中，
// 在顶栏/头像等方形上下文里显得极小（曾导致“Logo 看不见/被压扁”）。
function pngSize (file) {
  const buf = readFileSync(file)
  if (buf.length > 24 && buf[12] === 0x49 && buf[13] === 0x48 && buf[14] === 0x44 && buf[15] === 0x52) {
    return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }
  }
  return { w: 512, h: 512 }
}

function logoSvg (logo) {
  const encoded = readFileSync(logo.path).toString('base64')
  const { w, h } = logo.mime === 'image/png' ? pngSize(logo.path) : { w: 512, h: 512 }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}"><image href="data:${logo.mime};base64,${encoded}" width="${w}" height="${h}"/></svg>\n`
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
  writeAssetWithSiblings(htmlPath, newHtml)
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
  writeIndependent(svgTarget, logoSvg(logo))
  // 启动页（boot screen）Logo：index.html 中 .qwenpaw-boot__logo 直接引用根路径
  // /qwenpaw.png，需要用当前平台 Logo 物理覆盖该文件（仅位图 Logo 可安全写入 .png）。
  const rasterMime = new Set(['image/png', 'image/jpeg', 'image/webp'])
  if (rasterMime.has(logo.mime)) {
    writeAssetWithSiblings(join(consoleDir, 'qwenpaw.png'), readFileSync(logo.path))
  }
  else {
    // SVG 自定义 Logo 无法写入 .png：把启动页 img 改指同步生成的 /qwenpaw.svg
    const bootHtmlPath = join(consoleDir, 'index.html')
    let bootHtml = readFileSync(bootHtmlPath, 'utf8')
    if (bootHtml.includes('src="/qwenpaw.png"')) {
      bootHtml = bootHtml.split('src="/qwenpaw.png"').join('src="/qwenpaw.svg"')
      writeAssetWithSiblings(bootHtmlPath, bootHtml)
      console.log('Console 启动页 Logo 已改为 SVG 引用（自定义 Logo 为 SVG）。')
    }
  }
  // 其余上游默认 Logo 资产（登录页 logo-dark/light.svg、creator-logo.png 等）一并
  // 覆盖为当前平台 Logo，避免任何残留的 QwenPaw 黡标识。
  const svgLogo = logoSvg(logo)
  for (const name of readdirSync(consoleDir)) {
    if (/^logo-(dark|light)\.svg$/.test(name)) {
      writeAssetWithSiblings(join(consoleDir, name), svgLogo)
    } else if (name === 'creator-logo.png' && rasterMime.has(logo.mime)) {
      writeAssetWithSiblings(join(consoleDir, name), readFileSync(logo.path))
    }
  }
  const htmlPath = join(consoleDir, 'index.html')
  const html = readFileSync(htmlPath, 'utf8')
  const nextHtml = html.replace(/<link rel="icon"[^>]*\/>/, '<link rel="icon" type="image/svg+xml" href="/qwenpaw.svg" />')
  if (nextHtml !== html) {
    writeAssetWithSiblings(htmlPath, nextHtml)
  }
  console.log(`Console favicon、启动页 Logo 与默认 Logo 资产已同步为${logo.source}。`)
}

// 注入灵泽万川蓝绿主题。console 全站配色由 .css-var-r0 上的 antd CSS 变量驱动
// （上游主色为橙色 --qwenpaw-color-primary:#ff7f16），因此用更高优先级的选择器
// 覆盖主色系变量 + 登录页背景/Logo 尺寸，实现整体换肤。
// 主题可通过 Workspace 的 branding/theme.json 自定义：
// { "primary": "#0086AD", "primaryHover": "#00A3C4", "primaryActive": "#00688A",
//   "loginLogoHeight": 88, "loginBg": "cover.png"（branding 目录内的图片文件名） }
const THEME_DEFAULTS = { primary: '#0086AD', primaryHover: '#00A3C4', primaryActive: '#00688A', loginLogoHeight: 88, loginBg: '' }
function brandTheme () {
  const branding = join(workingDir(), 'branding')
  try {
    const cfg = JSON.parse(readFileSync(join(branding, 'theme.json'), 'utf8'))
    const hex = v => typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v) ? v : null
    const theme = {
      primary: hex(cfg.primary) || THEME_DEFAULTS.primary,
      primaryHover: hex(cfg.primaryHover) || THEME_DEFAULTS.primaryHover,
      primaryActive: hex(cfg.primaryActive) || THEME_DEFAULTS.primaryActive,
      loginLogoHeight: Number.isFinite(cfg.loginLogoHeight) && cfg.loginLogoHeight >= 32 && cfg.loginLogoHeight <= 240 ? cfg.loginLogoHeight : THEME_DEFAULTS.loginLogoHeight,
      loginBg: ''
    }
    if (typeof cfg.loginBg === 'string' && cfg.loginBg && !cfg.loginBg.includes('..')) {
      const p = join(branding, cfg.loginBg)
      if (existsSync(p) && statSync(p).size > 0) theme.loginBg = p
    }
    return theme
  } catch {}
  return { ...THEME_DEFAULTS }
}

function themeCss (theme) {
  const p = theme.primary, h = theme.primaryHover, a = theme.primaryActive
  // 由主色推导的浅色底/描边（保持 antd 层级关系）
  const bg = '#E8F5F9', bgHover = '#CDEAF2', border = '#8FD1E0', borderHover = '#5FBBD0'
  const lines = [
    `:root{--zy-brand:${p};}`,
    `:root,html .css-var-r0{`,
    `--qwenpaw-color-primary:${p};--qwenpaw-color-primary-hover:${h};--qwenpaw-color-primary-active:${a};`,
    `--qwenpaw-color-primary-bg:${bg};--qwenpaw-color-primary-bg-hover:${bgHover};`,
    `--qwenpaw-color-primary-border:${border};--qwenpaw-color-primary-border-hover:${borderHover};`,
    `--qwenpaw-color-primary-text:${p};--qwenpaw-color-primary-text-hover:${h};--qwenpaw-color-primary-text-active:${a};`,
    `--qwenpaw-color-link:${p};--qwenpaw-color-link-hover:${h};--qwenpaw-color-link-active:${a};`,
    `--qwenpaw-input-active-border-color:${p};--qwenpaw-input-hover-border-color:${h};`,
    `--qwenpaw-input-active-shadow:0 0 0 2px ${p}1a;--qwenpaw-control-outline:${p}1a;`,
    `--qwenpaw-control-item-bg-active:${bg};--qwenpaw-control-item-bg-active-hover:${bgHover};`,
    `--qwenpaw-button-group-border-color:${p};}`,
    `a{color:${p};}`,
    // 登录页 Logo 放大（上游内联 48px）
    `img[style*="height: 48px"]{height:${theme.loginLogoHeight}px !important;width:auto !important;}`,
    // 顶栏 Logo 放大（上游 16px 的 CSS Module 类，按类名片段匹配以跨哈希稳定命中）
    `img[class*="logoImg"]{height:32px !important;width:auto !important;max-width:none !important;}`,
  ]
  if (theme.loginBg) {
    const data = 'data:image/' + (theme.loginBg.endsWith('.png') ? 'png' : 'jpeg') + ';base64,' + readFileSync(theme.loginBg).toString('base64')
    lines.push(`div[style*="245, 247, 250"],div[style*="245,247,250"]{background:url("${data}") center/cover no-repeat !important;}`)
  } else {
    lines.push(`div[style*="245, 247, 250"],div[style*="245,247,250"]{background:linear-gradient(135deg,#F0F8FA 0%,#C4E2EC 55%,#9FCFDF 100%) !important;}`)
  }
  return lines.join(String.fromCharCode(10))
}

function applyBrandTheme (consoleDir) {
  const htmlPath = join(consoleDir, 'index.html')
  let html = readFileSync(htmlPath, 'utf8')
  html = html.replace(/<style id="zy-(kingdee-theme|brand-theme)">[\s\S]*?<\/style>/g, '')
  const style = `<style id="zy-brand-theme">${themeCss(brandTheme())}</style>`
  const nextHtml = html.replace(/<\/head>/, style + '</head>')
  if (nextHtml === html) {
    warn('未找到 </head>，无法注入品牌主题。')
    return
  }
  writeAssetWithSiblings(htmlPath, nextHtml)
  console.log('Console 已注入灵泽万川蓝绿主题样式。')
}

// 生成内嵌的“文档资料”本地页面（替代上游外链 qwenpaw.agentscope.io）。
// 内容源为仓库 docs/console-help/src/*.zh.md（自官方文档站抓取的中文 Markdown），
// 构建时做：品牌替换（QwenPaw→智造云AIOS，保护标识符/仓库地址）、图片剔除、
// 外链文档地址改写为本页锚点，最终渲染为带侧边栏目录的单页离线文档。
const DOCS_SRC = join(scriptsRoot, '..', '..', '..', 'docs', 'console-help', 'src')

const DOC_TITLES = {
  intro: '项目介绍', quickstart: '快速开始', desktop: '桌面应用', console: '控制台',
  mailbox: '邮箱管理与自动化', tui: '终端界面', cli: 'CLI', multiAgent: '多智能体',
  models: '模型', channels: '频道配置', skills: 'Skills', mcp: 'MCP 与内置工具',
  browser: '浏览器', acpServer: 'ACP 集成', memory: '长期记忆', embedding: '向量模型',
  memoryEvolvingAndProactive: '记忆进化与主动交互', computerUse: '电脑操作',
  chrome: 'Chrome 浏览器扩展', creator: 'Creator', context: '上下文',
  loopEngineering: '循环工程', commands: '魔法命令', cron: '定时任务', heartbeat: '心跳',
  config: '配置与工作目录', security: '安全', backup: '备份与恢复', plugins: '插件系统',
  pluginsMigration: '插件迁移指南', hub: '部署与管理多租户', architecture: '架构设计',
  faq: '常见问题', apiTutorial: 'RESTful API 接口', community: '问题反馈与交流',
  contributing: '开源与贡献', roadmap: '路线图', practiceAgentTeam: 'Agent Team 实践',
}

const DOC_GROUPS = [
  ['快速上手', ['intro', 'quickstart', 'desktop', 'console', 'tui', 'cli']],
  ['智能体与能力', ['multiAgent', 'models', 'context', 'loopEngineering', 'commands', 'skills', 'mcp', 'browser', 'chrome', 'computerUse', 'memory', 'embedding', 'memoryEvolvingAndProactive']],
  ['自动化与集成', ['mailbox', 'channels', 'cron', 'heartbeat', 'acpServer', 'creator']],
  ['部署与管理', ['config', 'security', 'backup', 'plugins', 'pluginsMigration', 'hub', 'architecture']],
  ['参考', ['apiTutorial', 'practiceAgentTeam', 'roadmap', 'community', 'contributing', 'faq']],
]

function escapeHtml (text) {
  return text.split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;').split('"').join('&quot;')
}

function slugAnchor (id) { return 'doc-' + id }

// 极简 Markdown → HTML（标题/段落/列表/引用/表格/代码块/行内标记；图片剔除）。
function mdToHtml (md, knownIds) {
  const esc = escapeHtml
  const inline = (text) => {
    let t = esc(text)
    t = t.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1') // 剔除图片，保留可选 alt 文本
    t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, label, url) => {
      const dm = url.match(/(?:^|qwenpaw\.agentscope\.io)\/docs\/([a-zA-Z-]+)(?:[?#][^)]*)?$/)
        || (url.startsWith('/docs/') ? [null, url.slice(7).split(/[?#]/)[0]] : null)
        || (url.startsWith('./') ? [null, url.slice(2).split(/[?#]/)[0]] : null)
      if (dm) {
        // 文档内链接常用 kebab slug（multi-agent），章节 id 是 camel（multiAgent）
        const camel = dm[1].replace(/-([a-z])/g, (mm, c) => c.toUpperCase())
        const id = knownIds.has(dm[1]) ? dm[1] : (knownIds.has(camel) ? camel : dm[1])
        if (knownIds.has(id)) return `<a href="#${slugAnchor(id)}">${label}</a>`
        return `<strong>${label}</strong>`
      }
      return `<a href="${url}" target="_blank" rel="noreferrer">${label}</a>`
    })
    t = t.split('`').reduce((acc, part, i) => i % 2 ? acc + '<code>' + part + '</code>' : acc + part, '')
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    return t
  }
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  // 引用式链接定义：[id]: url —— 先收集再从正文中剔除
  const refLinks = {}
  for (let li = 0; li < lines.length; li++) {
    const rm = lines[li].match(/^\s{0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+"[^"]*")?\s*$/)
    if (rm) { refLinks[rm[1].toLowerCase()] = rm[2]; lines[li] = '' }
  }
  const inlineWithRefs = (text) => {
    let t = text.replace(/\[([^\]]+)\]\[([^\]]+)\]/g, (mm, label, ref) => {
      const url = refLinks[String(ref).toLowerCase()]
      return url ? '[' + label + '](' + url + ')' : label
    })
    return inline(t)
  }
  const out = []
  let i = 0
  let para = []
  const flushPara = () => { if (para.length) { out.push('<p>' + para.map(inlineWithRefs).join('<br>') + '</p>'); para = [] } }
  while (i < lines.length) {
    const line = lines[i]
    if (/^\s*<[a-zA-Z!/]/.test(line)) {
      flushPara()
      const buf = []
      while (i < lines.length && (/^\s*<[a-zA-Z!/]/.test(lines[i]) || (/^\s*\S/.test(lines[i]) && lines[i].includes('>')))) { buf.push(lines[i]); i++ }
      out.push(buf.join('\n'))
      continue
    }
    if (/^```|^~~~/.test(line)) {
      flushPara()
      const buf = []
      i++
      while (i < lines.length && !/^```|^~~~/.test(lines[i])) { buf.push(lines[i]); i++ }
      i++
      out.push('<pre><code>' + esc(buf.join('\n')) + '</code></pre>')
      continue
    }
    const h = line.match(/^(#{1,5})\s+(.*)$/)
    if (h) {
      flushPara()
      const level = Math.min(h[1].length + 1, 6)
      out.push(`<h${level}>${inline(h[2])}</h${level}>`)
      i++
      continue
    }
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:-|]+\|\s*$/.test(lines[i + 1] || '')) {
      flushPara()
      const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
      const head = cells(line)
      i += 2
      const body = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { body.push(cells(lines[i])); i++ }
      out.push('<table><thead><tr>' + head.map(c => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        + body.map(r => '<tr>' + r.map(c => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>')
      continue
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      flushPara()
      const items = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, '')); i++ }
      out.push('<ul>' + items.map(it => `<li>${inlineWithRefs(it)}</li>`).join('') + '</ul>')
      continue
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      flushPara()
      const items = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, '')); i++ }
      out.push('<ol>' + items.map(it => `<li>${inlineWithRefs(it)}</li>`).join('') + '</ol>')
      continue
    }
    if (/^>\s?/.test(line)) {
      flushPara()
      const buf = []
      while (i < lines.length && /^>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^>\s?/, '')); i++ }
      out.push('<blockquote>' + buf.map(inlineWithRefs).join('<br>') + '</blockquote>')
      continue
    }
    if (/^\s*(---|\*\*\*)\s*$/.test(line)) { flushPara(); out.push('<hr>'); i++; continue }
    if (!line.trim()) { flushPara(); i++; continue }
    para.push(line)
    i++
  }
  flushPara()
  return out.join('\n')
}

function writeLocalDocs (consoleDir) {
  const t = brandTheme()
  const logo = selectedLogo()
  const logoData = 'data:' + logo.mime + ';base64,' + readFileSync(logo.path).toString('base64')
  const pages = []
  for (const [group, ids] of DOC_GROUPS) {
    for (const id of ids) {
      const file = join(DOCS_SRC, id + '.zh.md')
      if (!existsSync(file)) continue
      pages.push({ id, group, title: DOC_TITLES[id] || id })
    }
  }
  const knownIds = new Set(pages.map(p => p.id))
  const toc = DOC_GROUPS.map(([group, ids]) => {
    const items = ids.filter(id => knownIds.has(id))
    if (!items.length) return ''
    return '<div class="nav-group"><div class="nav-title">' + group + '</div>' +
      items.map(id => '<a href="#' + slugAnchor(id) + '">' + (DOC_TITLES[id] || id) + '</a>').join('') + '</div>'
  }).join('')
  const sections = pages.map(p => {
    let md = readFileSync(join(DOCS_SRC, p.id + '.zh.md'), 'utf8')
    md = md.replace(/^---\n[\s\S]*?\n---\n/, '') // frontmatter
    const branded = applyBrand(md)
    const anchorAlias = p.id === 'intro' ? '<i id="tutorial"></i>' : (p.id === 'faq' ? '<i id="faq"></i>' : '')
    return '<section id="' + slugAnchor(p.id) + '">' + anchorAlias + '<h2>' + escapeHtml(p.title) + '</h2>' + mdToHtml(branded, knownIds) + '</section>'
  }).join('\n')
  const html = ['<!DOCTYPE html>',
'<html lang="zh-CN">',
'<head>',
'<meta charset="utf-8">',
'<meta name="viewport" content="width=device-width,initial-scale=1">',
'<title>智造云AIOS 帮助中心</title>',
'<style>',
':root{--brand:' + t.primary + ';--brand-hover:' + t.primaryHover + ';--text:#1D2129;--muted:#4E5969;}',
'*{box-sizing:border-box}',
'body{margin:0;font-family:-apple-system,\'Segoe UI\',\'Microsoft YaHei\',sans-serif;background:linear-gradient(135deg,#F0F8FA 0%,#C4E2EC 100%);color:var(--text);line-height:1.75}',
'.layout{display:flex;min-height:100vh}',
'aside{width:230px;flex-shrink:0;background:#fff;padding:20px 14px;position:sticky;top:0;height:100vh;overflow-y:auto;border-right:1px solid #D8E8EE}',
'main{flex:1;max-width:900px;margin:0 auto;padding:28px 26px 80px}',
'header.top{display:flex;align-items:center;gap:14px}',
'header.top img{height:52px;width:auto}',
'h1{font-size:24px;margin:0}',
'.sub{color:var(--muted);margin:4px 0 20px}',
'.quick{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:26px}',
'.quick a{color:var(--brand);text-decoration:none;padding:6px 14px;border:1px solid var(--brand);border-radius:18px;font-size:14px}',
'.quick a:hover{background:var(--brand);color:#fff}',
'.nav-group{margin-bottom:14px}',
'.nav-title{font-size:12px;color:var(--muted);margin:8px 6px 4px;letter-spacing:1px}',
'aside a{display:block;color:var(--text);text-decoration:none;font-size:13px;padding:4px 10px;border-radius:6px}',
'aside a:hover{background:#EDF5F8;color:var(--brand)}',
'section{background:#fff;border-radius:12px;padding:22px 28px;margin-bottom:18px;box-shadow:0 2px 10px rgba(0,60,80,.06)}',
'h2{font-size:20px;border-left:4px solid var(--brand);padding-left:10px;margin-top:0}',
'h3,h4,h5,h6{margin-top:1.2em}',
'code{background:#EDF3F5;padding:2px 6px;border-radius:4px;font-size:13px}',
'pre{background:#F5F8FA;border:1px solid #E0EBF0;border-radius:8px;padding:14px;overflow-x:auto}',
'pre code{background:none;padding:0}',
'table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}',
'th,td{border:1px solid #E0EBF0;padding:8px 10px;text-align:left}',
'th{background:#EDF5F8}',
'blockquote{border-left:4px solid var(--brand);margin:12px 0;padding:8px 14px;background:#F5FAFC;color:var(--muted)}',
'a{color:var(--brand)}',
'.tag{display:inline-block;background:#FFF3E0;color:#D46B08;border-radius:4px;padding:2px 10px;font-size:13px;margin-left:8px}',
'.todo{border:1px dashed var(--brand);border-radius:10px;padding:26px;text-align:center;color:var(--muted)}',
'footer{color:var(--muted);font-size:13px;text-align:center;margin-top:30px}',
'@media (max-width:860px){aside{display:none}}',
'</style>',
'</head>',
'<body>',
'<div class="layout">',
'<aside>',
'<header class="top"><img src="' + logoData + '" alt="智造云AIOS"></header>',
toc,
'</aside>',
'<main>',
'<h1>智造云AIOS 帮助中心</h1>',
'<p class="sub">智造云AIOS 2.2.0（灵泽万川 · 企业级智能体操作系统） · 离线内嵌文档</p>',
'<div class="quick">',
'<a href="#tutorial">快速上手</a>',
'<a href="#demo">视频教程</a>',
'<a href="#changelog">更新日志</a>',
'<a href="#faq">常见问题</a>',
'</div>',
'<section id="demo">',
'<h2>视频教程 <span class="tag">待开发</span></h2>',
'<div class="todo">🎬 视频教程正在制作中，敬请期待。<br>当前可先阅读左侧目录的文字版文档。</div>',
'</section>',
'<section id="changelog">',
'<h2>更新日志</h2>',
'<ul>',
'<li>智造云AIOS 2.2.0：基于 QwenPaw 2.2.0 运行时；业务应用解耦按需安装；内置账户体系（单机与 Hub 多用户）；灵泽万川蓝绿品牌化主题；支持品牌目录自定义 Logo、主题色与登录页封面。</li>',
'</ul>',
'</section>',
sections,
'<footer>灵泽万川 · 智造云AIOS 2.2.0 — 本页面为内嵌离线文档</footer>',
'</main>',
'</div>',
'</body>',
'</html>',
'' ].join('\n')
  writeAssetWithSiblings(join(consoleDir, 'aios-docs.html'), html)
  console.log('Console 内嵌帮助文档已生成：aios-docs.html（' + pages.length + ' 个文档章节）')
}

function suppressConsoleTour (consoleDir) {
  const htmlPath = join(consoleDir, 'index.html')
  const html = readFileSync(htmlPath, 'utf8')
  const styleId = 'zy-tour-suppress'
  if (html.includes(`id="${styleId}"`)) return
  const style = `<style id="${styleId}">.qwenpaw-tour-mask,.qwenpaw-tour{display:none !important;}</style>`
  const nextHtml = html.replace(/<\/head>/, style + '</head>')
  if (nextHtml === html) {
    warn('未找到 </head>，无法注入引导抑制样式。')
    return
  }
  writeAssetWithSiblings(htmlPath, nextHtml)
  console.log('Console 新手引导弹层已抑制（style#zy-tour-suppress 注入）。')
}

const runtime = resolveRuntime()
// --console-dir <目录>：显式指定控制台资产目录（如 Hub venv 的 console），
// 缺省时按项目运行时解析
const dirFlagIdx = process.argv.indexOf('--console-dir')
const consoleDir = dirFlagIdx !== -1 && process.argv[dirFlagIdx + 1]
  ? process.argv[dirFlagIdx + 1]
  : locateConsoleDir(runtime)

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
    if (!r.optional) missing.push(r.name)
  }
}

const branded = applyBrand(content)

if (checkMode) {
  if (missing.filter(name => !REPLACEMENTS.find(r => r.name === name)?.optional).length) {
    const required = missing.filter(name => !REPLACEMENTS.find(r => r.name === name)?.optional)
    console.error('[patch-console-ui] 检查失败：console bundle 中未找到以下必需目标：' + required.join('、') + '。bundle 可能已随上游升级更新。')
    process.exit(1)
  }
  if (branded !== content) {
    console.error('[patch-console-ui] 检查失败：console bundle 中仍存在未替换的 QwenPaw 品牌文案（应替换为 智造云AIOS）。')
    process.exit(1)
  }
  // 校验所有可打补丁的 JS/HTML 资源文件均已替换 QwenPaw 品牌文案。
  const unpatchedFiles = []
  for (const file of collectBrandableFiles(consoleDir)) {
    const cc = readFileSync(file, 'utf8')
    if (cc.includes('QwenPaw') && applyBrand(cc) !== cc) unpatchedFiles.push(file)
  }
  if (unpatchedFiles.length) {
    console.error('[patch-console-ui] 检查失败：以下文件仍包含未替换的 QwenPaw 品牌文案（应替换为 智造云AIOS）：\n' + unpatchedFiles.join('\n'))
    process.exit(1)
  }
  const htmlTitle = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  if (htmlTitle.includes('QwenPaw')) {
    console.error('[patch-console-ui] 检查失败：index.html 仍包含 QwenPaw 品牌标题（应替换为 智造云AIOS）。')
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
  writeAssetWithSiblings(bundlePath, content)
  console.log('Console UI 定制已应用：' + bundlePath)
} else {
  console.log('Console UI 定制已是最新状态：' + bundlePath)
}

const cacheBust = ensureCacheBust(consoleDir, content)
if (cacheBust.changed) {
  console.log('Console index.html 已移除主 bundle ?v= 查询参数（避免 console 双重执行）')
}
syncConsoleLogo(consoleDir)
applyBrandTheme(consoleDir)
writeLocalDocs(consoleDir)
suppressConsoleTour(consoleDir)


// 对其它 Console 资源（懒加载 chunk / vendor）执行同样的品牌替换。
let extraBranded = 0
for (const file of collectBrandableFiles(consoleDir)) {
  if (file === bundlePath) continue
  const cc = readFileSync(file, 'utf8')
  if (!cc.includes('QwenPaw') && !cc.includes('灵泽万川智造云')) continue
  const out = applyBrand(cc)
  if (out !== cc) {
    writeAssetWithSiblings(file, out)
    extraBranded++
  }
}
if (extraBranded) console.log('已更新 ' + extraBranded + ' 个额外 Console 资源文件品牌文案。')

if (missing.length) {
  warn('以下目标未找到，bundle 可能已更新：' + missing.join('、'))
}
