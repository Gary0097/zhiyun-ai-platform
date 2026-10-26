// Build-time only. npm never runs during a normal platform launch.
import { mkdirSync, copyFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
const target = resolve('apps/zhizaoyunAIOS/runtime/office-node')
mkdirSync(target, { recursive: true })
for (const file of ['package.json', 'package-lock.json']) copyFileSync(resolve('scripts/office-node', file), resolve(target, file))
const result = spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['ci', '--omit=dev', '--no-audit', '--no-fund'], { cwd: target, stdio: 'inherit', shell: process.platform === 'win32' })
process.exitCode = result.status ?? 1
