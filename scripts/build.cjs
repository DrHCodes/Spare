const fs=require('node:fs');const path=require('node:path');
const root=path.resolve(__dirname,'..');const out=path.join(root,'dist');
fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out);
for(const f of ['index.html','app.js','style.css','icon.svg'])fs.copyFileSync(path.join(root,'web',f),path.join(out,f));
console.log('Built 4 frontend files. No API keys or Python backend deployed.');
