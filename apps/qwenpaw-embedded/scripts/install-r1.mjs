import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const app = join(root, 'pawapps', 'zhiyun-orders')
const run = (command, args, hint) => {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit', env: process.env })
  if (result.status !== 0) { console.error(hint); process.exit(result.status || 1) }
}

run('qwenpaw', ['plugin', 'install', app, '--force'], '订单 PawApp 安装失败；请确认 QwenPaw 2.1.0 可用')
run(process.env.PYTHON || 'python', [join(root, 'apps/qwenpaw-embedded/scripts/enable-r1-tools.py')], '订单 Tool 启用失败；请确认 python 与 qwenpaw 位于同一环境')
console.log('R1 安装完成。重新启动 QwenPaw 后，可从桌面打开「订单与交付风险」，或在新对话中调用订单 Tool。')
