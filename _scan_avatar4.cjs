const fs=require('fs');
const c=fs.readFileSync('apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js','utf8');
const pats=['avatar:','.avatar','avatar,','avatar}','senderAvatar','agentLogo','avatarUrl','icon:'];
for(const p of pats){
  const re=new RegExp(p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g');
  let m,n=0;
  while((m=re.exec(c))&&n<3){
    console.log(p+'  ||  '+c.slice(Math.max(0,m.index-70),m.index+50).replace(/\n/g,' '));
    n++;
  }
}
