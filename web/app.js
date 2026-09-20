/* Live audio only. No browser speech synthesis, prerecorded workouts, or invented state. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
let pc=null,stream=null,dc=null,sid=null,poll=null,ping=null,connecting=false,muted=false,wakeLock=null;
let saved='';try{saved=localStorage.getItem('spare-voice-url')||'';}catch{}
let base=saved||((location.protocol==='http:'||location.protocol==='https:')?location.origin:'http://localhost:7860');
let access='',misses=0;
const fmt=x=>{const s=Math.max(0,Math.ceil(x||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;};
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
async function api(path,body){
 const r=await fetch(base+path,{method:body?'POST':'GET',headers:{...(body?{'Content-Type':'application/json'}:{}),...(access?{'Authorization':'Bearer '+access}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(25000)});
 let data;try{data=await r.json();}catch{throw Error('This address serves the interface, not the voice backend. Start the Python server, or set its URL in Connection.');}
 if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`Server returned ${r.status}.`);return data;
}
function label(text,active=false){$('connectionStatus').textContent=text;$('connectionStatus').classList.toggle('active',active);}
function configCopy(c){$('providerInfo').textContent=`Speech: ${c.speech_provider}. Reasoning: General Compute / ${c.model}. ${c.missing?.length?'Missing: '+c.missing.join(', '):'Keys present; live access not yet verified.'}`;}
function iceDone(p){return new Promise((resolve,reject)=>{if(p.iceGatheringState==='complete')return resolve();const timeout=setTimeout(()=>{p.removeEventListener('icegatheringstatechange',change);reject(Error('Audio negotiation timed out. Check the network or ICE configuration.'));},18000);function change(){if(p.iceGatheringState==='complete'){clearTimeout(timeout);p.removeEventListener('icegatheringstatechange',change);resolve();}}p.addEventListener('icegatheringstatechange',change);});}
async function start(){
 if(connecting||pc)return;
 connecting=true;$('connect').disabled=true;notice('');label('CONNECTING');
 try{
  if(!window.isSecureContext)throw Error('Microphone access needs HTTPS or localhost. Open this app through the Python server, not a downloaded HTML file.');
  const cfg=await api('/api/config');configCopy(cfg);
  if(!cfg.voice_installed)throw Error('Voice dependencies are not installed. Use START-SPARE.command or uv sync --extra voice on your computer.');
  if(cfg.missing?.length)throw Error('Add these keys privately to agent/.env: '+cfg.missing.join(', ')+'. There is no browser-voice fallback.');
  if(cfg.access_required&&!access){$('settingsDialog').showModal();throw Error('Enter your private Spare access code in Connection settings. Do not enter an API key.');}
  stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
  pc=new RTCPeerConnection({iceServers:cfg.ice_servers||[]});
  const own=pc;pc.addTransceiver(stream.getAudioTracks()[0],{direction:'sendrecv',streams:[stream]});
  pc.ontrack=async e=>{$('remoteAudio').srcObject=e.streams[0]||new MediaStream([e.track]);try{await $('remoteAudio').play();}catch{$('enableAudio').hidden=false;}};
  dc=pc.createDataChannel('spare-control');
  dc.onopen=()=>{ping=setInterval(()=>{if(dc?.readyState==='open')dc.send('ping '+Date.now());},1000);};
  dc.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='signalling'&&m.message?.type==='peerLeft'){disconnect(false);notice('The voice server ended the connection. Your workout is no longer running.');}}catch{}};
  pc.onconnectionstatechange=()=>{if(own!==pc)return;const state=pc.connectionState;if(state==='connected'){label('CONNECTED · LISTENING',true);}else if(['failed','disconnected'].includes(state)){disconnect(false);notice('Audio connection lost. Movement will pause. Reconnect before continuing.');}};
  await pc.setLocalDescription(await pc.createOffer());await iceDone(pc);
  const answer=await api('/api/offer',{sdp:pc.localDescription.sdp,type:pc.localDescription.type});sid=answer.session_id;
  await pc.setRemoteDescription({sdp:answer.sdp,type:answer.type});
  $('connect').hidden=true;$('consent').hidden=true;$('liveControls').hidden=false;
  $('subtext').textContent='Speak naturally. You can interrupt with “I need a break.”';
  $('technical').textContent=`Speech: ${cfg.speech_provider}\nReasoning: ${cfg.model}\nWaiting for a live voice response…`;
  try{wakeLock=await navigator.wakeLock?.request('screen');}catch{}
  poll=setInterval(refresh,700);await refresh();
 }catch(e){await disconnect(true);notice(e.name==='NotAllowedError'?'Microphone access was declined. Allow it in your browser to use voice.':e.message||'Could not connect.');}
 finally{connecting=false;$('connect').disabled=false;}
}
async function refresh(){
 if(!sid)return;
 try{
  const s=await api('/api/session/'+sid);misses=0;
  if(s.error)notice(s.error);
  $('orb').classList.toggle('speaking',s.bot_speaking);$('orb').classList.toggle('listening',s.user_speaking);
  const stage=s.generating?'DESIGNING YOUR SESSION':s.bot_speaking?'SPARE IS SPEAKING':s.user_speaking?'LISTENING TO YOU':s.workout?.status==='paused'?'PAUSED · SAY READY TO CONTINUE':'YOUR VOICE LEADS';
  $('stateLabel').textContent=stage;
  if(s.caption)$('prompt').textContent=s.caption;
  $('understood').textContent=s.effort?`${s.minutes} minutes · target ${s.effort.target_effort}/10 · ${s.effort.anchor}. ${s.effort.needs_confirmation?'Spare will confirm this interpretation.':''}`:s.minutes?`${s.minutes} minutes. Waiting for your effort preference.`:'Tell Spare how much time you have.';
  if(s.workout){const w=s.workout;$('sessionInfo').hidden=false;$('timeLeft').textContent=fmt(w.seconds_left);$('effortScore').textContent=`${w.effort}/10`;$('currentExercise').textContent=w.current_name||'Finished';$('pause').disabled=w.status!=='running';if(w.status==='ended')$('subtext').textContent='Your session has ended. Use End session to disconnect the microphone.';}
  if(s.inference)$('technical').textContent=`Reasoning: ${s.inference.provider} / ${s.inference.model}\nWorkout generation: ${s.inference.seconds}s\nRequests: ${s.design_requests}\n${JSON.stringify(s.inference.usage||{},null,2)}\nMovement timer, not verified repetitions. No total-cost estimate.`;
 }catch(e){if(++misses>=3){await disconnect(true);notice('Lost the session connection. Audio stopped. Reconnect to continue.');}}
}
async function control(action){if(!sid)return;try{await api('/api/session/'+sid+'/control',{action});await refresh();}catch(e){notice(e.message);if(action==='stop')await disconnect(true);}}
async function disconnect(tellServer=true){
 const old=sid;sid=null;clearInterval(poll);clearInterval(ping);poll=ping=null;
 if(dc){dc.close();dc=null;}if(pc){const p=pc;pc=null;p.close();}if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
 $('remoteAudio').pause();$('remoteAudio').srcObject=null;try{await wakeLock?.release();}catch{}wakeLock=null;
 $('orb').classList.remove('speaking','listening');$('connect').hidden=false;$('connect').disabled=false;$('liveControls').hidden=true;$('consent').hidden=false;label('NOT CONNECTED');
 $('stateLabel').textContent='MICROPHONE DISCONNECTED';$('enableAudio').hidden=true;muted=false;$('mute').textContent='Mute mic';$('mute').setAttribute('aria-pressed','false');
 // Local audio and microphone are already OFF; do not wait for a remote server.
 if(tellServer&&old){api('/api/session/'+old+'/control',{action:'disconnect'}).catch(()=>{});}
}
$('connect').onclick=start;
$('stop').onclick=async()=>{await disconnect(true);$('prompt').textContent='That time was yours.';$('subtext').textContent='Your microphone is off. Start another conversation whenever you are ready.';};
$('pause').onclick=()=>control('pause');
$('mute').onclick=async()=>{muted=!muted;stream?.getAudioTracks().forEach(t=>t.enabled=!muted);$('mute').textContent=muted?'Unmute mic':'Mute mic';$('mute').setAttribute('aria-pressed',String(muted));if(muted)await control('pause');};
$('enableAudio').onclick=async()=>{try{await $('remoteAudio').play();$('enableAudio').hidden=true;}catch{notice('The browser could not start audio playback. Check output permissions.');}};
$('settings').onclick=()=>{$('backend').value=base;$('settingsDialog').showModal();};
$('saveSettings').onclick=async()=>{try{const u=new URL($('backend').value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)throw Error('Use a plain HTTP(S) server address.');if(pc)await disconnect(true);base=u.href.replace(/\/$/,'');access=$('accessCode').value;try{localStorage.setItem('spare-voice-url',base);}catch{}$('settingsDialog').close();notice('Connection saved. Press Start talking.');}catch(e){$('providerInfo').textContent=e.message;}};
$('privacy').onclick=()=>$('privacyDialog').showModal();
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
document.addEventListener('visibilitychange',()=>{if(document.hidden&&sid)control('pause');});
window.addEventListener('pagehide',()=>{if(stream)stream.getTracks().forEach(t=>t.stop());if(pc)pc.close();});
// Opened as a file: deliberately a visual preview, not a fake working voice session.
if(location.protocol==='file:')notice('Interface preview only. Live voice requires the Python backend and private API keys.');
})();
