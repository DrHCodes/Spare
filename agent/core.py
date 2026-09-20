"""Live workout generation and deterministic per-call workout state.
No speech SDK imports: testable without keys. No fixed workout fallback.
"""
from __future__ import annotations
import json
import math
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable
from settings import settings

LIBRARY = json.loads((Path(__file__).parent / 'library.json').read_text())

class PlanError(ValueError): pass
class ProviderError(RuntimeError): pass


def call_model(messages: list[dict], sender: Callable | None = None) -> dict:
    c = settings()
    if sender is not None:
        return sender(messages)
    if not c['general_key']:
        raise ProviderError('GENERAL_COMPUTE_API_KEY is missing. No request was made.')
    if not c['general_url'].startswith('https://'):
        raise ProviderError('Use an HTTPS model endpoint.')
    payload = {'model': c['general_model'], 'messages': messages,
               'temperature': .4, 'max_tokens': 10000, 'stream': False}
    req = urllib.request.Request(c['general_url'] + '/chat/completions',
        data=json.dumps(payload).encode(), method='POST', headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer '+c['general_key']})
    try:
        with urllib.request.urlopen(req, timeout=65) as r:
            raw = r.read(400001)
            if len(raw) > 400000: raise ProviderError('Response too large.')
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        hints={401:'Check the key.',403:'Check model access.',404:'Confirm the event model ID.',429:'Check rate limits and credits.'}
        raise ProviderError(f'General Compute HTTP {e.code}. '+hints.get(e.code,'Try again later.')) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise ProviderError('The model request failed. No preset workout was substituted.') from None


def block_count(seconds: int) -> int:
    warm = min(180, max(12, seconds // 10))
    return max(2, round((seconds - 2 * warm) / 60))


def clean_text(value, max_words=45):
    if not isinstance(value, str) or not value.strip() or len(value.split()) > max_words:
        raise PlanError('The model returned an instruction of invalid length.')
    if any(x in value.lower() for x in ['keep your feet quiet','keep your feed quiet','push through pain']):
        raise PlanError('The generated wording did not pass the coaching check.')
    return value.strip()


def build_plan(data: dict, seconds: int, effort: float, floor_ok: bool) -> dict:
    if type(seconds) is not int or not 120 <= seconds <= 3600:
        raise PlanError('Choose between 2 and 60 minutes.')
    if isinstance(effort, bool) or not isinstance(effort,(float,int)) or not math.isfinite(effort) or not 1 <= effort <= 8:
        raise PlanError('This prototype supports target effort 1 to 8.')
    blocks = data.get('blocks')
    n = block_count(seconds)
    if not isinstance(blocks, list) or len(blocks) != n:
        raise PlanError(f'Expected {n} blocks. Please ask Spare to try generating again.')
    cleaned=[]
    for b in blocks:
        if not isinstance(b,dict) or b.get('exercise_id') not in LIBRARY:
            raise PlanError('Unknown movement; no workout started.')
        ex=LIBRARY[b['exercise_id']]
        if ex['jumping'] or ex['equipment']!='none' or (ex['position']=='floor' and not floor_ok):
            raise PlanError('The plan violates movement constraints.')
        if effort < ex.get('min_effort',1):
            raise PlanError('The plan contains a variation outside the requested effort range.')
        ratio=b.get('work_fraction')
        if isinstance(ratio,bool) or not isinstance(ratio,(int,float)) or not math.isfinite(ratio) or not .3 <= ratio <= .75:
            raise PlanError('Work/recovery ratio is invalid.')
        if cleaned and cleaned[-1][0]['group']==ex['group'] and ex['group']!='recovery':
            raise PlanError('Repeated muscle group without another group between work blocks.')
        cleaned.append((ex, ratio, clean_text(b.get('instruction')),clean_text(b.get('start_cue'),16)))
    ids=[c[0]['id'] for c in cleaned]
    if ids.count('split_left') != ids.count('split_right'):
        raise PlanError('Split squat sides must be balanced.')
    warm=min(180,max(12,seconds//10)); main=seconds-2*warm
    slot, extra=divmod(main,n)
    plan=[]
    def add(kind, ex, secs, cue):
        plan.append({'kind':kind,'id':ex,'seconds':secs,'cue':cue})
    # Split long bookends so they are not three minutes of a single instruction.
    for kind in ['warmup']:
        remain=warm
        for i in range(math.ceil(warm/30)):
            amount=min(30,remain); remain-=amount
            ex=['step','shoulders','hingesmall','reach'][i%4]
            add(kind,ex,amount,LIBRARY[ex]['cue'])
    for i,(ex,ratio,instruction,start) in enumerate(cleaned):
        size=slot+(i<extra)
        # Budget a human-length instruction rather than an arbitrary ten-second gap.
        setup=min(size-12,max(8,math.ceil(len(instruction.split())/2.3)+2))
        available=size-setup
        upper=.52 if effort<=3 else .65 if effort<=6 else .75
        ratio=max(.3,min(upper,ratio))
        work=max(5,min(available-5,round(available*ratio)))
        add('setup',ex['id'],setup,instruction)
        add('work',ex['id'],work,start)
        rest=available-work
        add('recovery','breathe',rest,f'And rest. You have {rest} seconds.')
    remaining=warm
    for i in range(math.ceil(warm/30)):
        amount=min(30,remaining);remaining-=amount
        ex=['coolstep','shoulders','breathe'][i%3]
        add('cooldown',ex,amount,LIBRARY[ex]['cue'])
    if sum(s['seconds'] for s in plan)!=seconds or min(s['seconds'] for s in plan)<=0:
        raise PlanError('Timing validation failed.')
    return {'title':clean_text(data.get('title','Your Spare session'),16),
            'rationale':clean_text(data.get('rationale','A new session based on your preferences.'),70),
            'total_seconds':seconds,'effort':effort,'floor_ok':floor_ok,'plan':plan,
            'note':'AI-generated draft. Effort is a target preference, not measured exertion.'}


def generate_plan(seconds: int, effort: float, floor_ok=False, notes='', sender=None):
    if type(seconds) is not int or not 120 <= seconds <= 3600:
        raise PlanError('Choose 2 to 60 minutes.')
    n=block_count(seconds)
    catalog=[{'id':k,'name':v['name'],'group':v['group'],'guidance':v['cue']} for k,v in LIBRARY.items()
        if (v['position']=='standing' or floor_ok) and effort>=v.get('min_effort',1)
        and k not in {'breathe','step','coolstep','weightshift'}]
    system='''Design a new equipment-free, no-jumping home workout from the allowed catalog.
Return only JSON: {"title":string,"rationale":string,"blocks":[{"exercise_id":string,"instruction":string,"start_cue":string,"work_fraction":number}]}.
Use exactly the requested number of blocks. Alternate lower, upper, core, or recovery groups.
Do not use adjacent blocks in the same non-recovery group. Balance split_left/split_right counts.
Instruction: 12-40 spoken words, clear setup and motion, ordinary adult language, no fragment labels.
Start cue: 3-12 words, e.g. 'Ready? Start when you are comfortable.' It must not specify an invented duration.
work_fraction 0.30 to 0.75 governs work vs rest AFTER setup. Include recovery even at high effort.
The app supplies setup timing, warmup, cooldown, and exact arithmetic. Do not add those blocks yourself.
Your effort is a subjective target. 'Lagree-like' is a PERSONAL reference, not a universal standard, Pilates equivalence, or equipment replacement.
Fast continuous push-ups mean a desire for high effort, not a literal prescription. No nonstop maximal work.
Avoid 'keep your feet quiet', cutesy language, clinical or weight-loss promises, and invented observations.
Use the catalog's guidance. Respect stated preferences; if impossible return {"error":"brief reason"}.
No markdown.''' 
    query={'seconds':seconds,'effort_target':effort,'floor_allowed':floor_ok,'preferences':str(notes)[:600],
           'required_blocks':n,'catalog':catalog}
    start=time.monotonic()
    result=call_model([{'role':'system','content':system},{'role':'user','content':json.dumps(query)}],sender)
    try:
        content=result['choices'][0]['message']['content'].strip()
        if content.startswith('```'): content=content.split('\n',1)[1].rsplit('```',1)[0]
        data=json.loads(content)
        if not isinstance(data,dict): raise ValueError()
    except (KeyError,IndexError,AttributeError,ValueError,TypeError):
        raise PlanError('Invalid model output; no workout was started.') from None
    if data.get('error'): raise PlanError(str(data['error'])[:200])
    plan=build_plan(data,seconds,effort,floor_ok)
    plan['inference']={'provider':'General Compute','model':result.get('model',settings()['general_model']),
        'seconds':round(time.monotonic()-start,3),'usage':result.get('usage',{}),'test_mock':sender is not None}
    return plan


class Workout:
    """Finish-deadline budget. No automatic resume after speech/interruptions.
    Cue-gated work never starts counting before the corresponding spoken introduction ends.
    """
    def __init__(self, plan):
        self.document=plan;self.plan=[dict(x) for x in plan['plan']]
        self.index=0;self.left=float(self.plan[0]['seconds']);self.budget=float(plan['total_seconds'])
        self.status='ready';self.reason='';self.revision=0;self.movement_seconds=0.;self.cue_done=False
        self.run_generation=0
    def current(self):
        return self.plan[self.index] if self.index<len(self.plan) else None
    def snapshot(self):
        s=self.current()
        return {'status':self.status,'reason':self.reason,'seconds_left':round(self.budget,1),
                'interval_left':round(self.left,1),'effort':self.document['effort'],
                'current_name':LIBRARY[s['id']]['name'] if s else None,
                'current_kind':s['kind'] if s else None, 'index':self.index,
                'movement_timer_seconds':round(self.movement_seconds,1), 'revision':self.revision,
                'measured_repetitions':None,'title':self.document['title']}
    def control(self,action):
        if action=='start' and self.status=='ready': self.status='running';self.run_generation+=1
        elif action=='pause' and self.status=='running': self.status='paused';self.reason='break or conversation';self.run_generation+=1
        elif action=='resume' and self.status=='paused' and self.budget>0:
            self.status='running';self.reason='';self.cue_done=False;self.run_generation+=1
        elif action=='stop': self.status='ended';self.reason='stopped by you';self.run_generation+=1
        elif action=='skip' and self.status in {'running','paused'}:
            # Skip both setup and work when setup is current. Never credit skipped time.
            if self.current()['kind']=='setup': self._advance()
            self._advance();self.status='paused' if self.current() else 'ended'
            self.reason='skipped; say ready to continue';self.run_generation+=1
        elif action not in {'start','pause','resume','stop','skip'}:
            raise PlanError('Unsupported control.')
        self.revision+=1
        return self.snapshot()
    def _advance(self):
        self.index+=1;self.cue_done=False;self.revision+=1
        if self.current():self.left=float(self.current()['seconds'])
        else:self.status='ended';self.reason='session finished';self.left=0
    def cue_finished(self,index):
        if self.index==index and self.status=='running':
            self.cue_done=True
            if self.left<=0:self._advance()
    def set_remaining(self,seconds):
        if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 0<=seconds<=3600:
            raise PlanError('Invalid remaining time.')
        # This can shorten; longer times require a newly designed extension (not repetition).
        if seconds>self.budget:raise PlanError('To extend, pause and request a new remaining plan.')
        self.budget=float(seconds);self.revision+=1
        if not seconds:self.status='ended';self.reason='time finished'
    def tick(self,dt):
        if self.status not in {'running','paused'} or not isinstance(dt,(float,int)) or not math.isfinite(dt) or dt<=0:return
        if dt>3:
            # A blocked server must not claim the user exercised through a time gap.
            self.status='paused';self.reason='timing gap; say ready';self.run_generation+=1
        used=min(dt,self.budget);self.budget=max(0.,self.budget-used)
        if self.status=='running' and self.current():
            s=self.current()
            if self.cue_done or s['kind']!='work':
                spent=min(used,self.left);self.left=max(0.,self.left-spent)
                if s['kind']=='work':self.movement_seconds+=spent
                if self.left<=0 and self.cue_done:self._advance()
        if self.budget<=0:self.status='ended';self.reason='your finish time';self.run_generation+=1
    def easier(self):
        if self.status not in {'running','paused'}:raise PlanError('Start a session first.')
        self.control('pause')
        for s in self.plan[self.index:]:
            ex=LIBRARY[s['id']]; alt=ex.get('easier')
            if s['kind'] in {'setup','work'} and alt and alt in LIBRARY:
                s['id']=alt
                s['cue']=LIBRARY[alt]['cue'] if s['kind']=='setup' else 'Ready? Begin at your own pace.'
        self.document['effort']=max(1,self.document['effort']-1)
        # Re-explain any changed in-progress movement, without crediting setup as work.
        if self.current() and self.current()['kind']=='work':
            original=dict(self.current()); original['seconds']=max(5,math.ceil(self.left))
            self.plan[self.index:self.index+1]=[
                {'kind':'setup','id':original['id'],'seconds':12,'cue':LIBRARY[original['id']]['cue']}, original]
            self.left=12.
        self.cue_done=False;self.reason='easier alternatives; say ready'
        return self.snapshot()
