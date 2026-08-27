const fs=require('fs'),path=require('path');
const dir='apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console';
function walk(d){let out=[];
  for(const e of fs.readdirSync(d,{withFileTypes:true})){
    const full=path.join(d,e.name);
    if(e.isDirectory()){out=out.concat(walk(full));}
    else if(/\.(js|json)$/.test(e.name)){
      try{const c=fs.readFileSync(full,'utf8');
        if(c.includes('/online.svg')||c.includes('welcome.avatar')||c.includes('welcomeAvatar')) out.push(full);
      }catch(_){}
    }
  }
  return out;
}
walk(dir).forEach(f=>console.log(f));
