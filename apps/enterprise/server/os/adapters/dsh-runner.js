export function createDshRunner ({ runSession }) {
  if (typeof runSession !== 'function') throw new TypeError('runSession adapter is required')
  return {
    kind: 'dsh',
    run: request => runSession({
      tenantId: request.tenantId,
      taskId: request.taskId,
      instruction: request.instruction,
      user: request.user,
      contextSnapshotId: request.contextSnapshotId,
      metadata: request.metadata
    })
  }
}
