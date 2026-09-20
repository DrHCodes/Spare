/* Spare v3: browser -> OpenAI WebRTC; Vercel handles private API calls. */
(()=>{'use strict';
const $=id=>document.getElementById(id),text=(id,v)=>{$(id).textContent=v;};
let pc=null,dc=null,mic=null,access='',cfg=null,connecting=false,responding=false,speaking=false,userSpeaking=false,pending=null,muted=false,workout=null,revision=0,designs=0,startedAt=0,last=performance.now(),wake=null;
const fmt=x=>{x=Math.max(0,Math.ceil(x||0));return `${Math.floor(x/60)}:${String(x%60).padStart(2,'0')}`;};
const notice=t=>{text('notice',t);$('notice').hidden=!t;};
function send(e){if(dc?.readyState==='open')dc.send(JSON.stringify(e));}
function context(t){send({type:'conversation.item.create',item:{type:'message',role:'user',content:[{type:'input_text',text:'APP_EVENT (application state, not a new user request): '+t}]}});}
function speak(t){pending=t;flush();}
function flush(){if(!pending||responding||speaking||userSpeaking||dc?.readyState!=='open')return;const t=pending;pending=null;context(t);responding=true;send({type:'response.create',response:{tool_choice:'none',instructions:'Respond briefly to the latest APP_EVENT. Speak only the relevant instruction or question. Do not use tools, count repetitions, or move ahead to another interval.'}});}
async function api(body){const r=await fetch('/api/spare',{method:body?'POST':'GET',headers:{...(body?{'Content-Type':'application/json'}:{}),...(access?{Authorization:'Bearer '+access}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(55000)});let d;try{d=await r.json();}catch{throw Error('The Vercel API is not deployed yet. Wait for the latest deployment to be Ready, then refresh.');}if(!r.ok)throw Error(d.error||`Request failed (${r.status}).`);return d;}
function status(t,on=false){text('connectionStatus',t);$('connectionStatus').classList.toggle('active',on);}
function current(){return workout?.stages[workout.index]||null;}
function remaining(){return workout?(workout.deadline?Math.max(0,(workout.deadline-performance.now())/1000):workout.total_seconds):0;}
function snapshot(){return workout?{status:workout.status,seconds_left:Math.round(remaining()),current:current(),effort:workout.effort,active_seconds:Math.round(workout.active)}:{status:'no_workout'};}
function render(){if(!workout)return;$('sessionInfo').hidden=false;text('timeLeft',fmt(remaining()));text('effortScore',`${workout.effort}/10`);text('currentExercise',workout.status==='ended'?'Finished':current()?.name||'Ready');$('pause').disabled=workout.status!=='running';}
function cancelAudio(){pending=null;if(responding)send({type:'response.cancel'});send({type:'output_audio_buffer.clear'});speaking=false;$('orb').classList.remove('speaking');}
function pause(){if(workout?.status==='running')workout.status='paused';render();}
function cue(){const s=current();if(!s)return;const rule=s.kind==='setup'?'Explain setup. Do not tell them to begin repetitions yet.':s.kind==='work'?'Tell them to start this movement now. Keep it short.':s.kind==='recovery'?'Tell them to rest.':'Guide this gentle '+s.kind+'.';speak(JSON.stringify({state:snapshot(),instruction:rule}));}
function control(action){
 if(!workout)return {ok:false,error:'No workout exists. Generate it first.'};
 if(action==='pause'){pause();}
 else if(action==='stop'){workout.status='ended';revision++;}
 else if(action==='resume'){if(workout.status==='ended'||remaining()<=0)return {ok:false,error:'The session has ended. Generate another only if requested.'};if(document.hidden)return {ok:false,error:'Return to the visible browser tab before resuming.'};if(!workout.deadline)workout.deadline=performance.now()+workout.total_seconds*1000;workout.status='running';}
 else if(action==='skip'){workout.index++;while(current()&&current().kind==='work')workout.index++;if(!current())workout.status='ended';else{workout.left=current().seconds;workout.status='paused';}}
 else return {ok:false,error:'Unknown action.'};render();return {ok:true,...snapshot(),note:action==='resume'?'Coach ONLY this current interval; do not advance ahead of app timers.':'Do not resume until the person explicitly says ready.'};
}
async function tool(item){let result;try{const a=JSON.parse(item.arguments||'{}');if(item.name==='design_workout'){
 if(++designs>8)throw Error('Demo generation limit reached. End the session before starting another.');
 pause();text('stateLabel','DESIGNING YOUR WORKOUT');const rev=revision,old=workout;
 if(old?.deadline&&remaining()<120)throw Error('Less than two minutes remain. Use the current plan at an easier pace, rest, or end rather than generating a new full workout.');
 if(old?.deadline)a.minutes=Math.min(Number(a.minutes),remaining()/60);
 const p=await api({action:'design',...a});if(rev!==revision||!pc)throw Error('Plan discarded because you interrupted or ended the session. Confirm the latest request before trying again.');
 workout={...p,index:0,left:p.stages[0].seconds,status:'ready',deadline:old?.deadline||0,active:old?.active||0};
 text('understood',`${p.minutes.toFixed(1)} minutes · target ${p.effort}/10 · ${p.title}`);text('technical',`Live speech: ${cfg.model}\nWorkout generation: ${p.provider} / ${p.model}\n${JSON.stringify(p.usage||{})}\nMovement timing is not verified repetitions.`);render();
 result={ok:true,title:p.title,summary:p.summary,provider:p.provider,total_seconds:p.total_seconds,...snapshot(),instruction:'Briefly summarize, then ask if ready. Movement has not started.'};
 }else if(item.name==='control_workout')result=control(a.action);else throw Error('Unknown tool.');
 }catch(e){result={ok:false,error:e.message};notice(e.message);}
 send({type:'conversation.item.create',item:{type:'function_call_output',call_id:item.call_id,output:JSON.stringify(result)}});
 return result;
}
let handled=new Set();
async function event(e){
 if(e.type==='session.created'){status('CONNECTED · LISTENING',true);speak('Introduce yourself as Spare, an AI coach, and ask only: How much time do you have?');}
 if(e.type==='response.created')responding=true;
 if(e.type==='input_audio_buffer.speech_started'){userSpeaking=true;revision++;pending=null;pause();$('orb').classList.add('listening');text('stateLabel','LISTENING · MOVEMENT PAUSED');if(workout)context('The user started speaking, so movement is now paused. '+JSON.stringify(snapshot()));}
 if(e.type==='input_audio_buffer.speech_stopped'){userSpeaking=false;$('orb').classList.remove('listening');}
 if(e.type==='output_audio_buffer.started'){speaking=true;$('orb').classList.add('speaking');text('stateLabel','SPARE IS SPEAKING');}
 if(e.type==='output_audio_buffer.stopped'||e.type==='output_audio_buffer.cleared'){speaking=false;$('orb').classList.remove('speaking');text('stateLabel',workout?.status==='paused'?'PAUSED · SAY READY':'LISTENING');flush();}
 if(e.type==='response.output_audio_transcript.done'||e.type==='response.audio_transcript.done')text('prompt',e.transcript||'');
 if(e.type==='conversation.item.input_audio_transcription.completed'){
 const t=e.transcript||'';text('understood','You: '+t);
 if(/\b(?:pain|hurts|dizzy|dizziness)\b/i.test(t)&&workout){control('stop');context('Safety stop has been applied. Do not resume this workout.');}
 }
 if(e.type==='response.done'){
 responding=false;const calls=(e.response?.output||[]).filter(x=>x.type==='function_call'&&!handled.has(x.call_id));
 if(calls.length){for(const x of calls){handled.add(x.call_id);await tool(x);}if(!userSpeaking&&dc?.readyState==='open'){responding=true;send({type:'response.create'});}}
 else flush();
 }
 if(e.type==='error'){
 const code=e.error?.code||'';
 if(/cancel_not_active|response_cancel|output_audio_buffer_clear/.test(code))return;
 if(/active_response/.test(code)){responding=true;return;}
 notice(e.error?.message||'Voice service error.');pause();responding=false;
 }
}
async function start(){
 if(pc||connecting)return;connecting=true;startedAt=0;$('connect').disabled=true;notice('');status('CONNECTING');
 try{
 cfg=await api();text('providerInfo',`Voice: ${cfg.model} · Design: ${cfg.designer}`);
 if(cfg.missing.length)throw Error('In Vercel > Settings > Environment Variables add '+cfg.missing.join(', ')+', then redeploy.');
 if(!access){$('settingsDialog').showModal();throw Error('Enter your private Spare demo password in Connection. Never enter an API key here.');}
 if(!window.isSecureContext)throw Error('Open your HTTPS Vercel website for microphone access.');
 mic=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
 pc=new RTCPeerConnection();const own=pc;mic.getTracks().forEach(t=>pc.addTrack(t,mic));
 pc.ontrack=e=>{$('remoteAudio').srcObject=e.streams[0]||new MediaStream([e.track]);$('remoteAudio').play().catch(()=>$('enableAudio').hidden=false);};
 dc=pc.createDataChannel('oai-events');dc.onmessage=e=>{try{event(JSON.parse(e.data)).catch(err=>notice(err.message));}catch{}};
 pc.onconnectionstatechange=()=>{if(pc!==own)return;if(pc.connectionState==='connected')status('CONNECTED · LISTENING',true);if(['failed','disconnected'].includes(pc.connectionState)){stop();notice('Audio disconnected. Exercise stopped. Reconnect when ready.');}};
 await pc.setLocalDescription(await pc.createOffer());const answer=await api({action:'connect',sdp:pc.localDescription.sdp});if(own!==pc)return;
 await pc.setRemoteDescription({type:'answer',sdp:answer.sdp});
 startedAt=performance.now();designs=0;handled.clear();workout=null;$('sessionInfo').hidden=true;$('connect').hidden=true;$('liveControls').hidden=false;$('consent').hidden=true;
 text('subtext','Talk naturally. Interrupt with “I need a break.” Keep this page open.');text('technical',`Vercel-only v3\nVoice: ${cfg.model}\nWorkout designer: ${cfg.designer}\nNo local server. No browser speech synthesis.`);
 if(cfg.designer.startsWith('OpenAI'))notice('OpenAI-only mode. General Compute is not configured, so sponsor compute is not being used.');
 try{wake=await navigator.wakeLock?.request('screen');}catch{}
 }catch(e){stop();notice(e.name==='NotAllowedError'?'Allow microphone access in your browser to start.':e.message);}
 finally{connecting=false;$('connect').disabled=false;}
}
function stop(){revision++;if(workout)workout.status='ended';pending=null;try{cancelAudio();}catch{}if(dc){dc.close();dc=null;}const old=pc;pc=null;old?.close();mic?.getTracks().forEach(t=>t.stop());mic=null;$('remoteAudio').pause();$('remoteAudio').srcObject=null;wake?.release().catch(()=>{});wake=null;responding=speaking=userSpeaking=false;$('orb').classList.remove('speaking','listening');$('connect').hidden=false;$('connect').disabled=false;$('liveControls').hidden=true;$('consent').hidden=false;status('NOT CONNECTED');text('stateLabel','MICROPHONE DISCONNECTED');muted=false;$('mute').textContent='Mute mic';$('mute').setAttribute('aria-pressed','false');render();}
setInterval(()=>{
 const now=performance.now(),dt=(now-last)/1000;last=now;if(!pc)return;
 if(startedAt&&now-startedAt>(cfg?.connection_minutes||15)*60000){stop();notice('Demo connection limit reached. Your microphone is off.');return;}
 if(!workout||workout.status==='ended')return;
 if(workout.deadline&&remaining()<=0){workout.status='ended';cancelAudio();speak('The time budget is over and all exercise timers have stopped. Tell them the workout is finished; then suggest pressing End session to disconnect.');render();return;}
 if(workout.status==='running'){
  if(current()?.kind==='work')workout.active+=Math.min(dt,Math.max(0,workout.left));
  workout.left=Math.max(0,workout.left-dt);
  if(workout.left<=0&&!speaking&&!responding&&!userSpeaking){workout.index++;if(!current()){workout.status='ended';speak('The workout is finished. Tell them to rest, and press End session to disconnect.');}else{workout.left=current().seconds;cue();}}
 }render();
},200);
$('connect').onclick=start;$('stop').onclick=()=>{stop();text('prompt','That time was yours.');text('subtext','Your microphone is off.');};
$('pause').onclick=()=>{pause();cancelAudio();context('Pause button pressed. Movement is paused. Wait for explicit readiness.');speak('Movement is paused. Ask the user to say ready whenever they want to continue.');};
$('mute').onclick=()=>{muted=!muted;mic?.getAudioTracks().forEach(t=>t.enabled=!muted);$('mute').textContent=muted?'Unmute mic':'Mute mic';$('mute').setAttribute('aria-pressed',String(muted));if(muted){pause();cancelAudio();context('Microphone muted and movement paused. Do not resume until unmuted and explicitly ready.');}};
$('settings').onclick=()=>$('settingsDialog').showModal();$('saveSettings').onclick=()=>{access=$('accessCode').value.trim();$('accessCode').value='';$('settingsDialog').close();notice('Demo password saved for this page only. Press Start talking.');};
$('privacy').onclick=()=>$('privacyDialog').showModal();document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
$('enableAudio').onclick=()=>$('remoteAudio').play().then(()=>$('enableAudio').hidden=true).catch(()=>notice('Check browser audio permissions.'));
document.addEventListener('visibilitychange',()=>{if(document.hidden&&pc){pause();cancelAudio();context('Tab hidden. Exercise paused. Require explicit readiness after they return.');}});
window.addEventListener('pagehide',stop);
})();
