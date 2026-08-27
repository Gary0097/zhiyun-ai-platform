const fs=require('fs');
const p='apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js';
const c=fs.readFileSync(p,'utf8');
console.log('has avatar:"/qwenpaw.png":', c.includes('avatar:"/qwenpaw.png"'));
console.log('has avatar:"/online.svg":', c.includes('avatar:"/online.svg"'));
console.log('count /qwenpaw.png:', (c.match(/\/qwenpaw\.png/g)||[]).length);
console.log('count /online.svg:', (c.match(/\/online\.svg/g)||[]).length);
