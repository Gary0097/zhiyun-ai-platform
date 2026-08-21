// 清理验证测试残留：移除测试 Logo，查看最近一次助手聊天回复
import { init, db } from '../server/db.js'
init()
db.prepare("UPDATE business_setting SET value = '' WHERE key = 'brand.logo'").run()
console.log('测试 Logo 已移除')
const msgs = db.prepare("SELECT role, content FROM runtime_message ORDER BY id DESC LIMIT 2").all()
for (const m of msgs.reverse()) console.log(`[${m.role}]`, m.content.slice(0, 260))
