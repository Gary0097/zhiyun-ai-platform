import assert from 'node:assert/strict'
import net from 'node:net'
import { listenPort } from '../apps/zhizaoyunAIOS/scripts/runtime-env.mjs'
import { diagnose } from '../apps/zhizaoyunAIOS/scripts/doctor.mjs'

assert.equal(listenPort(), 8088)
assert.equal(listenPort('18090'), 18090)
for (const invalid of ['', '0', '65536', '-1', '1.5', '1e3', '80;echo unsafe', ' 80']) assert.throws(() => listenPort(invalid))
// A supplied descriptor is an already validated in-process result, not an
// environment receipt. Keep the real foreign listener alive during diagnosis.
const server = net.createServer(socket => socket.end())
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const port = server.address().port
try {
  const runtime = { command: null, python: process.execPath, output: 'missing', version: '2.2.2', source: 'missing' }
  const printed = [], originalLog = console.log
  let code
  console.log = value => printed.push(value)
  try { code = await diagnose({ runtime, port, jsonOutput: true }) } finally { console.log = originalLog }
  assert.equal(code, 1)
  const report = JSON.parse(printed.join('\n'))
  assert.equal(report.checks.find(c => c.id === 'qwenpaw-cli').status, 'fail')
  assert.equal(report.checks.find(c => c.id === 'port-' + port).status, 'fail')
  assert.equal(report.checks.find(c => c.id === 'directories').status, 'pass')
  await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => { socket.end(); resolve() })
    socket.on('error', reject)
  })
} finally { await new Promise(resolve => server.close(resolve)) }
console.log('PASS startup diagnostics: strict ports, missing runtime rejection, foreign listener preserved')
