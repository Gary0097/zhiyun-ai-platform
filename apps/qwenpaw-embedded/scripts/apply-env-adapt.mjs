// 幂等补丁：让 start.mjs 适配「本机 qwenpaw 为 Desktop 打包 exe」的环境。
// 每次 git pull 后 PR 会带回 Python 版（import qwenpaw 检查 + cleanup-legacy.py），
// 本脚本把它们改为 Node 等价实现，重复运行无副作用。
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const startPath = join(dirname(fileURLToPath(import.meta.url)), 'start.mjs')
let src = readFileSync(startPath, 'utf8')
let changed = false

// 1. 删除 `run(python, ['-c', 'import qwenpaw'], ...)` 硬编码检查行
const importCheck = /^run\(python, \['-c', 'import qwenpaw'\][^\n]*\n\n?/m
if (importCheck.test(src)) {
  src = src.replace(importCheck, '')
  changed = true
}

// 2. cleanup-legacy.py（python）→ cleanup-legacy.mjs（Node）
const cleanupPy = /run\(python, \[join\(scriptsRoot, 'cleanup-legacy\.py'\)\]/
if (cleanupPy.test(src)) {
  src = src.replace(
    cleanupPy,
    "run(process.execPath, [join(scriptsRoot, 'cleanup-legacy.mjs')]",
  )
  // 补上说明注释
  src = src.replace(
    "run(process.execPath, [join(scriptsRoot, 'cleanup-legacy.mjs')]",
    "// 本机 qwenpaw 为 Desktop 打包 exe，用 Node 等价实现清理。\nrun(process.execPath, [join(scriptsRoot, 'cleanup-legacy.mjs')]",
  )
  changed = true
}

if (changed) {
  writeFileSync(startPath, src, 'utf8')
  console.log('✔ 环境适配已应用：start.mjs 改用 Node 版 cleanup，跳过 import qwenpaw 检查')
} else {
  console.log('✔ 环境适配无需变更（start.mjs 已是 Node 版）')
}
