const fs = require('fs');
const f = 'apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js';
const c = fs.readFileSync(f, 'utf8');
function show(pat, label) {
  console.log('########## ' + label + ' ##########');
  let idx = 0, n = 0;
  while ((idx = c.indexOf(pat, idx)) !== -1) {
    console.log('--- occurrence ' + (++n) + ' @ ' + idx + ' ---');
    console.log(c.slice(Math.max(0, idx-120), idx + pat.length + 120).replace(/\n/g, '\\n'));
    idx += pat.length;
  }
  if (!n) console.log('(none)');
}
show('online', 'online');
show('qwenpawBack', 'qwenpawBack');
show('creator-logo', 'creator-logo');
