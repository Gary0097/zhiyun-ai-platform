const fs=require("fs"),path=require("path");
const root="apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw";
const hits=[];
function walk(d){
  let ents;
  try{ents=fs.readdirSync(d,{withFileTypes:true});}catch(e){return;}
  for(const en of ents){
    const full=path.join(d,en.name);
    if(en.isDirectory()){ walk(full); continue; }
    if(!/\.(py|js|json|html|svg)$/i.test(en.name)) continue;
    try{
      const s=fs.readFileSync(full,"utf8");
      const re=/online\.svg|avatar|default_avatar|default_agent/i;
      if(re.test(s)) hits.push(full.replace(root,"<qwenpaw>"));
    }catch(e){}
  }
}
walk(root);
console.log("Total:",hits.length);
console.log(hits.slice(0,80).join("\n"));
