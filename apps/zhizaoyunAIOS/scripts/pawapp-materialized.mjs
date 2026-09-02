// 判断锁定的 PawApp 是否已全部物化（无需 Git 即可启动）。
// 供 doctor.mjs 的 git 检查降级逻辑与 verify-no-git-boot.mjs 的无 Git 回归测试共用。
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

export function pawappsAllMaterialized (appRoot) {
  try {
    const lock = JSON.parse(readFileSync(join(appRoot, 'pawapps.lock.json'), 'utf8'))
    return (lock.apps || []).every(app => {
      const target = join(appRoot, 'runtime', 'pawapps', app.install_dir)
      const marker = join(target, '.pawapp-commit')
      try {
        return existsSync(marker) && readFileSync(marker, 'utf8').trim() === app.commit
          && existsSync(join(target, 'plugin.json')) && !existsSync(join(target, '.git'))
      } catch { return false }
    })
  } catch { return false }
}
