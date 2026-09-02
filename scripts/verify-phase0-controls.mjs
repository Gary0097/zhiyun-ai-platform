import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const installed = join(root, 'apps', 'zhizaoyunAIOS', 'runtime', 'pawapps')
const repositories = [
  { id: 'zhiyun-ai-platform', root },
  { id: 'zhiyun-data-studio', root: join(installed, 'zhiyun-data-studio') },
  { id: 'zhiyun-order-studio', root: join(installed, 'zhiyun-order-studio') },
]

for (const repository of repositories) {
  for (const relative of [
    'AGENTS.md',
    '.github/ISSUE_TEMPLATE/codex-feature.yml',
    '.github/ISSUE_TEMPLATE/config.yml',
    '.github/PULL_REQUEST_TEMPLATE.md',
    '.github/workflows/release-gate.yml',
  ]) {
    assert.ok(existsSync(join(repository.root, relative)), `${repository.id} missing ${relative}`)
  }
  const agents = readFileSync(join(repository.root, 'AGENTS.md'), 'utf8')
  assert.match(agents, /Never commit directly/i, `${repository.id} must prohibit direct default-branch commits`)
  assert.match(agents, /merge automatically|automatic merge/i, `${repository.id} must prohibit automatic merge`)
  const issue = readFileSync(join(repository.root, '.github', 'ISSUE_TEMPLATE', 'codex-feature.yml'), 'utf8')
  for (const label of ['codex-ready', 'priority-p0', 'priority-p1', 'priority-p2']) {
    assert.ok(issue.includes(label), `${repository.id} issue form missing ${label}`)
  }
  const workflow = readFileSync(join(repository.root, '.github', 'workflows', 'release-gate.yml'), 'utf8')
  assert.ok(workflow.includes('ubuntu-24.04') && workflow.includes('windows-2022'), `${repository.id} gate must cover Ubuntu and Windows`)
}

console.log('Phase 0 控制检查通过：三仓库规则、模板、标签契约及 Windows/Linux 门禁均已落盘。')
