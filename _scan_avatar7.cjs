const fs = require('fs');
const f = 'apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js';
const c = fs.readFileSync(f, 'utf8');
let idx = 0, n = 0;
while ((idx = c.indexOf('avatar', idx)) !== -1) {
  console.log('--- occurrence ' + (++n) + ' @ ' + idx + ' ---');
  console.log(c.slice(Math.max(0, idx-200), idx + 120).replace(/\n/g, '\\n'));
  console.log();
  idx += 6;
}
