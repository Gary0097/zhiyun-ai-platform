import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, join } from 'node:path'
import { readLocalProfile, attachLocalInstance } from '../apps/zhizaoyunAIOS/scripts/local-instance.mjs'
import { provisionOfficeSkills } from '../apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs'
const root = mkdtempSync(join(tmpdir(), 'local-office-'))
try {
  const workspace = join(root, 'workspace'), secret = join(root, 'secret'), agent = join(workspace, 'workspaces/default')
  mkdirSync(agent, { recursive: true }); mkdirSync(secret)
  writeFileSync(join(workspace, 'config.json'), JSON.stringify({ agents: { default_agent: 'default' } }))
  const config = { active_model: { provider_id: 'preserve-provider', model: 'preserve-model' }, system_prompt_files: ['AGENTS.md', 'SOUL.md', 'PROFILE.md'], language: 'zh' }
  writeFileSync(join(agent, 'agent.json'), JSON.stringify(config))
  writeFileSync(join(agent, 'AGENTS.md'), 'User custom instructions must remain active')
  writeFileSync(join(secret, 'auth.json'), 'existing-native-account')
  assert.throws(() => attachLocalInstance({ workspace, secretDir: secret, localNoAuth: true }), /已有原生账号/)
  const profile = join(root, 'profile.json')
  writeFileSync(profile, JSON.stringify({ schema_version: 1, workspace, secret_dir: secret }))
  assert.equal(readLocalProfile(profile).workspace, workspace)
  provisionOfficeSkills({ workspace, packRoot: resolve('skills/office'), preservePrompts: true, log: () => {} })
  assert.deepEqual(JSON.parse(readFileSync(join(agent, 'agent.json'), 'utf8')), config)
  assert.equal(readFileSync(join(agent, 'AGENTS.md'), 'utf8'), 'User custom instructions must remain active')
  writeFileSync(profile, JSON.stringify({ schema_version: 1, workspace: join(root, 'missing'), secret_dir: secret }))
  assert.throws(() => readLocalProfile(profile), /无效/)
  console.log('PASS local attachment: native accounts protected, missing directories rejected, original model and prompt configuration preserved')
} finally { rmSync(root, { recursive: true, force: true }) }
