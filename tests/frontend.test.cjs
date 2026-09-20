const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'web/index.html'),'utf8'),js=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
test('one voice entry, no duration or difficulty selection cards',()=>{assert.match(html,/id="connect"/);assert.doesNotMatch(html,/<select|data-minutes|data-level/);});
test('no browser speech synthesis or SpeechRecognition fallback',()=>{assert.doesNotMatch(js,/new SpeechSynthesisUtterance|window\.speechSynthesis|new (?:webkit)?SpeechRecognition/);});
test('full duplex audio and echo cancellation requested',()=>{assert.match(js,/direction:'sendrecv'/);assert.match(js,/echoCancellation:true/);});
test('microphone off on teardown',()=>{assert.match(js,/stream\.getTracks\(\)\.forEach\(t=>t\.stop\(\)\)/);});
test('no API key collection in interface',()=>{assert.doesNotMatch(html,/id="(?:apiKey|openaiKey|gradiumKey)"/);});
test('all JavaScript element IDs are in HTML',()=>{for(const match of js.matchAll(/\$\('([^']+)'\)/g))assert.ok(html.includes(`id="${match[1]}"`),match[1]);});
test('static build excludes backend and secrets',()=>{require('../scripts/build.cjs');assert.deepEqual(fs.readdirSync(path.join(root,'dist')).sort(),['app.js','icon.svg','index.html','style.css']);});
