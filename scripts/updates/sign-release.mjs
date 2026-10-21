import { createPrivateKey, createPublicKey, createHash, sign } from 'node:crypto'
import { createReadStream, readFileSync, statSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { config, validateManifest } from './protocol.mjs'

try {
  const directory = process.argv[2]
  if (!directory) throw Error('需要待签名资产目录')
  const c = config('scripts/updates/channel.json')
  const key = createPrivateKey(process.env.AIOS_UPDATE_PRIVATE_KEY || '')
  if (key.asymmetricKeyType !== 'ed25519') throw Error('需要 Ed25519 签名密钥')
  const pub = createPublicKey(key).export({ type: 'spki', format: 'pem' }).toString()
  if (!c.publicKeys.includes(pub)) throw Error('签名密钥不匹配已审核的客户端公钥')
  const version = JSON.parse(readFileSync('apps/zhizaoyunAIOS/qwenpaw.lock.json')).version
  const commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  const assets = []
  for (const [platform, suffix] of [['win32', 'setup.exe'], ['linux', 'online-installer.zip']]) {
    const name = `zhiyun-ai-os-v${version}-${suffix}`
    const hash = createHash('sha256'); const path = join(directory, name)
    for await (const chunk of createReadStream(path)) hash.update(chunk)
    assets.push({ platform, name, size: statSync(path).size, sha256: hash.digest('hex') })
  }
  const manifest = validateManifest({ schema: 1, product: 'zhiyun-ai-os', version, commit, assets }, `v${version}`)
  const raw = Buffer.from(JSON.stringify(manifest, null, 2) + '\n')
  writeFileSync(join(directory, 'aios-update.json'), raw)
  writeFileSync(join(directory, 'aios-update.sig'), sign(null, raw, key))
  console.log(`Signed release manifest for ${version}; no release published`)
} catch { console.error('更新签名失败：请检查公私钥、版本锁和两平台待签名资产。'); process.exitCode = 1 }
