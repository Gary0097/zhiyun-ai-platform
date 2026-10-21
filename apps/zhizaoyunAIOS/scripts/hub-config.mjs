import { readFileSync, writeFileSync } from 'node:fs'
import { networkInterfaces } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export function lanAddress(interfaces) {
  const addresses = Object.values(interfaces).flat().filter(x => x && !x.internal &&
    (x.family === 'IPv4' || x.family === 4) &&
    /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(x.address))
  return addresses[0]?.address || '127.0.0.1'
}

export function renderHubConfig(source, address) {
  // Preserve administrator-specified public URLs and all other settings.
  return source.replace(/^(\s*public_base_url:\s*)http:\/\/127\.0\.0\.1:8000(?=\s|$)/m,
    (_, prefix) => `${prefix}http://${address}:8000`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
  const source = readFileSync(join(root, 'hub.yaml'), 'utf8')
  writeFileSync(join(root, 'hub.runtime.yaml'), renderHubConfig(source, lanAddress(networkInterfaces())), 'utf8')
}
