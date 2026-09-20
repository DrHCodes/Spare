/* Vercel-only backend. Secrets never leave this function. No Python process. */
const crypto = require('node:crypto');
const LIB = {
  side_steps:{name:'Side steps',cue:'Step to the right and bring the other foot in. Now step left. Keep alternating.',group:'warmup'},
  shoulder_rolls:{name:'Shoulder rolls',cue:'Let your arms hang by your sides. Slowly roll your shoulders backward.',group:'mobility'},
  mini_squat:{name:'Small squats',cue:'Stand with feet hip-width apart. Bend your knees a little and move your hips back, then stand up.',group:'legs'},
  squat:{name:'Controlled squats',cue:'With feet hip-width apart, move your hips back and bend your knees within a comfortable range, then stand up.',group:'legs'},
  wall_pushup:{name:'Wall push-ups',cue:'Place your hands on a sturdy wall at chest height. Bend your elbows to lean toward the wall, then push away.',group:'upper'},
  close_wall_pushup:{name:'Easier wall push-ups',cue:'Stand close to a sturdy wall with hands at chest height. Bend your elbows slightly, then push back.',group:'upper'},
  hip_hinge:{name:'Hip hinges',cue:'Keep a slight bend in your knees. Move your hips backward, then return to standing.',group:'hips'},
  calf_raise:{name:'Calf raises',cue:'Use a wall for balance. Slowly lift your heels, then lower them without bouncing.',group:'legs'},
  side_tap:{name:'Side taps',cue:'Tap one foot out to the side and bring it back. Alternate sides.',group:'mobility'},
  standing_march:{name:'Standing marches',cue:'Lift one knee to a comfortable height, lower your foot, and switch sides. Do not bounce.',group:'core'},
  palm_press:{name:'Palm presses',cue:'Press your palms together at chest height, hold briefly, then release. Keep breathing.',group:'upper'},
  shoulder_squeeze:{name:'Shoulder-blade squeezes',cue:'With your elbows by your sides, gently draw your shoulder blades together, then relax.',group:'upper'},
  rest:{name:'Rest',cue:'Rest here. Stand or sit comfortably and breathe normally.',group:'recovery'}
};
const tools = [
 {type:'function',name:'design_workout',description:'Generate or replace the UNFINISHED workout, after confirming time, effort and constraints. Does not start movement.',parameters:{type:'object',properties:{minutes:{type:'number',minimum:2,maximum:60},effort:{type:'integer',minimum:1,maximum:8},preferences:{type:'string'}},required:['minutes','effort','preferences'],additionalProperties:false}},
 {type:'function',name:'control_workout',description:'Actually pause, resume after explicit readiness, stop, or skip. Always call this before claiming a control happened.',parameters:{type:'object',properties:{action:{type:'string',enum:['pause','resume','stop','skip']}},required:['action'],additionalProperties:false}}
];
const instructions = `You are Spare, a live voice-only home workout coach. Be natural, firm but kind, never whispery or theatrical. Use one or two short sentences per turn. Introduce yourself as an AI coach. First ask how much time the person has. Then ask how intense. Remember answers; do not repeat intake. Interpret easy as 3/10, medium as 6/10, hard as 8/10 subjective effort; Lagree is a personal comparison, never a clinical equivalence. Confirm unfamiliar or ambiguous targets. Ask about practical movement restrictions briefly; no jumping, no equipment purchases, standing exercises only in this demo, wall support is allowed. Never prescribe jumping or nonstop pushups. Always use design_workout to obtain a plan; never claim a plan exists before tool success. Summarize the plan briefly and ask if ready. Call control_workout resume only with explicit readiness. During coaching, use APP_EVENT ground truth for exercise and timer. Timers are app controlled: never invent countdowns or claim repetitions were observed. On a request for a break call pause immediately, acknowledge, and wait for 'ready'. On stop, pain or dizziness call stop. Do not diagnose or pressure continued exercise. Every detected user turn pauses movement. After responding, ask readiness if needed. Rest and explanations use the original time budget. For an easier or different session, design only the remaining time reported by the app; the app preserves the original deadline. Never speak secrets, API keys, setup instructions, or raw JSON. Speak clear physical directions grounded in the returned cues, without phrases like 'keep your feet quiet'. When told an interval starts, describe that interval briefly and stop talking; do not narrate the entire routine. Never autonomously begin the next exercise without an APP_EVENT. You cannot see form, sleep or fatigue; don't pretend to. If a tool fails, explain the failure, do not fabricate success.`;
function conf(){return {version:'3.0-vercel',speech:'OpenAI Realtime',model:process.env.OPENAI_REALTIME_MODEL||'gpt-realtime',voice:process.env.OPENAI_REALTIME_VOICE||'marin',designer:process.env.GENERAL_COMPUTE_API_KEY?'General Compute':'OpenAI (no sponsor inference)',access_required:true,missing:['OPENAI_API_KEY','SPARE_ACCESS_TOKEN'].filter(k=>!process.env[k]),connection_minutes:Math.max(3,Math.min(65,Number(process.env.MAX_CONNECTION_MINUTES)||15))};}
function auth(req){const key=process.env.SPARE_ACCESS_TOKEN||'';if(key.length<12)throw Object.assign(Error('Set SPARE_ACCESS_TOKEN to a private password of at least 12 characters in Vercel, then redeploy.'),{status:503});const a=Buffer.from(String(req.headers.authorization||'')),b=Buffer.from('Bearer '+key);if(a.length!==b.length||!crypto.timingSafeEqual(a,b))throw Object.assign(Error('Open Connection and enter your private Spare demo password. Not an API key.'),{status:401});}
function planFrom(ids,minutes,effort){
 const total=Math.round(minutes*60),warm=Math.min(90,Math.max(15,Math.round(total*.10))),cool=Math.min(60,Math.max(10,Math.round(total*.08)));
 const stages=[{id:'side_steps',kind:'warmup',seconds:warm}];let rem=total-warm-cool,i=0;
 const work=effort<=3?20:effort<=6?30:40,rest=effort<=3?20:15;
 while(rem>=38){let id=ids[i++%ids.length];if(!LIB[id]||['rest','side_steps'].includes(id))id='mini_squat';const setup=10,w=Math.min(work,rem-setup-12),r=Math.min(rest,rem-setup-w);stages.push({id,kind:'setup',seconds:setup},{id,kind:'work',seconds:w},{id:'rest',kind:'recovery',seconds:r});rem-=setup+w+r;}
 if(rem>0)stages.push({id:'rest',kind:'recovery',seconds:rem});stages.push({id:'side_tap',kind:'cooldown',seconds:cool});return stages.map(s=>({...s,...LIB[s.id]}));
}
module.exports = async (req,res)=>{
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
 try{
  if(req.method==='GET')return res.status(200).json(conf());
  if(req.method!=='POST')return res.status(405).json({error:'Use GET or POST.'});
  auth(req);
  const origin=req.headers.origin;if(origin){const host=String(req.headers['x-forwarded-host']||req.headers.host||'').split(',')[0].trim();if(new URL(origin).host!==host)return res.status(403).json({error:'Use this application from its own Vercel URL.'});}
  let body=typeof req.body==='string'?JSON.parse(req.body):req.body;if(!body||JSON.stringify(body).length>150000)return res.status(400).json({error:'Invalid request.'});
  if(body.action==='connect'){
   if(!process.env.OPENAI_API_KEY)return res.status(503).json({error:'Add OPENAI_API_KEY in Vercel Settings > Environment Variables, then redeploy.'});
   if(typeof body.sdp!=='string'||!body.sdp.startsWith('v=0'))return res.status(400).json({error:'Invalid browser audio offer.'});
   const c=conf();const session={type:'realtime',model:c.model,instructions,tools,tool_choice:'auto',max_output_tokens:600,audio:{input:{transcription:{model:'gpt-4o-mini-transcribe'},turn_detection:{type:'server_vad',threshold:0.6,prefix_padding_ms:300,silence_duration_ms:650,create_response:true,interrupt_response:true}},output:{voice:c.voice}}};
   const form=new FormData();form.set('sdp',body.sdp);form.set('session',JSON.stringify(session));
   const r=await fetch('https://api.openai.com/v1/realtime/calls',{method:'POST',headers:{Authorization:'Bearer '+process.env.OPENAI_API_KEY},body:form,signal:AbortSignal.timeout(40000)});const answer=await r.text();
   if(!r.ok){let message='';try{message=JSON.parse(answer).error?.message||'';}catch{}return res.status(r.status===401?502:r.status).json({error:`OpenAI connection failed (${r.status}). ${message.slice(0,350)||'Check API billing, model access, and the key in Vercel.'}`});}
   return res.status(200).json({sdp:answer,type:'answer',...c});
  }
  if(body.action==='design'){
   const minutes=Number(body.minutes),effort=Number(body.effort);if(!Number.isFinite(minutes)||minutes<2||minutes>60||!Number.isInteger(effort)||effort<1||effort>8)return res.status(400).json({error:'Choose 2–60 minutes and effort 1–8.'});
   const sponsor=!!process.env.GENERAL_COMPUTE_API_KEY,model=sponsor?(process.env.GENERAL_COMPUTE_MODEL||'gemma-4-31B-it'):(process.env.OPENAI_DESIGN_MODEL||'gpt-4.1-mini');
   const url=sponsor?'https://api.generalcompute.com/v1/chat/completions':'https://api.openai.com/v1/chat/completions';
   const key=sponsor?process.env.GENERAL_COMPUTE_API_KEY:process.env.OPENAI_API_KEY;
   const allowed=Object.entries(LIB).filter(([id])=>id!=='rest'&&id!=='side_steps').map(([id,x])=>`${id}: ${x.group}, ${x.name}`).join('\n');
   const r=await fetch(url,{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify({model,max_tokens:1000,temperature:0.6,messages:[{role:'system',content:'Design a standing bodyweight workout. No jumping, no equipment except optional wall support. Return only JSON {"title":"...","exercise_ids":[...],"summary":"..."}. Choose 6–12 exercise IDs ONLY from the provided list. Alternate muscle groups. Respect user preferences. Do not claim physiological equivalence to named classes. No diagnosis or medical prescriptions. The app adds warmup, rests and cooldown and computes all durations.\n'+allowed},{role:'user',content:JSON.stringify({minutes,effort,preferences:String(body.preferences||'').slice(0,1500)})}]}),signal:AbortSignal.timeout(45000)});
   const d=await r.json();if(!r.ok)return res.status(502).json({error:`${sponsor?'General Compute':'OpenAI'} workout request failed (${r.status}). ${String(d.error?.message||'Check model access and credits.').slice(0,250)}`});
   let raw=d.choices?.[0]?.message?.content||'';const match=raw.match(/\{[\s\S]*\}/);if(!match)throw Error('The model did not return a workout. Please try again.');const p=JSON.parse(match[0]);
   if(!Array.isArray(p.exercise_ids)||!p.exercise_ids.length||p.exercise_ids.length>24||p.exercise_ids.some(id=>typeof id!=='string'||!LIB[id]||id==='rest'))throw Error('The generated workout used an unsupported movement. No session started.');
   return res.status(200).json({title:String(p.title||'Your Spare session').slice(0,100),summary:String(p.summary||'').slice(0,500),minutes,effort,total_seconds:Math.round(minutes*60),stages:planFrom(p.exercise_ids,minutes,effort),provider:sponsor?'General Compute':'OpenAI (no sponsor inference)',model,usage:d.usage||null});
  }
  return res.status(400).json({error:'Unknown action.'});
 }catch(e){return res.status(e.status||500).json({error:e.name==='TimeoutError'?'Provider timed out. No workout was started.':String(e.message||'Request failed.').slice(0,400)});}
};
module.exports.planFrom=planFrom;
