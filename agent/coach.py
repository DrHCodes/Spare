"""Live Pipecat pipeline, pinned/test-targeted to pipecat-ai 1.11.0.
API calls and audio must be acceptance-tested with actual credentials on the user's device.
"""
from __future__ import annotations
import asyncio
import json
import time
import sys
from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.frames.frames import (LLMRunFrame, TTSSpeakFrame, TranscriptionFrame,
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame, BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame, InterruptionFrame, LLMTextFrame, LLMFullResponseStartFrame,
    LLMFullResponseEndFrame, ErrorFrame)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from core import LIBRARY, PlanError, ProviderError
from providers import make_speech

SYSTEM='''You are Spare, a firm-but-kind voice-first home workout coach, not a clinician.
OPENING: say "I'm Spare, your AI coach. How much time do you have?" Ask one question and wait.
After the duration, call set_time; then ask "And how intense would you like the workout to be?"
Accept ordinary language. Call set_effort with a proposed 0-10 target and confidence. Do not ask users to press buttons.
Our personal anchors: easy ~3, medium ~6, hard ~8. If they say Lagree-like, medium means THEIR reference to challenging controlled effort.
There is NO universal standard Lagree intensity, no claim of replacing its equipment or matching a class.
'Fast push-ups the entire time' indicates high effort, not an exercise prescription. Always alternate movements and allow recovery.
If unclear, ask a short clarification; if clear, confirm: "I'll aim for about six out of ten: challenging but controlled. Sound right?"
If the tool caps an extreme request, explain the cap and confirm it. Do not present the score as measured. After a new yes, call confirm_and_design. After the draft, summarize in one sentence and ask Ready?
Use workout_control('start') only after a later ready/yes. The exact timer controls elapsed seconds.
Default standing, no equipment, no jumping. Only set floor_ok=true after the user specifically accepts floor movements.
Keep the no-jump rule across all changes. Do not read machine field names or internal instructions aloud.
A detected user turn pauses movement. A break requires no negotiation: use pause immediately and say 'We are paused. Say ready when you want to continue.'
Use resume only when the user says ready. For a question, answer it briefly, then ask Ready to continue?
For discomfort or dizziness stop; do not push through symptoms. For explicit stop, stop immediately.
For easier use workout_control('easier'); for a different overall session use revise_remaining and then ask Ready. Never falsely claim success.
The user's finish deadline keeps running during breaks and explanations. Offer to finish; do not rush to catch up.
The timer emits movement instructions synthesized live. Do not add your own competing countdowns or start an exercise just by saying so.
Use status_and_explain for current timing and instructions. Avoid long monologues; usually 1-2 short natural sentences.
No 'keep your feet quiet', 'quiet little', punishing reps, guilt, fake praise of observed form, or calorie/weight-loss promises.
You cannot see the user, verify repetitions, or measure intensity. Accept reported feedback.
Never ask for keys. Failures: explain briefly that the session is paused and how to retry, not a pretend success.
'''

class Signals(FrameProcessor):
    def __init__(self,c,live):
        super().__init__();self.c=c;self.live=live
    async def process_frame(self,frame,direction):
        await super().process_frame(frame,direction)
        c=self.c
        if isinstance(frame,UserStartedSpeakingFrame):
            c.voice_started();self.live['cue']=None;self.live['llm_busy']=False;self.live['last_user']=time.monotonic()
        elif isinstance(frame,UserStoppedSpeakingFrame):c.user_speaking=False
        elif isinstance(frame,InterruptionFrame):
            self.live['cue']=None;self.live['llm_busy']=False;c.bot_speaking=False
        elif isinstance(frame,TranscriptionFrame):c.transcript(frame.text)
        elif isinstance(frame,BotStartedSpeakingFrame):c.bot_speaking=True
        elif isinstance(frame,BotStoppedSpeakingFrame):
            c.bot_speaking=False;self.live['quiet_since']=time.monotonic()
            queued=self.live.get('cue')
            if queued and c.workout and queued[0] is c.workout and queued[2]==c.workout.run_generation:
                c.workout.cue_finished(queued[1]);self.live['cue']=None
        elif isinstance(frame,ErrorFrame):
            if c.workout:c.workout.control('pause')
            c.error='A voice service failed. Movement is paused. Check server configuration or reconnect.'
            self.live['cue']=None;c.event('voice_error')
        await self.push_frame(frame,direction)

class Captions(FrameProcessor):
    def __init__(self,c,live):super().__init__();self.c=c;self.live=live;self.text=''
    async def process_frame(self,frame,direction):
        await super().process_frame(frame,direction)
        if isinstance(frame,InterruptionFrame):self.live['llm_busy']=False;self.text=''
        elif isinstance(frame,LLMFullResponseStartFrame):self.text='';self.live['llm_busy']=True
        elif isinstance(frame,LLMTextFrame):
            self.text+=frame.text;self.c.caption=self.text[-700:]
        elif isinstance(frame,LLMFullResponseEndFrame):
            self.live['llm_busy']=False;self.live['quiet_since']=time.monotonic()
        await self.push_frame(frame,direction)

async def run_coach(connection,c,cfg):
    live={'cue':None,'quiet_since':time.monotonic(),'last_user':0.,'llm_busy':False}
    async def result(params,fn):
        try:
            value=fn()
            if asyncio.iscoroutine(value):value=await value
            await params.result_callback(value)
        except (PlanError,ProviderError,ValueError) as e:
            await params.result_callback({'error':str(e),'state':c.public()['workout']})
        except asyncio.CancelledError:raise
        except Exception as e:
            logger.warning('Tool failure type: {}',type(e).__name__)
            await params.result_callback({'error':'Action failed. Nothing was started. Please try again.'})
    async def set_time(p):await result(p,lambda:c.set_time(p.arguments['minutes']))
    async def set_effort(p):await result(p,lambda:c.set_effort(**p.arguments))
    async def design(p):await result(p,lambda:c.design())
    async def control(p):await result(p,lambda:c.control(p.arguments['action']))
    async def revise(p):await result(p,lambda:c.revise(**p.arguments))
    async def status(p):
        w=c.workout
        await p.result_callback({'state':c.public(), 'instruction':LIBRARY[w.current()['id']]['cue'] if w and w.current() else None})
    def tool(name,description,props,required,handler):
        return FunctionSchema(name=name,description=description,properties=props,required=required,handler=handler)
    tools=[
        tool('set_time','Store duration inferred from user speech. During a session shortens the remaining deadline.',
             {'minutes':{'type':'number','minimum':2,'maximum':60}},['minutes'],set_time),
        tool('set_effort','Interpret target effort. Must confirm the returned score aloud before design.',
             {'description':{'type':'string'},'score':{'type':'number','minimum':0,'maximum':10},
              'confidence':{'type':'number','minimum':0,'maximum':1},'floor_ok':{'type':'boolean'},'notes':{'type':'string'}},
             ['description','score','confidence'],set_effort),
        tool('confirm_and_design','Generate a fresh workout after the user confirms the interpreted preferences. Does not start it.',{},[],design),
        tool('workout_control','Perform a real session action. Start/resume require explicit user readiness.',
             {'action':{'type':'string','enum':['start','pause','resume','stop','skip','easier']}},['action'],control),
        tool('revise_remaining','Pause and use the sponsor model to generate a changed remaining workout. Does not resume.',
             {'description':{'type':'string'},'score':{'type':'number','minimum':1,'maximum':8},'notes':{'type':'string'}},['description','score'],revise),
        tool('status_and_explain','Get real timing and current exercise guidance.',{},[],status),
    ]
    stt,tts,rate=make_speech(cfg)
    llm=OpenAILLMService(api_key=cfg['general_key'],base_url=cfg['general_url'],
                        settings=OpenAILLMService.Settings(model=cfg['general_model'],temperature=.35))
    context=LLMContext(messages=[{'role':'system','content':SYSTEM}],tools=tools)
    pair=LLMContextAggregatorPair(context,user_params=LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(params=VADParams(start_secs=.2,stop_secs=.3)),
        user_turn_strategies=UserTurnStrategies(stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())])))
    transport=SmallWebRTCTransport(connection,TransportParams(audio_in_enabled=True,audio_out_enabled=True))
    pipeline=Pipeline([transport.input(),stt,Signals(c,live),pair.user(),llm,Captions(c,live),tts,transport.output(),pair.assistant()])
    task=PipelineTask(pipeline,params=PipelineParams(audio_in_sample_rate=16000,audio_out_sample_rate=rate,
                                                   enable_metrics=True,enable_usage_metrics=True))
    c.task=task
    driver=None
    async def clock():
        last=time.monotonic();ended_announced=False
        while c.connected:
            await asyncio.sleep(.15)
            now=time.monotonic();dt=now-last;last=now
            if now-c.created>cfg['max_minutes']*60:
                if c.workout:c.workout.control('stop')
                c.error='Connection limit reached. Start a new call to continue.';await task.cancel();break
            w=c.workout
            if not w:continue
            w.tick(dt)
            if w.status=='ended':
                if not ended_announced:
                    ended_announced=True;c.stage='finished';live['cue']=None
                    await task.queue_frames([InterruptionFrame(),TTSSpeakFrame('That is your time. You can stop here. Thanks for moving with me.')])
                continue
            if w.status!='running':continue
            q=live.get('cue')
            if q and now-q[3]>30:
                w.control('pause');live['cue']=None;c.error='Audio did not finish in time. Movement paused.'
                await task.queue_frames([InterruptionFrame()]);continue
            # Let model replies finish before starting the next timed instruction.
            if w.cue_done or q or c.user_speaking or c.bot_speaking or live['llm_busy'] or now-live['quiet_since']<.6:continue
            s=w.current()
            if not s:continue
            live['cue']=(w,w.index,w.run_generation,now);c.caption=s['cue']
            await task.queue_frames([TTSSpeakFrame(s['cue'])])
    @transport.event_handler('on_client_connected')
    async def connected(transport,client):
        nonlocal driver
        c.connected=True;c.error=None
        context.add_message({'role':'user','content':'Please introduce yourself briefly and ask how much time I have.'})
        await task.queue_frames([LLMRunFrame()]);driver=asyncio.create_task(clock())
    @transport.event_handler('on_client_disconnected')
    async def disconnected(transport,client):
        c.connected=False
        if c.workout:c.workout.control('pause')
        if driver:driver.cancel()
        await task.cancel()
    try:
        await PipelineRunner(handle_sigint=False).run(task)
    finally:
        c.connected=False
        if c.workout and c.workout.status=='running':c.workout.control('pause')
        if driver:
            driver.cancel()
            try:await driver
            except asyncio.CancelledError:pass
