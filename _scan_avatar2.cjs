const fs=require("fs"),path=require("path");
const root="apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw";
const found=[];
function walk(d){
  let ents;
  try{ents=fs.readdirSync(d,{withFileTypes:true});}catch(e){return;}
  for(const en of ents){
    const full=path.join(d,en.name);
    if(en.isDirectory()){ walk(full); continue; }
    if(/avatar|agent|logo|icon|online/i.test(en.name)) found.push(full);
  }
}
walk(root);
console.log(found.join("\n"));
