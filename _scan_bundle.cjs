const fs = require('fs');
const f = 'apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js';
const c = fs.readFileSync(f, 'utf8');
// find the snippet around welcome avatar setting at idx 5732961
const idx = 5732961;
console.log('=== context around welcome avatar (idx 5732961) ===');
console.log(c.slice(idx - 3000, idx + 200).replace(/\n/g, '\\n'));
