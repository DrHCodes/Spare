import asyncio
import copy
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from core import build_plan,block_count,generate_plan,Workout,PlanError,ProviderError,LIBRARY
from controller import Controller,explicit_yes
from effort import interpret_effort
from settings import settings,missing_keys


def fake_response(messages):
    q=json.loads(messages[-1]['content']);n=q['required_blocks']
    b=[{'exercise_id':('shallow' if i%2==0 else 'wallclose'),
        'instruction':LIBRARY['shallow' if i%2==0 else 'wallclose']['cue'],
        'start_cue':'Ready? Begin at your own pace.','work_fraction':.55} for i in range(n)]
    return {'model':'mock-test-only','usage':{'prompt_tokens':100,'completion_tokens':100},
            'choices':[{'message':{'content':json.dumps({'title':'Test session','rationale':'Mock generation for tests only.','blocks':b})}}]}


def fixture(seconds=180,effort=6):return generate_plan(seconds,effort,sender=fake_response)

class EffortTests(unittest.TestCase):
    def test_easy(self):self.assertEqual(interpret_effort('keep it easy').score,3)
    def test_lagree(self):self.assertEqual(interpret_effort('Like Lagree').score,6)
    def test_hard_reference(self):self.assertEqual(interpret_effort('fast pushups the entire time').score,8)
    def test_numeric_overrides_label(self):self.assertEqual(interpret_effort('Lagree is 8 out of 10 for me').score,8)
    def test_negation(self):self.assertEqual(interpret_effort('not intense, more like medium',6,.7).score,6)
    def test_clamp_max(self):self.assertTrue(interpret_effort('10 out of 10').capped)
    def test_no_known_score(self):
        with self.assertRaises(ValueError):interpret_effort('something different')
    def test_nonfinite(self):
        with self.assertRaises(ValueError):interpret_effort('something different',float('nan'))
    def test_confirmation_required(self):self.assertTrue(interpret_effort('medium').needs_confirmation)
    def test_never_measured(self):self.assertFalse(interpret_effort('easy').public()['measured'])
    def test_confirm_rejects_no(self):self.assertFalse(explicit_yes("no, I'm not ready"))
    def test_confirm_yes(self):self.assertTrue(explicit_yes("Yes, let's start"))

class PlanTests(unittest.TestCase):
    def test_all_previous_variants_plus_custom(self):
        for minutes in [2,3,5,7,10,15,20,30,45,60]:
            for effort in [3,6,8]:
                with self.subTest(minutes=minutes,effort=effort):
                    p=fixture(minutes*60,effort)
                    self.assertEqual(sum(x['seconds'] for x in p['plan']),minutes*60)
                    self.assertGreater(min(x['seconds'] for x in p['plan']),0)
                    self.assertTrue(p['inference']['test_mock'])
                    self.assertTrue(all(not LIBRARY[x['id']]['jumping'] for x in p['plan']))
    def raw(self,seconds=180):
        return json.loads(fake_response([{'content':json.dumps({'required_blocks':block_count(seconds)})}])['choices'][0]['message']['content'])
    def test_unknown_movement(self):
        p=self.raw();p['blocks'][0]['exercise_id']='jumping_jack'
        with self.assertRaises(PlanError):build_plan(p,180,6,False)
    def test_no_floor_without_permission(self):
        p=self.raw();p['blocks'][0]['exercise_id']='knee_pushup'
        with self.assertRaises(PlanError):build_plan(p,180,8,False)
    def test_repeated_muscles(self):
        p=self.raw();p['blocks'][1]['exercise_id']='shallow'
        with self.assertRaises(PlanError):build_plan(p,180,6,False)
    def test_side_balance(self):
        p=self.raw();p['blocks'][0]['exercise_id']='split_left'
        with self.assertRaises(PlanError):build_plan(p,180,8,False)
    def test_recovery_required(self):
        p=self.raw();p['blocks'][0]['work_fraction']=1
        with self.assertRaises(PlanError):build_plan(p,180,8,False)
    def test_awkward_script_rejected(self):
        p=self.raw();p['blocks'][0]['instruction']='Keep your feet quiet.'
        with self.assertRaises(PlanError):build_plan(p,180,6,False)
    def test_no_key_no_call(self):
        with patch.dict(os.environ,{'GENERAL_COMPUTE_API_KEY':''}):
            with self.assertRaises(ProviderError):generate_plan(180,6)
    def test_failure_not_preset(self):
        with self.assertRaises(PlanError):generate_plan(180,6,sender=lambda m:{'choices':[]})

class TimerTests(unittest.TestCase):
    def setUp(self):self.w=Workout(fixture())
    def test_does_not_start_itself(self):self.w.tick(1);self.assertEqual(self.w.budget,180)
    def test_break_does_not_credit(self):
        self.w.control('start');self.w.control('pause');self.w.tick(1)
        self.assertEqual(self.w.budget,179);self.assertEqual(self.w.movement_seconds,0)
    def test_work_gated_by_audio(self):
        self.w.control('start')
        while self.w.current()['kind']!='work':self.w._advance()
        before=self.w.left;self.w.tick(1);self.assertEqual(self.w.left,before)
        self.w.cue_finished(self.w.index);self.w.tick(1);self.assertEqual(self.w.left,before-1)
    def test_stop_terminal(self):self.w.control('stop');self.w.control('resume');self.assertEqual(self.w.status,'ended')
    def test_no_resume_after_interruption(self):
        self.w.control('start');self.w.control('pause');self.w.tick(1);self.assertEqual(self.w.status,'paused')
    def test_deadline_ends_even_in_break(self):
        self.w.control('start');self.w.control('pause');self.w.set_remaining(1);self.w.tick(1)
        self.assertEqual(self.w.status,'ended')
    def test_old_audio_does_not_advance_new_index(self):
        self.w.control('start');old=self.w.index;self.w._advance();self.w.cue_finished(old)
        self.assertFalse(self.w.cue_done)
    def test_gap_pauses(self):self.w.control('start');self.w.tick(12);self.assertEqual(self.w.status,'paused')
    def test_easier_pauses(self):
        self.w.control('start');self.w.easier();self.assertEqual(self.w.status,'paused');self.assertEqual(self.w.document['effort'],5)
    def test_skipped_time_not_movement(self):
        self.w.control('start');self.w.control('skip');self.assertEqual(self.w.movement_seconds,0)

class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_onboarding(self):
        c=Controller();c.set_time(3);self.assertEqual(c.stage,'effort');c.set_effort('medium',6,.9)
        c.transcript('yes');await c.design(sender=fake_response)
        self.assertEqual(c.workout.status,'ready');c.transcript('ready');c.control('start')
        c.voice_started();self.assertEqual(c.workout.status,'paused')
        c.transcript('I need a break');self.assertEqual(c.workout.status,'paused')
        c.transcript('ready');c.control('resume');self.assertEqual(c.workout.status,'running')
    async def test_cannot_start_without_ready(self):
        c=Controller();c.set_time(3);c.set_effort('easy');c.transcript('yes');await c.design(sender=fake_response)
        c.transcript('what happens next')
        with self.assertRaises(PlanError):c.control('start')
    async def test_design_requires_confirmation(self):
        c=Controller();c.set_time(3);c.set_effort('easy');c.transcript('maybe')
        with self.assertRaises(PlanError):await c.design(sender=fake_response)
    async def test_cancelled_design_no_late_commit(self):
        c=Controller();c.set_time(3);c.set_effort('easy');c.transcript('yes')
        def slow(m):time.sleep(.07);return fake_response(m)
        task=asyncio.create_task(c.design(sender=slow));await asyncio.sleep(.01);c.voice_started()
        with self.assertRaises(PlanError):await task
        self.assertIsNone(c.workout)
    async def test_design_limit(self):
        c=Controller(1);c.set_time(3);c.set_effort('easy');c.transcript('yes');await c.design(sender=fake_response)
        c.workout.control('stop');c.transcript('yes')
        with self.assertRaises(PlanError):await c.design(sender=fake_response)
    async def test_revision_preserves_completed_time(self):
        c=Controller();c.set_time(10);c.set_effort('medium');c.transcript('yes');await c.design(sender=fake_response)
        c.control('start');c.workout.movement_seconds=20;await c.revise('easy',3,sender=fake_response)
        self.assertEqual(c.workout.status,'paused');self.assertEqual(c.workout.movement_seconds,20)
    async def test_no_arbitrary_automatic_resume(self):
        c=Controller();c.workout=Workout(fixture());c.workout.control('start');c.voice_started();c.transcript('thank you')
        self.assertEqual(c.workout.status,'paused')

class ConfigTests(unittest.TestCase):
    def test_provider_keys(self):
        for mode,expected in [('gradium',['GENERAL_COMPUTE_API_KEY','GRADIUM_API_KEY']),('openai',['GENERAL_COMPUTE_API_KEY','OPENAI_API_KEY']),('hybrid',['GENERAL_COMPUTE_API_KEY','GRADIUM_API_KEY','OPENAI_API_KEY'])]:
            with patch.dict(os.environ,{'SPEECH_PROVIDER':mode,'GENERAL_COMPUTE_API_KEY':'','GRADIUM_API_KEY':'','OPENAI_API_KEY':''}):
                self.assertEqual(missing_keys(settings()),expected)

if __name__=='__main__':unittest.main()
