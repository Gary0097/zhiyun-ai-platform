import { db } from '../db.js'
import { runAgent } from '../harness.js'
import { ExecutionKernel } from './execution-kernel.js'
import { createLightweightRunner } from './adapters/lightweight-runner.js'
import { RuntimeStore } from './runtime-store.js'
import { TaskService } from './task-service.js'

export const runtimeStore = new RuntimeStore({ database: db })
export const executionKernel = new ExecutionKernel()
  .registerRunner('lightweight', createLightweightRunner({ runAgent }))
export const taskService = new TaskService({ database: db, kernel: executionKernel, store: runtimeStore })
