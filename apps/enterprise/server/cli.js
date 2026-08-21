// 命令行工具：模拟数据生成 / 清理
import { simulate, clearSimulated } from './simulator.js'
import { init } from './db.js'

const cmd = process.argv[2]
init()
if (cmd === 'simulate') {
  const args = Object.fromEntries(process.argv.slice(3).map(a => a.split('=')).filter(x => x.length === 2))
  console.log('开始生成历史数据…', args)
  const t = Date.now()
  const summary = simulate({ start: args.start, end: args.end, dailyBase: Number(args.dailyBase || 480) })
  console.log('完成，用时', ((Date.now() - t) / 1000).toFixed(1), 's')
  console.log(JSON.stringify(summary, null, 2))
} else if (cmd === 'clear') {
  const args = Object.fromEntries(process.argv.slice(3).map(a => a.split('=')).filter(x => x.length === 2))
  console.log('清除模拟数据：', clearSimulated(args))
} else {
  console.log('用法: node server/cli.js simulate [start=2025-12-01] [end=2026-08-31] [dailyBase=480] | clear')
}
