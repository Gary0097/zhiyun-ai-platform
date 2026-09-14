import { createPrivateKey, createPublicKey, createHash, sign, verify } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { config } from './protocol.mjs'

export function verifyPublisherKey(keys, privatePem) {
  const key = createPrivateKey(privatePem)
  if (key.asymmetricKeyType !== 'ed25519') throw Error('Publisher key must use Ed25519')
  const publicKey = createPublicKey(key)
  const der = publicKey.export({ type: 'spki', format: 'der' })
  const trusted = keys.some(pem => createPublicKey(pem).export({ type: 'spki', format: 'der' }).equals(der))
  if (!trusted) throw Error('Publisher key does not match a reviewed client trust root')
  const challenge = Buffer.from('AIOS publisher self-check; not a release manifest or installer')
  if (!verify(null, challenge, publicKey, sign(null, challenge, key))) throw Error('Publisher signature self-check failed')
  return createHash('sha256').update(der).digest('hex')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const channel = config(new URL('./channel.json', import.meta.url))
    const fingerprint = verifyPublisherKey(channel.publicKeys, process.env.AIOS_UPDATE_PRIVATE_KEY || '')
    console.log(`Publisher key matches client trust root; SHA256(SPKI DER): ${fingerprint}`)
    console.log('Cryptographic self-check only; no release asset created or published')
  } catch {
    console.error('Publisher verification failed: check the protected environment secret and reviewed client public key')
    process.exitCode = 1
  }
}
