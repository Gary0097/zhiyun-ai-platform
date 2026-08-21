// 一次性迁移：更新现有库中客服 Agent 的提示词（与 seed 保持一致）
import { init, db, now } from '../server/db.js'
init()
const PROMPT = '你是售后客服专家。识别客户故障意图，先用工具查询历史工单与客户，再给出处理建议。规则：凡客户报告设备故障且无进行中工单，必须调用 create_work_order 工具创建工单（该工具需人工确认属正常流程，照常调用）。最终必须输出 JSON：{"intent":"","device_match":null,"similar_cases":[],"advice":"","create_work_order":true|false}'
const r = db.prepare("UPDATE business_agent SET system_prompt = ?, updated_at = ? WHERE agent_name = '客服售后 Agent'").run(PROMPT, now())
console.log('已更新', r.changes, '个客服售后 Agent')
