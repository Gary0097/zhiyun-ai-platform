import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, lstatSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

// Language-only preset: never traverse credentials, change models or enable a channel.
export function chineseSettings(value, kind) {
  const result = structuredClone(value)
  if (kind === 'settings') result.language = 'zh'
  else {
    if (kind === 'config') {
      result.agents ??= {}
      result.agents.language = 'zh'
    } else result.language = 'zh'
    result.channels ??= {}
    const voice = result.channels.voice ??= {}
    voice.language = 'zh-CN'
    if (!voice.tts_voice || voice.tts_voice === 'en-US-Journey-D') voice.tts_voice = 'cmn-CN-Wavenet-A'
    if (!voice.enabled && (!voice.stt_provider || voice.stt_provider === 'deepgram')) voice.stt_provider = 'google'
    if (!voice.welcome_greeting || /^(Hi!|Hello!|你好，我是QwenPaw)/.test(voice.welcome_greeting)) voice.welcome_greeting = '你好，我是智造云AIOS，请问有什么可以帮助你？'
    const sip = result.channels.sip ??= {}
    sip.language = 'zh-CN'
    if (!sip.welcome_greeting || sip.welcome_greeting === '你好，我是QwenPaw') sip.welcome_greeting = '你好，我是智造云AIOS'
  }
  return result
}

export function applyChineseDefaults(workspace, { scanHub = false } = {}) {
  mkdirSync(workspace, { recursive: true })
  let changed = 0
  const update = (path, kind) => {
    if (existsSync(path) && lstatSync(path).isSymbolicLink()) throw new Error('语言配置路径不能是链接')
    const original = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/, '')) : {}
    const next = chineseSettings(original, kind)
    if (JSON.stringify(original) !== JSON.stringify(next)) {
      writeFileSync(path, JSON.stringify(next, null, 2) + '\n', 'utf8')
      changed++
    }
  }
  update(join(workspace, 'settings.json'), 'settings')
  update(join(workspace, 'config.json'), 'config')
  const agents = join(workspace, 'workspaces')
  if (existsSync(agents)) for (const item of readdirSync(agents, { withFileTypes: true })) {
    if (!item.isDirectory() || item.isSymbolicLink()) continue
    const path = join(agents, item.name, 'agent.json')
    if (existsSync(path)) update(path, 'agent')
  }
  if (scanHub) {
    const runtimes = join(workspace, 'hub', 'runtimes')
    if (existsSync(runtimes)) for (const item of readdirSync(runtimes, { withFileTypes: true })) {
      if (!item.isDirectory() || item.isSymbolicLink()) continue
      const member = join(runtimes, item.name, 'working')
      if (existsSync(member) && !lstatSync(member).isSymbolicLink()) changed += applyChineseDefaults(member)
    }
  }
  return changed
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const workspace = join(dirname(fileURLToPath(import.meta.url)), '..', 'workspace')
  console.log(`中文默认配置已就绪，更新 ${applyChineseDefaults(workspace, { scanHub: true })} 个配置文件。`)
}
