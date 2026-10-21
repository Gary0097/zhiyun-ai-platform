import assert from 'node:assert/strict'
import { chineseSettings } from './chinese-defaults.mjs'

const original = { language: 'en', model: { provider_id: 'keep-provider', model_id: 'keep-model' },
  channels: { voice: { enabled: false, language: 'en-US', tts_voice: 'en-US-Journey-D', twilio_auth_token: 'synthetic-sentinel' } } }
const next = chineseSettings(original, 'agent')
assert.equal(next.language, 'zh')
assert.equal(next.channels.voice.language, 'zh-CN')
assert.equal(next.channels.voice.tts_voice, 'cmn-CN-Wavenet-A')
assert.equal(next.channels.voice.enabled, false)
assert.equal(next.channels.voice.twilio_auth_token, 'synthetic-sentinel')
assert.deepEqual(next.model, original.model)
assert.equal(original.language, 'en')
assert.deepEqual(chineseSettings(next, 'agent'), next)
assert.equal(chineseSettings({ theme: 'dark' }, 'settings').theme, 'dark')
console.log('中文语言、默认语音、幂等及模型/凭据/开关保留检查通过。')
