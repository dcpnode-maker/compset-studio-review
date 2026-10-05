import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from compset import collection_control as c


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.collector=self.root/'collector';self.collector.mkdir()
        self.control=self.root/'control';self.control.mkdir()
        self.config={'collector_root':str(self.collector),'control_root':str(self.control),'app_root':str(self.root)}

    def test_running_refresh_follows_existing_owner_and_deduplicates(self):
        with patch.object(c,'process_matches',return_value=True):
            a=c.request_refresh(self.config,{'dataset':'dubai'})
            b=c.request_refresh(self.config,{'dataset':'dubai'})
        self.assertEqual(a['state'],'already_running');self.assertEqual(a['request_id'],b['request_id'])
        self.assertNotIn('collector_root',a)

    def test_stopped_owner_requests_review_without_launch_or_reset(self):
        c.save(self.collector/'STATUS.json',{'state':'stopped'})
        before=(self.collector/'STATUS.json').read_bytes()
        with patch.object(c,'process_matches',return_value=False),patch.object(c.subprocess,'run') as run:
            answer=c.request_refresh(self.config,{'dataset':'dubai'})
        self.assertEqual(answer['state'],'review_requested');run.assert_not_called()
        self.assertEqual(before,(self.collector/'STATUS.json').read_bytes())

    def test_unknown_request_fields_rejected(self):
        with self.assertRaises(ValueError):c.request_refresh(self.config,{'dataset':'dubai','url':'https://arbitrary.invalid'})

    def test_exact_incident_identity(self):
        a={'state':'stopped','current_attempt':{'token':'a'},'error_type':'ProxyError'}
        self.assertEqual(c.incident_key(self.collector,a),c.incident_key(self.collector,{**a,'updated_at':'new'}))
        self.assertNotEqual(c.incident_key(self.collector,a),c.incident_key(self.collector,{**a,'current_attempt':{'token':'b'}}))

    def test_healthy_watcher_makes_no_model_calls(self):
        c.save(self.collector/'STATUS.json',{'state':'running'})
        with patch.object(c,'load_config',return_value={**self.config,'astra_enabled':True}),patch.object(c,'process_matches',return_value=True),patch.object(c,'run_repair') as repair:
            c.watch(self.root,once=True)
        repair.assert_not_called()

    def test_owner_disappears_with_stale_running_state_triggers_one_review(self):
        status={'state':'running','current_attempt':{'token':'interrupted-request'}}
        c.save(self.collector/'STATUS.json',status)
        c.save(self.collector/'PROCESS.json',{'launcher_pid':99,'launcher_start_utc_ticks':100})
        before=(self.collector/'STATUS.json').read_bytes()
        with patch.object(c,'load_config',return_value={**self.config,'astra_enabled':True}),patch.object(c,'run_repair') as repair:
            with patch.object(c,'process_matches',return_value=True):c.watch(self.root,once=True)
            with patch.object(c,'process_matches',return_value=False):
                c.watch(self.root,once=True)
                c.watch(self.root,once=True)
        repair.assert_called_once()
        self.assertEqual(repair.call_args.args[1]['reason'],'recorded_collector_process_missing')
        self.assertEqual((self.collector/'STATUS.json').read_bytes(),before)

    def test_owner_loss_does_not_override_pause_or_completion(self):
        for state in ('paused','completed','budget_exhausted'):
            self.assertEqual(c.observed_incident_status({'state':state},False,True),{'state':state})

    def test_same_incident_not_repeated(self):
        s={'state':'stopped','current_attempt':{'token':'abc'}}
        c.save(self.collector/'STATUS.json',s)
        c.save(self.control/'repairs'/(c.incident_key(self.collector,s)+'.json'),{'started_at':c.stamp(),'state':'needs_attention'})
        with patch.object(c,'load_config',return_value={**self.config,'astra_enabled':True}),patch.object(c,'process_matches',return_value=False),patch.object(c,'run_repair') as repair:
            c.watch(self.root,once=True)
        repair.assert_not_called()

    def test_pause_is_preserved(self):
        c.save(self.collector/'STATUS.json',{'state':'paused'})
        with patch.object(c,'process_matches',return_value=False):
            self.assertEqual(c.request_refresh(self.config,{'dataset':'dubai'})['state'],'paused')

    def test_old_stop_on_first_start_requires_demand(self):
        c.save(self.collector/'STATUS.json',{'state':'stopped','reason':'old_stop'})
        with patch.object(c,'load_config',return_value={**self.config,'astra_enabled':True}),patch.object(c,'process_matches',return_value=False),patch.object(c,'run_repair') as repair:
            c.watch(self.root,once=True)
            repair.assert_not_called()
            c.request_refresh(self.config,{'dataset':'dubai'})
            c.watch(self.root,once=True)
            repair.assert_called_once()

    def test_new_stop_after_healthy_observation_triggers_once(self):
        c.save(self.collector/'STATUS.json',{'state':'running'})
        with patch.object(c,'load_config',return_value={**self.config,'astra_enabled':True}),patch.object(c,'process_matches',return_value=False),patch.object(c,'run_repair') as repair:
            c.watch(self.root,once=True)
            c.save(self.collector/'STATUS.json',{'state':'stopped','current_attempt':{'token':'new'}})
            c.watch(self.root,once=True)
            c.watch(self.root,once=True)
            repair.assert_called_once()

    def test_triage_waiting_does_not_escalate(self):
        triage={'state':'waiting','summary':'Provider restriction is recorded.','diagnosis':'HTTP 403','evidence_paths':['STATUS.json'],'actionable':False,'tests':[]}
        def fake_run(command, **kwargs):
            output=Path(command[command.index('--output-last-message')+1]);output.write_text(json.dumps(triage),encoding='utf-8')
            return type('Done',(),{'returncode':0})()
        config={**self.config,'astra_enabled':True,'codex_executable':'codex','triage_model':'gpt-6-luna','escalation_model':'gpt-6-astra'}
        with patch.object(c.subprocess,'run',side_effect=fake_run) as run:
            c.run_repair(config,{'state':'failed'},'incident-a')
        run.assert_called_once()
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('--model')+1],'gpt-6-luna')
        report=c.read(self.control/'repairs'/'incident-a.json',{})
        self.assertEqual(report['dispatch_kind'],'automatic_triage')
        self.assertEqual(report['state'],'waiting')

    def test_actionable_triage_escalates_with_sanitized_diagnosis(self):
        responses=[{'state':'needs_attention','summary':'Local transport failure.','diagnosis':'Connection reset in proxy adapter','evidence_paths':['STATUS.json'],'actionable':True,'tests':['focused test']},
                   {'state':'needs_attention','summary':'Repair requires owner review.','changed_files':[],'tests':[]}]
        commands=[]
        def fake_run(command, **kwargs):
            commands.append(command)
            output=Path(command[command.index('--output-last-message')+1]);output.write_text(json.dumps(responses.pop(0)),encoding='utf-8')
            return type('Done',(),{'returncode':0})()
        config={**self.config,'astra_enabled':True,'codex_executable':'codex','triage_model':'gpt-6-luna','escalation_model':'gpt-6-astra'}
        with patch.object(c.subprocess,'run',side_effect=fake_run) as run:
            c.run_repair(config,{'state':'failed'},'incident-b')
        self.assertEqual(run.call_count,2)
        self.assertEqual(commands[0][commands[0].index('--model')+1],'gpt-6-luna')
        self.assertEqual(commands[1][commands[1].index('--model')+1],'gpt-6-astra')
        escalation_prompt=run.call_args_list[1].kwargs['input']
        self.assertIn('Connection reset in proxy adapter',escalation_prompt)
        self.assertIn('Bounded Luna triage supplied',escalation_prompt)
        report=c.read(self.control/'repairs'/'incident-b.json',{})
        self.assertEqual(report['dispatch_kind'],'automatic_escalation')

    def test_configurable_models_default_and_astra_compatibility_gate(self):
        self.assertEqual(c.run_repair.__defaults__,None)
        config={**self.config,'astra_enabled':False,'codex_executable':'codex'}
        with patch.object(c.subprocess,'run') as run:
            c.run_repair(config,{'state':'failed'},'incident-c')
        run.assert_not_called()


if __name__=='__main__':unittest.main()
