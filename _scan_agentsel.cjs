const fs = require('fs');
const f = 'apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js';
const c = fs.readFileSync(f, 'utf8');
const idx = 29000;
console.log('=== agent selector region (29000-33000) ===');
const seg = c.slice(idx, idx + 4000);
console.log(seg.replace(/\n/g, '\\n'));
