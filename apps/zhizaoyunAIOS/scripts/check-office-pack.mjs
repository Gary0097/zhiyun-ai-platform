// 智造云 AIOS 办公版体检（aios-office 分支 v1.5.0）
// 一条命令审计办公完全体的全部关键状态，供安装后自检与售后排查：
//   ① 技能包清单与磁盘一致（frontmatter 合法）
//   ② 全部智能体工作区 11 项技能已预置且默认启用
//   ③ 技能池收录 11 项
//   ④ 依赖预装（venv 内可导入）
//   ⑤ OFFICE.md 办公回复规范与注入列表
//   ⑥ ZCode 技能桥接（skill_paths）
//   ⑦ 文件下载修复已注入 console bundle
// 退出码：0 = 全部通过；1 = 存在问题（WARN 行给出修复指引）。
// 用法：node apps/zhizaoyunAIOS/scripts/check-office-pack.mjs [--json]
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const scriptRoot = dirname(fileURLToPath(import.meta.url))
const appRoot = join(scriptRoot, '..')
const repoRoot = join(appRoot, '..', '..')
const workspace = process.env.QWENPAW_WORKING_DIR || join(appRoot, 'workspace')
const packRoot = join(repoRoot, 'skills', 'office')
const jsonMode = process.argv.includes('--json')

const findings = []
function report (pass, name, detail, hint) {
  findings.push({ pass, name, detail, hint })
  if (jsonMode) return
  console.log((pass ? '  ✓ ' : '  ✗ ') + name + (detail ? '：' + detail : ''))
  if (!pass && hint) console.log('      ↳ ' + hint)
}

try {
  // ① 技能包清单
  let packCount = 0
  try {
    const { loadOfficePack } = await import(pathToFileURL(join(scriptRoot, 'provision-office-skills.mjs')).href)
    const pack = loadOfficePack(packRoot)
    packCount = pack.skills.length
    report(true, '技能包清单', `v${pack.version}，${packCount} 项，frontmatter 全部合法`)
  } catch (e) {
    report(false, '技能包清单', e.message, '重跑 start-ai-os 触发预置，或检查 skills/office 目录完整性')
  }

  // ② 工作区预置与启用
  const workspacesRoot = join(workspace, 'workspaces')
  if (existsSync(workspacesRoot)) {
    for (const entry of readdirSync(workspacesRoot, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      const manifestPath = join(workspacesRoot, entry.name, 'skill.json')
      if (!existsSync(manifestPath)) continue
      try {
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
        const skills = manifest.skills || {}
        const office = Object.entries(skills).filter(([k]) => k.startsWith('office-'))
        const enabled = office.filter(([, v]) => v && v.enabled)
        if (office.length === packCount && enabled.length === packCount) {
          report(true, `工作区 ${entry.name}`, `${office.length}/${packCount} 项技能全部启用`)
        } else {
          report(false, `工作区 ${entry.name}`, `仅 ${enabled.length}/${packCount} 项启用（登记 ${office.length}）`,
            '控制台「工作区 → 技能」确认启用状态，或重跑 start-ai-os 重新预置')
        }
      } catch (e) {
        report(false, `工作区 ${entry.name}`, 'skill.json 解析失败：' + e.message, '重跑 start-ai-os 重建清单')
      }
    }
  } else {
    report(false, '工作区目录', 'workspaces/ 不存在', '先运行 start-ai-os 完成初始化')
  }

  // ③ 技能池
  try {
    const pool = JSON.parse(readFileSync(join(workspace, 'skill_pool', 'skill.json'), 'utf8'))
    const count = Object.keys(pool.skills || {}).filter(k => k.startsWith('office-')).length
    report(count === packCount, '技能池', `${count}/${packCount} 项 office 技能`, '重跑 start-ai-os 同步技能池')
  } catch {
    report(false, '技能池', 'skill_pool/skill.json 缺失或损坏', '重跑 start-ai-os')
  }

  // ④ 依赖预装
  try {
    const lock = JSON.parse(readFileSync(join(appRoot, 'qwenpaw.lock.json'), 'utf8'))
    const python = process.platform === 'win32'
      ? join(appRoot, ...lock.runtime_dir.split('/'), 'venv', 'Scripts', 'python.exe')
      : join(appRoot, ...lock.runtime_dir.split('/'), 'venv', 'bin', 'python')
    if (!existsSync(python)) {
      report(false, '依赖预装', '运行环境未安装', '运行 setup-ai-os.ps1/.sh 安装运行环境')
    } else {
      const probe = spawnSync(python, ['-c',
        'from importlib.util import find_spec;import sys;sys.exit(0 if all(find_spec(m) for m in ["docx","openpyxl","pptx","pdfplumber","pypdf","fpdf","PIL","chardet","markdownify","pandas","rapidocr_onnxruntime"]) else 1)'],
        { encoding: 'utf8', timeout: 120000 })
      report(probe.status === 0, '依赖预装', probe.status === 0 ? '11 项办公依赖全部可导入' : '存在缺失依赖',
        '重跑 start-ai-os 自动补装，或 node apps/zhizaoyunAIOS/scripts/ensure-office-deps.mjs')
    }
  } catch (e) {
    report(false, '依赖预装', e.message, '检查 qwenpaw.lock.json')
  }

  // ⑤ OFFICE.md 办公回复规范
  const officeMd = join(workspace, 'workspaces', 'default', 'OFFICE.md')
  if (existsSync(officeMd)) {
    report(true, '办公回复规范', 'OFFICE.md 已预置（' + readFileSync(officeMd, 'utf8').length + ' 字符）')
    try {
      const agent = JSON.parse(readFileSync(join(workspace, 'workspaces', 'default', 'agent.json'), 'utf8'))
      const spf = agent.system_prompt_files || []
      report(spf.includes('OFFICE.md'), '回复规范注入', 'system_prompt_files = [' + spf.join(', ') + ']',
        '控制台「系统提示词文件」确认包含 OFFICE.md')
    } catch {
      report(false, '回复规范注入', 'agent.json 读取失败', '重启服务后由预置器自动修复')
    }
  } else {
    report(false, '办公回复规范', 'default 工作区缺少 OFFICE.md', '重跑 start-ai-os 预置')
  }

  // ⑥ ZCode 桥接
  try {
    const config = JSON.parse(readFileSync(join(workspace, 'config.json'), 'utf8'))
    const paths = (config.skill_paths || []).filter(p => String(p).includes('zcode'))
    report(true, 'ZCode 技能桥接', paths.length
      ? `已挂载 ${paths.length} 个 ZCode 技能根（pptx/xlsx/docx/pdf/浏览器/电脑操作）`
      : '未挂载（本机未装 ZCode 或插件无技能目录，属正常）')
  } catch {
    report(true, 'ZCode 技能桥接', 'config.json 尚未生成（首次启动后生效）')
  }

  // ⑦ 文件下载修复（用 venv python 自定位 console 目录，与品牌补丁同法）
  try {
    const lock = JSON.parse(readFileSync(join(appRoot, 'qwenpaw.lock.json'), 'utf8'))
    const python = process.platform === 'win32'
      ? join(appRoot, ...lock.runtime_dir.split('/'), 'venv', 'Scripts', 'python.exe')
      : join(appRoot, ...lock.runtime_dir.split('/'), 'venv', 'bin', 'python')
    if (!existsSync(python)) {
      report(false, '文件下载修复', '运行环境未安装，无法定位 console', '运行 setup-ai-os.ps1/.sh')
    } else {
      const locate = spawnSync(python, ['-c', 'import qwenpaw, os; print(os.path.join(os.path.dirname(qwenpaw.__file__), "console"))'], { encoding: 'utf8', timeout: 60000 })
      const consoleDir = (locate.stdout || '').trim().split(/\r?\n/)[0]
      const indexHtml = consoleDir && existsSync(join(consoleDir, 'index.html'))
        ? readFileSync(join(consoleDir, 'index.html'), 'utf8') : ''
      const bundle = indexHtml.match(/src="\/assets\/(index-[^"]+\.js)"/)?.[1]
      const bundlePath = bundle && join(consoleDir, 'assets', bundle)
      if (bundlePath && existsSync(bundlePath) && readFileSync(bundlePath, 'utf8').includes('replace(/%/g,"%2525")')) {
        report(true, '文件下载修复', 'console bundle 已含 URL 编码修复')
      } else {
        report(false, '文件下载修复', 'console bundle 未检测到编码修复', '重跑 start-ai-os 重新应用品牌补丁')
      }
    }
  } catch (e) {
    report(false, '文件下载修复', e.message, '检查运行时目录')
  }
} catch (e) {
  report(false, '体检执行', e.message, '按上述提示逐项排查')
}

const failed = findings.filter(f => !f.pass)
if (jsonMode) {
  console.log(JSON.stringify({ pass: failed.length === 0, checks: findings }, null, 2))
} else {
  console.log(failed.length
    ? `\n办公版体检：${findings.length - failed.length}/${findings.length} 项通过，${failed.length} 项待修复（见上方 ↳ 指引）。`
    : `\n办公版体检：${findings.length}/${findings.length} 项全部通过（技能/依赖/规范/桥接/补丁修复）。`)
}
process.exit(failed.length ? 1 : 0)
