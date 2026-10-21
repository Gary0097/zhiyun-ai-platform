import { mkdirSync, readFileSync, existsSync, lstatSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { authenticate, compare, config, download, releaseAsset, small } from './protocol.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const command = process.argv[2] || 'check'
try {
  if (!['check', 'download'].includes(command)) throw Error('用法：client.mjs check|download')
  const c = config(join(root, 'scripts/updates/channel.json'))
  const current = JSON.parse(readFileSync(join(root, 'apps/zhizaoyunAIOS/qwenpaw.lock.json'))).version
  const release = JSON.parse(await small(`https://api.github.com/repos/${c.repository}/releases/latest`))
  if (release.draft || release.prerelease || typeof release.tag_name !== 'string') throw Error('更新频道未提供正式发布')
  const version = release.tag_name.replace(/^v/, '')
  if (compare(version, current) <= 0) {
    console.log(JSON.stringify({ available: false, current, message: '当前没有更高版本的智造云正式发布' }))
  } else {
    const raw = await small(releaseAsset(release, 'aios-update.json', c.repository))
    const signature = await small(releaseAsset(release, 'aios-update.sig', c.repository), 256)
    const manifest = authenticate(raw, signature, c.publicKeys, release.tag_name)
    const asset = manifest.assets.find(a => a.platform === process.platform)
    if (!asset) throw Error('新版尚未提供当前平台更新包')
    const result = { available: true, current, version: manifest.version, size: asset.size, release: `https://github.com/${c.repository}/releases/tag/${release.tag_name}` }
    if (command === 'download') {
      // Reject links at every ancestor; cache must stay inside this installation.
      const cache = join(root, '.aios-updates', 'downloads')
      for (let p = cache; ; p = dirname(p)) {
        if (existsSync(p) && lstatSync(p).isSymbolicLink()) throw Error('更新路径包含链接')
        if (dirname(p) === p) break
      }
      mkdirSync(cache, { recursive: true, mode: 0o700 })
      const target = join(cache, `${Date.now()}-${asset.name}`)
      await download(releaseAsset(release, asset.name, c.repository), asset, target)
      result.path = target
      result.sha256 = asset.sha256
    }
    console.log(JSON.stringify(result))
  }
} catch (e) { console.error(e.message); process.exitCode = 1 }
