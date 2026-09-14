import { createHash } from 'node:crypto'
import { createReadStream, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { authenticate, config } from './protocol.mjs'

// Both update entry points consume these exact assets from the same release.
export async function verifyReleaseAssets(directory, tag, commit, keys) {
  const manifest = authenticate(readFileSync(join(directory, 'aios-update.json')), readFileSync(join(directory, 'aios-update.sig')), keys, tag)
  if (manifest.commit !== commit) throw Error('签名清单提交与发布标签不一致')
  if (manifest.assets.length !== 2 || !['win32', 'linux'].every(p => manifest.assets.some(a => a.platform === p))) throw Error('发布必须同时包含 Windows 完整安装包与 Linux 安装包')
  for (const asset of manifest.assets) {
    let size = 0
    const hash = createHash('sha256')
    for await (const chunk of createReadStream(join(directory, asset.name))) {
      size += chunk.length
      if (size > asset.size) throw Error('发布资产大小不匹配')
      hash.update(chunk)
    }
    if (size !== asset.size || hash.digest('hex') !== asset.sha256) throw Error('发布资产摘要或大小不匹配')
  }
  return manifest
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const [, , directory, tag, commit] = process.argv
    if (!directory || !tag || !commit) throw Error('用法：verify-release-assets.mjs 资产目录 vX.Y.Z 完整提交号')
    await verifyReleaseAssets(directory, tag, commit, config(new URL('./channel.json', import.meta.url)).publicKeys)
    console.log('完整安装包与在线更新资产校验通过：签名、版本、提交、大小和摘要一致。')
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}
