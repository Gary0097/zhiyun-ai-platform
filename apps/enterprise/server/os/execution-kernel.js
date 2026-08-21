import { RUNNER_KIND, createExecutionRequest, normalizeExecutionResult } from './contracts.js'

export class ExecutionKernel {
  #runners = new Map()

  registerRunner (kind, runner) {
    if (!Object.values(RUNNER_KIND).includes(kind)) throw new TypeError(`Unsupported runner: ${kind}`)
    if (!runner || typeof runner.run !== 'function') throw new TypeError('Runner must implement run(request)')
    this.#runners.set(kind, runner)
    return this
  }

  chooseRunner (request) {
    if (request.routeHint) return request.routeHint
    const complex = request.metadata?.requiresApproval || request.metadata?.requiresSubagents || request.metadata?.longRunning
    return complex ? RUNNER_KIND.DSH : RUNNER_KIND.LIGHTWEIGHT
  }

  async run (input) {
    const request = createExecutionRequest(input)
    const kind = this.chooseRunner(request)
    const runner = this.#runners.get(kind)
    if (!runner) throw new Error(`Runner not registered: ${kind}`)
    try {
      const result = await runner.run(request)
      return normalizeExecutionResult(result, { runner: kind })
    } catch (error) {
      return normalizeExecutionResult({ status: 'failed', error: error.message }, { runner: kind })
    }
  }
}
