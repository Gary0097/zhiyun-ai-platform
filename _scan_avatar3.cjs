const fs=require('fs'),path=require('path');
const dir='apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets';
for(const f of fs.readdirSync(dir)){
  if(!f.endsWith('.js'))continue;
  const c=fs.readFileSync(path.join(dir,f),'utf8');
  const re=/avatar\s*[:=]\s*([^,;)\s\"'\`]+)/g;
  let m; const found=[];
  while((m=re.exec(c))) found.push(m[1]);
  if(found.length){
    console.log('### '+f+' ('+found.length+')');
    console.log([...new Set(found)].join('\n'));
  }
}
