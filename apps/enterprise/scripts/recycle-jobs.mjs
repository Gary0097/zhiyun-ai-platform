// 一次性修复：删除测试残留的孤儿 Job 记录（805 为验证过程被中断的产物）
import { init, db } from '../server/db.js'
init()
const r = db.prepare("DELETE FROM runtime_scheduled_job WHERE data_origin = 'real' AND status = 'failed' AND failure_reason LIKE '%孤儿%'").run()
console.log('删除孤儿 Job:', r.changes)
