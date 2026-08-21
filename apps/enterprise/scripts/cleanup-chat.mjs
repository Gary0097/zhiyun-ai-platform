// 清理测试污染数据：乱码会话、重复售后工单
import { init, db } from '../server/db.js'
init()
// 删除含 U+FFFD 乱码的消息所在会话
const badMsgs = db.prepare("SELECT DISTINCT conversation_id FROM runtime_message WHERE content LIKE '%' || char(0xFFFD) || '%'").all()
for (const m of badMsgs) {
  db.prepare('DELETE FROM runtime_message WHERE conversation_id = ?').run(m.conversation_id)
  db.prepare('DELETE FROM runtime_conversation WHERE id = ?').run(m.conversation_id)
}
console.log('删除乱码会话：', badMsgs.length, '个')
// 清理测试产生的重复售后工单（保留种子 2 条：id 1、2）
const r = db.prepare('DELETE FROM business_after_sale WHERE id > 2').run()
console.log('清理测试售后工单：', r.changes, '条')
// 清理空会话
const empty = db.prepare('DELETE FROM runtime_conversation WHERE id NOT IN (SELECT DISTINCT conversation_id FROM runtime_message)').run()
console.log('清理空会话：', empty.changes, '个')
