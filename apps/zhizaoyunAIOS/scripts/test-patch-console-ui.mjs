#!/usr/bin/env node
// 品牌化补丁（patch-console-ui.mjs）回归测试 —— fixture 驱动，长期运行。
//
// 被测脚本打补丁的对象是上游 console 构建产物（venv site-packages 内，不进
// 版本库、随上游升级变化），因此本测试在临时目录构造一个“微型 console”：
// fixture 中的目标串与真实 bundle 逐字符一致（登录页 hubLinks 外链、文档
// 菜单 URL、FAQ 远程拉取、ud 仓库地址、记忆/ACP/频道文档链接等），并在
// 相邻目录放置 hub/static_files.py 缓存策略 fixture，随后：
//   1) 运行补丁 → 断言替换、内容寻址改名（-zyb）、引用改写、压缩副本同步、
//      缓存策略放宽、内嵌文档生成全部正确；
//   2) 再运行一次 → 断言幂等（zyb 文件集合与内容不变，无双重后缀）；
//   3) --check 门禁 → 退出码 0；注入缓存策略回退 → --check 必须失败。
// 上游 bundle 升级导致目标串漂移时，本测试会第一时间变红。
// 由 scripts/verify-release.mjs 调用；亦可单独运行：node test-patch-console-ui.mjs
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { brotliCompressSync, brotliDecompressSync, gzipSync } from 'node:zlib'
import assert from 'node:assert/strict'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const patchScript = join(scriptsRoot, 'patch-console-ui.mjs')

let passed = 0
function ok (cond, name) {
  assert.ok(cond, name)
  passed++
  console.log('  ✓ ' + name)
}
function section (title) { console.log('\n== ' + title + ' ==') }

// ── fixture：与真实 bundle 逐字符一致的目标串 ───────────────────────────
const ENTRY = 'index-F1XTURE01.js'
const LOGIN = 'index-L0GIN123.js'
const EXTRA = 'ExtraHelp-EXTRA01.js'

// 主 bundle：必需替换项 + 保护标识 + 资源清单（引用两个懒加载 chunk）。
// 片段嵌入合法的声明/对象上下文——真实 bundle 中这些片段本就位于对象字面量
// 或赋值语句内，fixture 必须保持同等语法合法性，ESM 解析校验才有意义。
const entryFixture = [
  'const i18n={lng:localStorage.getItem("language")||navigator.language||"en",avatar:"/qwenpaw.png"};',
  'const bootTitle="QwenPaw Console";',
  'window.QwenPaw=window.QwenPaw||{};',
  'console.info("[QwenPaw audit] boot");',
  'const upstreamRepo="agentscope-ai/QwenPaw";',
  'var ud="https://github.com/agentscope-ai/QwenPaw",qM=3600*1e3;',
  'var UM=e=>`https://qwenpaw.agentscope.io/docs/intro?lang=${Mo(e)}`;',
  'var H=`https://qwenpaw.agentscope.io/docs/faq.${N}.md`;',
  'const manifest=["assets/' + LOGIN + '","assets/' + EXTRA + '"];',
  'export{bootTitle,manifest,i18n,ud,UM,H}',
].join('\n')

// 登录 chunk：hubLinks 导航（GitHub 外链 + QwenPaw 官网外链 + 语言切换按钮）
const loginFixture = [
  'import{G as $}from"./' + ENTRY + '"',
  'const nav=(d,t)=>d&&e.jsxs("nav",{className:r.hubLinks,"aria-label":t("login.hubLinks"),children:[',
  'e.jsxs("a",{href:"https://github.com/agentscope-ai/QwenPaw",target:"_blank",rel:"noopener noreferrer",children:[e.jsx(se,{size:14,strokeWidth:1.8,"aria-hidden":"true"}),"GitHub"]}),e.jsx("span",{"aria-hidden":"true"}),',
  'e.jsxs("a",{href:"https://qwenpaw.agentscope.io/",target:"_blank",rel:"noopener noreferrer",children:[e.jsx(te,{size:14,strokeWidth:1.8,"aria-hidden":"true"}),t("login.officialWebsite")]}),e.jsx("span",{"aria-hidden":"true"}),',
  'e.jsxs("button",{type:"button","aria-label":t("login.switchLanguage"),onClick:U,children:[e.jsx(ie,{size:14,strokeWidth:1.8,"aria-hidden":"true"}),C?"English":"简体中文"]})]})',
  'export default nav',
].join('\n')

// 懒加载 chunk：记忆（两处）/ ACP（模板字面量）/ 频道（URL 映射）/ ReMe 外链
const extraFixture = [
  'import{R as Ae}from"./' + ENTRY + '"',
  'const memoryDoc="https://qwenpaw.agentscope.io/docs/memory",memoryDoc2="https://qwenpaw.agentscope.io/docs/memory#anchor";',
  'function docLink(i){const n=T(i);return`https://qwenpaw.agentscope.io/docs/acp-integration?lang=${n}#${a}`}',
  'const N={dingtalk:"https://qwenpaw.agentscope.io/docs/channels/?lang=en#DingTalk-recommended",feishu:"https://qwenpaw.agentscope.io/docs/channels/?lang=en#Feishu-Lark"};',
  'const poweredBy=e.jsx("a",{href:"https://github.com/agentscope-ai/ReMe",target:"_blank",rel:"noreferrer",children:"ReMe"})',
  'export default Ae',
].join('\n')

const indexHtmlFixture = [
  '<!doctype html>',
  '<html lang="zh">',
  '<head>',
  '<meta charset="UTF-8">',
  '<link rel="icon" type="image/svg+xml" href="/qwenpaw-default.svg" />',
  '<title>QwenPaw Console</title>',
  '</head>',
  '<body>',
  '<div id="root"></div>',
  '<script type="module" crossorigin src="/assets/' + ENTRY + '"></script>',
  '</body>',
  '</html>',
  '',
].join('\n')

const IMMUTABLE_LINE = '_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"'
const staticFilesFixture = ['"""Console asset cache policy (fixture)."""', '', IMMUTABLE_LINE, ''].join('\n')

// ── 工具 ────────────────────────────────────────────────────────────────
const tmp = mkdtempSync(join(tmpdir(), 'zy-brand-test-'))
const consoleDir = join(tmp, 'qwenpaw', 'console')
const assetsDir = join(consoleDir, 'assets')
const pyFile = join(tmp, 'qwenpaw', 'hub', 'static_files.py')
const childEnv = { ...process.env, QWENPAW_WORKING_DIR: join(tmp, 'workspace') } // 空 workspace：测试不依赖机器品牌配置

function runPatch (extraArgs = []) {
  const r = spawnSync(process.execPath, [patchScript, '--console-dir', consoleDir, ...extraArgs], { encoding: 'utf8', env: childEnv })
  if (r.status !== 0) console.error(r.stdout + '\n' + r.stderr)
  return r
}

const entrySrcInHtml = () => (readFileSync(join(consoleDir, 'index.html'), 'utf8').match(/src="\/assets\/(index-[^"]+\.js)"/) || [])[1]
const zybJsFiles = () => readdirSync(assetsDir).filter(n => n.includes('-zyb') && n.endsWith('.js'))
const occurrences = (hay, needle) => hay.split(needle).length - 1

function assertEsmValid (file, label) {
  const probe = 'const vm=require("vm"),fs=require("fs");try{new vm.SourceTextModule(fs.readFileSync(process.argv[1],"utf8"));}catch(e){console.error("ESM_FAIL "+e.message);process.exit(1)}'
  const r = spawnSync(process.execPath, ['--experimental-vm-modules', '-e', probe, file], { encoding: 'utf8' })
  assert.equal(r.status, 0, label + ' 补丁后必须是合法 ESM：' + (r.stderr || ''))
}

try {
  // ── 构造 fixture ──────────────────────────────────────────────────────
  mkdirSync(assetsDir, { recursive: true })
  mkdirSync(dirname(pyFile), { recursive: true })
  mkdirSync(childEnv.QWENPAW_WORKING_DIR, { recursive: true })
  writeFileSync(join(assetsDir, ENTRY), entryFixture)
  writeFileSync(join(assetsDir, ENTRY + '.br'), brotliCompressSync(entryFixture)) // 预压缩副本：验证写入时同步刷新
  writeFileSync(join(assetsDir, ENTRY + '.gz'), gzipSync(entryFixture))
  writeFileSync(join(assetsDir, LOGIN), loginFixture)
  writeFileSync(join(assetsDir, EXTRA), extraFixture)
  // 预置“历史漂移遗留”僵尸：模拟 canonical 命名修复前每轮派生新名的场景，
  // 验证引用归一 + 清道夫能将其回收
  writeFileSync(join(assetsDir, 'index-F1XTURE01-zybdeadbeef.js'), 'export default 0\n')
  writeFileSync(join(assetsDir, 'index-F1XTURE01-zybdeadbeef.js.br'), brotliCompressSync('export default 0\n'))
  writeFileSync(join(consoleDir, 'index.html'), indexHtmlFixture)
  writeFileSync(pyFile, staticFilesFixture)

  // ── 第一次运行：补丁应用 ─────────────────────────────────────────────
  section('运行 1：补丁应用')
  const run1 = runPatch()
  ok(run1.status === 0, 'patch-console-ui 以退出码 0 完成')

  const entryZybName = entrySrcInHtml()
  ok(!!entryZybName && entryZybName.includes('-zyb'), 'index.html 主入口已指向内容寻址 -zyb 文件（' + entryZybName + '）')
  const entry = readFileSync(join(assetsDir, entryZybName), 'utf8')

  // 主 bundle 替换与保护
  ok(entry.includes('ud="/aios-docs.html#doc-community"'), 'GitHub 仓库地址（ud）改指内嵌文档')
  ok(entry.includes('H=`/aios-docs-faq.${N}.md`'), '更新弹窗 FAQ 拉取本地化（消除运行时外呼）')
  ok(entry.includes('UM=e=>"/aios-docs.html#tutorial"'), '文档菜单 URL 改指内嵌文档')
  ok(entry.includes('lng:localStorage.getItem("language")||"zh"'), '默认语言替换为 zh')
  ok(entry.includes('avatar:"/qwenpaw.svg"'), '欢迎页头像改用品牌 Logo SVG')
  ok(entry.includes('bootTitle="智造云AIOS Console"'), '用户可见 QwenPaw 文案替换为 智造云AIOS')
  ok(entry.includes('window.QwenPaw'), '技术标识 window.QwenPaw 保留')
  ok(entry.includes('[QwenPaw audit]'), '技术标识 [QwenPaw audit] 保留')
  ok(entry.includes('"agentscope-ai/QwenPaw"'), '技术标识 agentscope-ai/QwenPaw 保留')

  // 登录 chunk：两个外链进入死代码，语言切换保持活跃
  const loginZyb = zybJsFiles().find(n => n.startsWith(LOGIN.replace('.js', '') + '-zyb'))
  ok(!!loginZyb, '登录 chunk 已内容寻址改名（' + loginZyb + '）')
  const login = readFileSync(join(assetsDir, loginZyb), 'utf8')
  ok(entry.includes(loginZyb), '入口 manifest 引用与登录 chunk 实际 zyb 文件名一致（引用归一）')
  ok(!existsSync(join(assetsDir, 'index-F1XTURE01-zybdeadbeef.js')) && !existsSync(join(assetsDir, 'index-F1XTURE01-zybdeadbeef.js.br')), '历史漂移的未引用 zyb 僵尸文件（含压缩副本）已被清道夫回收')
  ok(login.includes('false&&(e.jsxs("a",{href:"https://github.com/agentscope-ai/QwenPaw"'), '登录页 GitHub 外链已移除（死代码化）')
  ok(login.includes('false&&(e.jsxs("a",{href:"https://qwenpaw.agentscope.io/"'), '登录页 QwenPaw 官网外链已移除（死代码化）')
  ok(login.includes('"aria-label":t("login.switchLanguage")') && occurrences(login, 'false&&(') === 2, '语言切换按钮保留且为唯一活跃项')

  // 懒加载 chunk：文档链接改内嵌、ReMe 外链移除
  const extraZyb = zybJsFiles().find(n => n.startsWith(EXTRA.replace('.js', '') + '-zyb'))
  ok(!!extraZyb, '懒加载 chunk 已内容寻址改名（' + extraZyb + '）')
  const extra = readFileSync(join(assetsDir, extraZyb), 'utf8')
  ok(!extra.includes('agentscope.io/docs/memory') && occurrences(extra, '/aios-docs.html#doc-memory') === 2, '记忆文档链接全部改指内嵌文档（含锚点变体）')
  ok(!extra.includes('agentscope.io/docs/acp-integration') && extra.includes('/aios-docs.html#doc-acpServer'), 'ACP 文档链接改指内嵌文档')
  ok(!extra.includes('agentscope.io/docs/channels') && occurrences(extra, '/aios-docs.html#doc-channels') === 2, '频道文档链接改指内嵌文档')
  ok(extra.includes('false&&e.jsx("a",{href:"https://github.com/agentscope-ai/ReMe"'), 'ReMe 外链已移除')

  // 引用改写：全目录不得再出现裸原文件名引用
  const originals = [ENTRY, LOGIN, EXTRA]
  let bareRefs = []
  for (const name of readdirSync(assetsDir).concat(['..', '..', 'index.html'])) {
    const full = name.endsWith('.html') && !name.includes('.js') ? join(consoleDir, 'index.html') : join(assetsDir, name)
    if (!existsSync(full) || (!full.endsWith('.js') && !full.endsWith('.html'))) continue
    const c = readFileSync(full, 'utf8')
    for (const orig of originals) if (c.includes(orig)) bareRefs.push(name + ' -> ' + orig)
  }
  ok(bareRefs.length === 0, '所有资产引用已改写为 -zyb 名（无裸原文件名引用）' + (bareRefs.length ? '：' + bareRefs.join('; ') : ''))

  // 压缩副本同步
  ok(existsSync(join(assetsDir, entryZybName + '.br')) && existsSync(join(assetsDir, entryZybName + '.gz')), 'zyb 入口的 .br/.gz 预压缩副本已生成')
  ok(brotliDecompressSync(readFileSync(join(assetsDir, entryZybName + '.br'))).toString('utf8') === entry, '.br 副本与 identity 内容一致')
  ok(brotliDecompressSync(readFileSync(join(assetsDir, ENTRY + '.br'))).toString('utf8').includes('智造云AIOS'), '原文件名的 .br 副本已同步刷新为品牌版')

  // 改名后语法有效性
  for (const f of zybJsFiles()) assertEsmValid(join(assetsDir, f), f)
  ok(true, '全部 -zyb 资产补丁后仍为合法 ESM 模块')

  // 缓存策略
  const py = readFileSync(pyFile, 'utf8')
  ok(py.includes('max-age=0, must-revalidate') && !py.includes('31536000, immutable'), '静态缓存策略已放宽为 ETag 协商')

  // 内嵌文档
  const docs = readFileSync(join(consoleDir, 'aios-docs.html'), 'utf8')
  ok(!/<a href="[^"]*agentscope/i.test(docs), '内嵌文档无 agentscope 外链锚点')
  ok(!docs.includes('id="doc-desktop"'), '内嵌文档不含上游 desktop 章节')
  ok(docs.includes('企业内支持'), '问题反馈章节已品牌化改写')
  ok(readFileSync(join(consoleDir, 'aios-docs-faq.zh.md'), 'utf8').includes('### 智造云AIOS如何更新'), 'FAQ 本地数据源（zh）标题与 bundle 抓取正则一致')
  ok(readFileSync(join(consoleDir, 'aios-docs-faq.en.md'), 'utf8').includes('### How to update 智造云AIOS'), 'FAQ 本地数据源（en）标题与 bundle 抓取正则一致')

  // 竖屏/窄屏适配：品牌文案块必须随分栏布局在 <900px 整体隐藏，宽屏分栏保留
  const themedHtml = readFileSync(join(consoleDir, 'index.html'), 'utf8')
  ok(themedHtml.includes('@media (max-width: 899px)') && themedHtml.includes('#aios-brand-copy{display:none !important;}'), '竖屏规则：窄屏下 #aios-brand-copy 品牌文案块整体隐藏（白字叠表单回归）')
  ok(themedHtml.includes('@media (min-width: 900px)') && themedHtml.includes('grid-template-columns:58.333% 41.667%'), '宽屏规则：分栏布局保留（桌面无回归）')

  const run1Zyb = zybJsFiles().sort()
  const run1EntryContent = entry

  // ── 第二次运行：幂等 ─────────────────────────────────────────────────
  section('运行 2：幂等性')
  const run2 = runPatch()
  ok(run2.status === 0, '重复运行以退出码 0 完成')
  const run2Zyb = zybJsFiles().sort()
  ok(JSON.stringify(run1Zyb) === JSON.stringify(run2Zyb), 'zyb 文件集合不变（' + run2Zyb.length + ' 个 js ×3 表示）')
  ok(run2Zyb.every(n => occurrences(n, '-zyb') === 1), '文件名无双重 -zyb 后缀')
  ok(entrySrcInHtml() === entryZybName, 'index.html 入口引用未漂移')
  ok(readFileSync(join(assetsDir, entryZybName), 'utf8') === run1EntryContent, 'zyb 入口内容逐字节一致')

  // ── 门禁：--check 通过 / 注入回归必须失败 ─────────────────────────────
  section('门禁（--check）')
  const checkPass = runPatch(['--check'])
  ok(checkPass.status === 0, '--check 对已补丁目录通过（退出码 0）')

  writeFileSync(pyFile, staticFilesFixture) // 注入：缓存策略回退为一年 immutable
  const checkFail = runPatch(['--check'])
  ok(checkFail.status !== 0, '缓存策略回退时 --check 必须失败（防回归虚绿）')

  console.log('\n品牌化补丁回归测试：' + passed + ' 项断言全部通过。')
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
