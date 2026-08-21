// 自动任务执行中心：Scheduler → Job → Worker(runAgent) → 结果/日志；job_lock 防重复执行
import { db, now } from './db.js'
import { evaluateCondition } from './tools.js'
import { logOperation } from './auth.js'
import { runtimeStore, taskService } from './os/runtime.js'

/** 5 字段 cron 解析（分 时 日 月 周），支持 * / ,- 与数字 */
export function cronMatches (expr, date) {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) return false
  const values = [date.getMinutes(), date.getHours(), date.getDate(), date.getMonth() + 1, date.getDay()]
  const ranges = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 6]]
  return fields.every((f, i) => matchField(f, values[i], ranges[i]))
}

function matchField (field, value, [min, max]) {
  return field.split(',').some(part => {
    const stepM = part.match(/^(\*|\d+-\d+)\/(\d+)$/)
    if (stepM) {
      const step = Number(stepM[2])
      let lo = min; let hi = max
      if (stepM[1] !== '*') { const [a, b] = stepM[1].split('-').map(Number); lo = a; hi = b }
      return value >= lo && value <= hi && (value - lo) % step === 0
    }
    const rangeM = part.match(/^(\d+)-(\d+)$/)
    if (rangeM) { const a = Number(rangeM[1]); const b = Number(rangeM[2]); return value >= a && value <= b }
    if (part === '*') return true
    return Number(part) === value
  })
}

class JobLockError extends Error { constructor (taskId) { super(`任务 ${taskId} 已有运行中 Job（job_lock）`); this.status = 409 } }

/** 触发到期任务：cron 到分钟级；interval 按上次调度时间；condition 每次评估
 *  上次运行只统计 data_origin='real' 的 Job——模拟历史含未来日期，不得压制真实调度 */
export async function tick (serverTick = true) {
  const nowMs = Date.now()
  const tasks = db.prepare("SELECT * FROM business_scheduled_task WHERE status = 'active'").all()
  const fired = []
  for (const task of tasks) {
    let due = false
    if (task.trigger_type === 'cron' && task.cron) {
      // 以分钟对齐判断当前分钟是否命中（同一分钟内多次 tick 只触发一次，靠 job_lock + pending 检查）
      const lastPending = db.prepare("SELECT 1 FROM runtime_scheduled_job WHERE task_id = ? AND data_origin = 'real' AND scheduled_at >= ?").get(task.task_id, new Date(Math.floor(nowMs / 60000) * 60000).toISOString())
      if (!lastPending && cronMatches(task.cron, new Date(nowMs))) due = true
    } else if (task.trigger_type === 'interval' && task.interval_seconds) {
      const last = db.prepare("SELECT MAX(finished_at) AS f FROM runtime_scheduled_job WHERE task_id = ? AND data_origin = 'real'").get(task.task_id)?.f
      if (!last || nowMs - new Date(last).getTime() >= task.interval_seconds * 1000) due = true
    } else if (task.trigger_type === 'condition') {
      const evalRes = evaluateCondition(task.tenant_id, task.condition_tool, task.condition_expr)
      // 成功运行压制 1 小时；失败/未完成运行只压制 5 分钟（失败应较快重试）
      const lastRun = db.prepare(`SELECT 1 FROM runtime_scheduled_job WHERE task_id = ? AND data_origin = 'real' AND (
        (status = 'success' AND scheduled_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 hour')) OR
        (status != 'success' AND scheduled_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-5 minutes')))`).get(task.task_id)
      if (evalRes.met && !lastRun) { due = true; task._condition_detail = evalRes.detail }
    }
    // 顺序执行：本地推理网关并发能力有限，避免多任务同时排队。
    // 单任务异常（如 JobLock/网关故障）只记日志跳过，绝不向上抛——tick 跑在 setInterval
    // 里，未捕获异常会杀死整个平台进程（2026-08-21 凌晨 JobLockError 崩溃事故根因）。
    if (due) {
      try {
        fired.push(await runTaskNow(task.task_id, serverTick ? 'scheduler' : 'manual', task._condition_detail))
      } catch (e) {
        console.warn(`[scheduler] 任务 ${task.task_id} 触发失败（已跳过）: ${e.message}`)
      }
    }
  }
  return fired
}

/** 立即执行一个任务（手动/调度共用）；job_lock 保证同一任务不并发重复执行 */
export async function runTaskNow (taskId, triggerSource = 'manual', conditionDetail = null, operatorUser = null) {
  const task = db.prepare('SELECT * FROM business_scheduled_task WHERE task_id = ?').get(taskId)
  if (!task) throw Object.assign(new Error('任务不存在'), { status: 404 })

  const lock = db.prepare("SELECT 1 FROM runtime_scheduled_job WHERE task_id = ? AND status IN ('pending','running','retrying')").get(taskId)
  if (lock) throw new JobLockError(taskId)

  const input = JSON.parse(task.input || '{}')
  const jobId = db.prepare(`INSERT INTO runtime_scheduled_job (task_id, tenant_id, scheduled_at, status, data_origin) VALUES (?,?,?, 'pending', 'real')`)
    .run(taskId, task.tenant_id, now()).lastInsertRowid

  const execute = async (attempt) => {
    db.prepare("UPDATE runtime_scheduled_job SET started_at = ?, status = 'running' WHERE job_id = ?").run(now(), jobId)
    try {
      const res = await taskService.executeScheduledTask({
        scheduledTask: task,
        instruction: input.instruction + (conditionDetail ? `（触发条件：${conditionDetail}）` : ''),
        triggerSource,
        attempt
      })
      if (res.status !== 'succeeded') {
        throw Object.assign(new Error(res.error || `AI-OS execution ${res.status}`), {
          osTaskId: res.osTaskId,
          osExecutionId: res.osExecutionId
        })
      }
      db.prepare("UPDATE runtime_scheduled_job SET status = 'success', finished_at = ?, execution_id = ? WHERE job_id = ?")
        .run(now(), res.executionId, jobId)
      return { ...res, jobId: Number(jobId), status: 'success' }
    } catch (e) {
      if (attempt < task.max_retry) {
        db.prepare("UPDATE runtime_scheduled_job SET status = 'retrying', retry_count = ? WHERE job_id = ?").run(attempt, jobId)
        const osTask = taskService.ensureScheduledTask(task)
        if (e.osExecutionId) runtimeStore.saveCheckpoint({
          task: osTask,
          executionId: e.osExecutionId,
          stepKey: 'retry.scheduled',
          state: { nextAttempt: attempt + 1, reason: e.message },
          safeToResume: true
        })
        return execute(attempt + 1)
      }
      db.prepare("UPDATE runtime_scheduled_job SET status = 'failed', finished_at = ?, failure_reason = ? WHERE job_id = ?")
        .run(now(), e.message.slice(0, 500), jobId)
      // Dead Letter：失败任务进入 audit 供管理员处理（PRD §72）
      db.prepare("INSERT INTO audit_audit_log (tenant_id, category, payload, created_at, data_origin) VALUES (?, 'dead_letter', ?, ?, 'real')")
        .run(task.tenant_id, JSON.stringify({ task_id: taskId, job_id: Number(jobId), reason: e.message }), now())
      return { jobId: Number(jobId), status: 'failed', error: e.message }
    }
  }
  const result = await execute(0)
  if (operatorUser) logOperation({ tenantId: task.tenant_id, userId: operatorUser.id, module: 'automation', action: triggerSource === 'manual' ? '手动执行任务' : '调度执行任务', resourceType: 'scheduled_task', resourceId: taskId })
  return result
}

export function startSchedulerLoop (intervalMs = 30000) {
  // 回收孤儿 Job：上次进程中断遗留的 running/pending 任务标记失败，释放 job_lock
  const orphaned = db.prepare("UPDATE runtime_scheduled_job SET status = 'failed', finished_at = ?, failure_reason = '进程中断遗留的孤儿任务，已自动回收' WHERE status IN ('running','pending','retrying') AND data_origin = 'real' AND scheduled_at < datetime('now', '-10 minutes')")
  const r = orphaned.run(now())
  if (r.changes) console.log(`[scheduler] 回收孤儿 Job ${r.changes} 个`)
  const timer = setInterval(() => {
    try { tick(true) } catch (e) { if (e.status !== 409) console.error('[scheduler]', e.message) }
  }, intervalMs)
  timer.unref()
  return timer
}
