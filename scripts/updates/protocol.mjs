import { createHash, createPublicKey, verify } from 'node:crypto'
import { createWriteStream, readFileSync, renameSync, rmSync } from 'node:fs'
import { Transform } from 'node:stream'
import { pipeline } from 'node:stream/promises'

export const VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/
export function compare(a, b) {
  if (![a, b].every(v => typeof v === 'string' && VERSION.test(v) && v.split('.').every(n => Number.isSafeInteger(+n)))) throw Error('仅支持正式版 x.y.z')
  for (let i = 0; i < 3; i++) {
    const d = +a.split('.')[i] - +b.split('.')[i]
    if (d) return Math.sign(d)
  }
  return 0
}
export function validateManifest(m, tag) {
  if (m.schema !== 1 || m.product !== 'zhiyun-ai-os' || compare(m.version, m.version) !== 0 || tag !== `v${m.version}`) throw Error('更新清单版本或产品不匹配')
  if (!/^[a-f0-9]{40}$/.test(m.commit) || !Array.isArray(m.assets) || !m.assets.length) throw Error('更新清单不完整')
  const platforms = new Set()
  for (const a of m.assets) {
    if (!['win32', 'linux'].includes(a.platform) || platforms.has(a.platform)) throw Error('更新平台无效或重复')
    platforms.add(a.platform)
    const name = a.platform === 'win32' ? `zhiyun-ai-os-v${m.version}-setup.exe` : `zhiyun-ai-os-v${m.version}-online-installer.zip`
    if (a.name !== name || !/^[a-f0-9]{64}$/.test(a.sha256) || !Number.isSafeInteger(a.size) || a.size < 1 || a.size > 16 * 1024 ** 3) throw Error('更新资产无效')
  }
  return m
}
export function authenticate(raw, signature, keys, tag) {
  if (!Array.isArray(keys) || !keys.length) throw Error('此安装尚未配置可信更新公钥，请先安装启用签名更新的正式安装包')
  const valid = keys.some(pem => {
    try { const key = createPublicKey(pem); return key.asymmetricKeyType === 'ed25519' && verify(null, raw, key, signature) } catch { return false }
  })
  if (!valid) throw Error('更新签名无效，已拒绝安装')
  return validateManifest(JSON.parse(raw.toString('utf8')), tag)
}
export async function small(url, max = 1024 * 1024, fetcher = fetch) {
  const r = await fetcher(url, { headers: { 'User-Agent': 'Zhizaoyun-AIOS-Updater', Accept: 'application/vnd.github+json' }, signal: AbortSignal.timeout(30000) })
  if (!r.ok) throw Error(`更新服务器返回 HTTP ${r.status}`)
  let size = 0; const chunks = []
  for await (const chunk of r.body) { size += chunk.length; if (size > max) throw Error('更新响应超限'); chunks.push(chunk) }
  return Buffer.concat(chunks)
}
export function releaseAsset(release, name, repository) {
  const matches = (release.assets || []).filter(a => a.name === name)
  const url = `https://github.com/${repository}/releases/download/${release.tag_name}/${name}`
  if (matches.length !== 1 || matches[0].browser_download_url !== url) throw Error(`发布缺少可信资产：${name}`)
  return url
}
export async function download(url, asset, target, fetcher = fetch) {
  const part = `${target}.part`
  const hash = createHash('sha256'); let size = 0
  try {
    const r = await fetcher(url, { signal: AbortSignal.timeout(60 * 60 * 1000) })
    if (!r.ok || !r.body) throw Error(`下载失败 HTTP ${r.status}`)
    const meter = new Transform({ transform(chunk, encoding, cb) {
      size += chunk.length
      if (size > asset.size) return cb(Error('下载文件超出签名清单大小'))
      hash.update(chunk); cb(null, chunk)
    } })
    await pipeline(r.body, meter, createWriteStream(part, { flags: 'wx', mode: 0o600 }))
    if (size !== asset.size || hash.digest('hex') !== asset.sha256) throw Error('下载文件校验失败')
    renameSync(part, target)
  } catch (e) {
    // An exclusive-create collision belongs to another downloader.
    if (e.code !== 'EEXIST') rmSync(part, { force: true })
    throw e
  }
}
export function config(path) {
  const c = JSON.parse(readFileSync(path, 'utf8'))
  if (c.schema !== 1 || c.repository !== 'Gary0097/zhiyun-ai-platform' || !Array.isArray(c.publicKeys)) throw Error('更新频道配置无效')
  return c
}
