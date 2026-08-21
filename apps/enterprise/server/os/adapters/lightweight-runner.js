export function createLightweightRunner ({ runAgent }) {
  if (typeof runAgent !== 'function') throw new TypeError('runAgent adapter is required')
  return {
    kind: 'lightweight',
    run: request => runAgent({
      agentId: request.agentId,
      user: request.user,
      instruction: request.instruction,
      triggerType: request.triggerType
    })
  }
}
