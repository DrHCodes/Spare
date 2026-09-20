"""Conversation/tool state isolated per peer. All durable effects pass through here."""
from __future__ import annotations
import asyncio
from dataclasses import replace
import re
import time
from core import Workout, PlanError, generate_plan, LIBRARY
from effort import interpret_effort


def explicit_yes(text):
    t=text.lower().strip()
    if re.search(r"\b(no|not|don't|dont|wait|hold|later)\b", t): return False
    return bool(re.search(r"\b(yes|yeah|yep|okay|ok|ready|start|sure|correct|sounds good|let.s do it|go ahead)\b",t))


class Controller:
    def __init__(self, max_designs=8):
        self.minutes=None;self.effort=None;self.floor_ok=False;self.notes=''
        self.workout=None;self.stage='time';self.confirmed=False;self.generation=0
        self.designs=0;self.max_designs=max_designs;self.last_user=''
        self.last_user_at=0.;self.caption='How much time do you have?'
        self.connected=False;self.error=None;self.bot_speaking=False;self.user_speaking=False
        self.generating=False;self.inference=None;self.events=[];self.created=time.monotonic()
    def event(self,name):
        self.events.append({'event':name,'elapsed':round(time.monotonic()-self.created,2)})
        self.events=self.events[-30:]
    def voice_started(self):
        self.user_speaking=True
        if self.generating:self.generation+=1
        if self.workout and self.workout.status=='running':
            self.workout.control('pause');self.event('movement_paused_for_interruption')
    def transcript(self,text):
        self.last_user=text[:1200];self.last_user_at=time.monotonic();t=text.lower().strip().rstrip('.!?')
        if not self.workout:return
        # A narrow fast path. Qualified/negated language remains for the LLM to resolve.
        if t in {'stop','stop workout','stop the workout',"i'm done",'i am done','end the workout'}:
            self.workout.control('stop');self.generation+=1;self.event('stop')
        elif t in {'pause','pause workout','i need a break','give me a break','wait','hold on'}:
            self.workout.control('pause');self.event('break')
        elif re.search(r'\b(chest pain|i feel dizzy|i am dizzy|this hurts|i.m in pain)\b',t):
            self.workout.control('stop');self.generation+=1;self.event('symptom_stop')
    def public(self):
        return {'stage':self.stage,'minutes':self.minutes,'effort':self.effort.public() if self.effort else None,
                'floor_ok':self.floor_ok,'connected':self.connected,'caption':self.caption,
                'error':self.error,'bot_speaking':self.bot_speaking,'user_speaking':self.user_speaking,
                'generating':self.generating,'workout':self.workout.snapshot() if self.workout else None,
                'inference':self.inference,'design_requests':self.designs,'events':self.events[-8:]}
    def set_time(self,minutes):
        if isinstance(minutes,bool) or not isinstance(minutes,(int,float)) or not 2<=minutes<=60:
            raise PlanError('Ask for a duration between 2 and 60 minutes.')
        if self.workout and self.workout.status in {'running','paused'}:
            self.workout.set_remaining(round(minutes*60));return self.workout.snapshot()
        self.minutes=float(minutes);self.confirmed=False;self.generation+=1
        self.stage='effort' if self.effort is None else 'confirm'
        return {'minutes':self.minutes,'next':'Ask how intense they want it, in their own words.'}
    def set_effort(self,description,score=None,confidence=.5,floor_ok=None,notes=''):
        if self.workout and self.workout.status in {'running','paused'}:
            raise PlanError('Use revise_remaining for effort changes during a session.')
        self.effort=interpret_effort(description,score,confidence)
        if floor_ok is not None:
            if type(floor_ok) is not bool:raise PlanError('Floor permission must be true or false.')
            self.floor_ok=floor_ok
        self.notes=str(notes)[:600];self.confirmed=False;self.generation+=1;self.stage='confirm'
        return {**self.effort.public(),'next':'Confirm the interpreted target with the user before generating.',
                'limits':'No jumping or equipment. High effort includes recovery, never nonstop fast push-ups.'}
    def require_yes(self):
        if time.monotonic()-self.last_user_at>30 or not explicit_yes(self.last_user):
            raise PlanError('Ask for an explicit recent confirmation first.')
    async def design(self,sender=None):
        self.require_yes()
        if self.minutes is None or self.effort is None:raise PlanError('Need time and effort first.')
        if self.generating:raise PlanError('A design request is already running.')
        if self.workout and self.workout.status in {'running','paused'}:raise PlanError('Use revise_remaining instead.')
        if self.designs>=self.max_designs:raise PlanError('Design request limit reached for this call.')
        self.designs+=1;self.generating=True;stamp=self.generation;self.stage='designing'
        try:
            result=await asyncio.to_thread(generate_plan,round(self.minutes*60),self.effort.score,self.floor_ok,self.notes,sender)
            if stamp!=self.generation:
                self.stage='confirm';raise PlanError('Request changed while generating. Discarded old plan.')
            self.workout=Workout(result);self.inference=result['inference'];self.confirmed=True;self.effort=replace(self.effort,needs_confirmation=False);self.stage='ready'
            self.event('generated_new_workout')
            return {'title':result['title'],'rationale':result['rationale'], 'effort':result['effort'],
                    'minutes':self.minutes,'status':'ready','next':'Briefly summarize and ask Ready? Do not start until yes.',
                    'deadline':'The original finish time continues during breaks. Say stop at any time.'}
        finally:
            self.generating=False
            if self.stage=='designing':self.stage='confirm'
    def control(self,action):
        if not self.workout:raise PlanError('No workout exists yet.')
        if action in {'start','resume'}:self.require_yes()
        if action=='easier':result=self.workout.easier()
        else:result=self.workout.control(action)
        if action=='stop':self.generation+=1
        self.stage='session' if self.workout.status!='ended' else 'finished'
        self.event(action);return result
    async def revise(self,description,score,notes='',sender=None):
        if not self.workout or self.workout.status not in {'running','paused'}:raise PlanError('No active session.')
        self.workout.control('pause')
        if self.workout.budget<120:raise PlanError('Less than two minutes remain. Offer an easier alternative, rest, or finish instead.')
        if self.generating:raise PlanError('Another design is running.')
        if self.designs>=self.max_designs:raise PlanError('Design request limit reached.')
        effort=interpret_effort(description,score,.7,True)
        self.designs+=1;self.generating=True;stamp=self.generation;old=self.workout
        try:
            result=await asyncio.to_thread(generate_plan,int(old.budget),effort.score,self.floor_ok,
                self.notes+' Remaining session revision: '+notes,sender)
            if self.generation!=stamp or old.status=='ended':raise PlanError('Cancelled old revision.')
            result['total_seconds']=int(old.budget)
            new=Workout(result);new.status='paused';new.budget=old.budget;new.movement_seconds=old.movement_seconds
            self.workout=new;self.effort=effort;self.inference=result['inference'];self.event('remaining_plan_revised')
            return {'status':'paused','next':'Describe the change and ask Ready?', 'remaining_seconds':new.budget,
                    'effort':effort.public(),'rationale':result['rationale']}
        finally:self.generating=False
