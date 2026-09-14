import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { compare } from './protocol.mjs'

export async function track(api, current, repository) {
  const upstream = 'agentscope-ai/QwenPaw'
  const release = await api(`/repos/${upstream}/releases/latest`)
  if (release.draft || release.prerelease) throw Error('上游不是正式发布')
  const version = release.tag_name?.replace(/^v/, '')
  if (compare(version, current) <= 0) return 'No newer stable release'
  const commit = await api(`/repos/${upstream}/commits/${encodeURIComponent(release.tag_name)}`)
  if (!/^[a-f0-9]{40}$/.test(commit.sha)) throw Error('上游提交无效')
  const marker = `<!-- aios-upstream:${version} -->`
  // Include closed issues: an intentionally rejected upgrade must not reopen daily.
  for (let page = 1; ; page++) {
    const issues = await api(`/repos/${repository}/issues?state=all&per_page=100&page=${page}`)
    if (issues.some(i => !i.pull_request && (i.body?.includes(marker) || i.title?.includes(`QwenPaw ${version}`)))) return `Already tracked ${version}`
    if (issues.length < 100) break
  }
  await api(`/repos/${repository}/issues`, {
    title: `升级评估：QwenPaw ${version}`,
    body: `${marker}\n当前稳定锁：${current}\n上游正式版：${version}\n精确提交：${commit.sha}\n发布记录：https://github.com/${upstream}/releases/tag/v${version}\n\n验收：\n- 先检查已有升级 PR 与当前主分支，人工标记 codex-ready 后在独立任务分支实施。\n- 同步版本锁、产品决策、版本声明和门禁；保留品牌界面、原生登录与 Hub 隔离。\n- Windows/Linux 发布门禁、真实运行时与品牌回归；使用真实数据路径验证模型、Hub 和升级恢复，不使用演示结果。\n- 确认旧 Workspace、数据库和密钥备份及迁移恢复方法。\n- 创建 PR，人工审核合并。随后构建安装包，在受保护发布环境签名，人工发布；不自动合并，不向客户端直接推送上游包。\n\n本 Issue 仅表示发现新版，不表示兼容性验证或升级已完成。`
  })
  return `Created upgrade assessment for ${version}`
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const repository = process.env.GITHUB_REPOSITORY
    if (repository !== 'Gary0097/zhiyun-ai-platform' || !process.env.GH_TOKEN) throw Error('需要仓库 Actions 身份')
    const current = JSON.parse(readFileSync(new URL('../../apps/zhizaoyunAIOS/qwenpaw.lock.json', import.meta.url))).version
    const api = async (path, body) => {
      const response = await fetch(`https://api.github.com${path}`, {
        method: body ? 'POST' : 'GET', signal: AbortSignal.timeout(30000),
        headers: { Authorization: `Bearer ${process.env.GH_TOKEN}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
        ...(body ? { body: JSON.stringify(body) } : {})
      })
      if (!response.ok) throw Error(`GitHub API HTTP ${response.status}`)
      return response.json()
    }
    console.log(await track(api, current, repository))
  } catch (e) { console.error(e.message); process.exitCode = 1 }
}
