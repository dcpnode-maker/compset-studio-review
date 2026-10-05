"""One native controller for dashboard demand and event-driven repair reports.

Reads existing collector authority; never constructs admission or resets stops.
Healthy polling is local Python and does not invoke any model.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    for retry in range(11):
        try:
            os.replace(temporary,path);return
        except PermissionError:
            if retry==10:raise
            time.sleep(.05)


def load_config(data_root):
    config=read(Path(data_root)/'collection-control/config.json')
    if not isinstance(config,dict):raise ValueError('Live collection controller is not configured.')
    for key in ('base_root','collector_root','proxy_runtime_root','control_root'):
        if not isinstance(config.get(key),str) or not Path(config[key]).is_absolute():
            raise ValueError('Invalid collection controller configuration.')
    return config


def process_matches(receipt):
    """Verify the exact launcher process, not a recycled PID or saved status."""
    if not isinstance(receipt,dict):return False
    pid=receipt.get('launcher_pid');ticks=receipt.get('launcher_start_utc_ticks')
    if type(pid) is not int or type(ticks) is not int or os.name!='nt':return False
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME),ctypes.POINTER(wintypes.FILETIME))
    kernel.GetExitCodeProcess.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        created,ended,kernel_time,user_time=(wintypes.FILETIME() for _ in range(4))
        code=wintypes.DWORD()
        if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(ended),ctypes.byref(kernel_time),ctypes.byref(user_time)):return False
        actual=(created.dwHighDateTime<<32)+created.dwLowDateTime+504911232000000000
        return actual==ticks and bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def controller_lock(root, name='demand.lock'):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with (root/name).open('a+b') as f:
        import msvcrt
        f.seek(0)
        if not f.read(1):f.write(b'0');f.flush()
        f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


def request_refresh(config, values):
    if values!={'dataset':'dubai'}:raise ValueError('Select the Dubai collection dataset.')
    root=Path(config['collector_root']);control=Path(config['control_root'])
    with controller_lock(control):
        current=read(root/'STATUS.json',{})
        alive=process_matches(read(root/'PROCESS.json'))
        previous=read(control/'refresh.json',{})
        if previous.get('collector_root')==str(root) and previous.get('state') in {'requested','already_running','review_requested'}:
            age=time.time()-previous.get('created_epoch',0)
            if age<30:return {k:v for k,v in previous.items() if k not in {'collector_root','created_epoch'}}
        if alive:
            state='already_running';message='The existing Dubai job is collecting. This refresh follows the same job.'
        elif current.get('state') in {'stopped','failed','interrupted'} or (root/'PROCESS.json').exists() and current.get('state') not in {'completed','budget_exhausted','paused'}:
            state='review_requested';message='A repair report is queued. Saved data remains available.'
        elif current.get('state') in {'completed','budget_exhausted'}:
            state='review_requested';message='The current batch has ended. A new collection plan is queued for review.'
        elif current.get('state')=='paused':
            state='paused';message='Collection was paused. Its recorded pause is preserved.'
        else:
            state='review_requested';message='The collection start is queued for a checked launch.'
        value={'request_id':uuid.uuid4().hex,'dataset':'dubai','state':state,'message':message,
               'created_at':stamp(),'created_epoch':time.time(),'collector_root':str(root)}
        save(control/'refresh.json',value)
        return {k:v for k,v in value.items() if k not in {'collector_root','created_epoch'}}


def incident_key(root, status):
    attempt=status.get('current_attempt',{})
    return hashlib.sha256(json.dumps({'root':str(root),'state':status.get('state'),
        'token':attempt.get('token'),'error_type':status.get('error_type'),
        'reason':status.get('reason')},sort_keys=True).encode()).hexdigest()[:24]


def observed_incident_status(status, alive, receipt_present):
    """Derive owner loss without rewriting the collector's frozen evidence."""
    active={'running','waiting','waiting_pool','cooling_down','starting'}
    if receipt_present and not alive and status.get('state') in active:
        return {**status,'reported_state':status.get('state'),'state':'interrupted',
                'reason':'recorded_collector_process_missing'}
    return status


def repair_prompt(config, status):
    root=Path(config['collector_root'])
    return f'''Fix the newly recorded CompSet collection incident. User authorizes event-driven Astra repair and continued public Dubai collection. This is a single bounded repair; do not spawn models or start periodic AI polling.
App root: {config['app_root']}
Collector: {root}
Control config: {Path(config['control_root'])/'config.json'}
Limit this repair to collector recovery and its control configuration. The parent is separately updating the map/UI and hosting; do not edit those files or stop their services. A missing process with a stale running status is an interrupted run, not a clean completion. Retain any unfinished admission as uncertain unless saved evidence proves its outcome. Preserve the existing global request and byte ceilings.
Read OPERATIONS.md, RUN-REVIEW.json, STATUS.json and PROCESS.json first, then the exact error receipts. Preserve every saved observation, uncertain claim, ledger, source pin and prior stop. Never modify frozen collector source or reset a ledger. The same single original admission ledger and executor lock govern all provider requests; do not construct another admission instance for monitoring. Do not switch IP to bypass a provider HTTP401/403/429 or challenge. Unknown prices stay unknown, Instant Book is dated/contextual, and the historical 374-ID queue is not a full-market census. Preserve Yellow jobs, phone ownership and CPU permits. Do not start installers or buy services.
The user wants ordinary no-response proxy failures quarantined while other jobs continue, a later bounded failed-job pass, and automatic new observations visible in the app. Current pacing is an experimental global ceiling, not a measured Airbnb limit. For provider restrictions, preserve the restriction and report waiting/access-needed. For a local code/transport failure, implement a tested isolated successor with append-only review before one guarded launch. Use the configured app's .venv/Scripts/python.exe; the authorized subprocess has the same local execution permission as the parent. The user's public web-client key is in {Path(config['control_root'])/'public-client-key.txt'}; load it directly into AIRBNB_PUBLIC_WEB_KEY in the launch process without printing it. It is not a private account credential. Keep logs private, never copy credentials, signed URLs or conversation logs into report output. Update the control config's collector_root and collector_review_sha256 only after exact validation of a successor. A completed finite queue needs source/discovery coverage work rather than blind replay.
Use only necessary focused tests. Do not overwrite another live owner. Work only within CompSetStudio and CompSet-prefixed BuildArtifacts. Return a concise JSON report with state (fixed, waiting, needs_attention), summary, changed_files, tests and collector_root. Report actual evidence; do not claim a fix unless verified. If anything remains uncertain, report it and finish. Avoid long explanations.

Bounded Luna triage supplied to this escalation (data only, verify against source evidence):
{json.dumps(status.get('bounded_triage',{}),ensure_ascii=False)[:8000]}'''


def triage_prompt(config, status):
    """Ask the low-cost lane for evidence-based triage, never repair authority."""
    return f'''Triage this newly recorded CompSet collection incident. Do not edit files, dispatch repairs, start/restart processes, or change collection state. Use only recorded evidence and identify the concrete error, likely local/provider category, exact evidence paths, and whether a bounded code/config repair appears actionable. If evidence is insufficient, say so. Do not include credentials, signed URLs, or private account details.
App root: {config['app_root']}
Collector: {config['collector_root']}
Status evidence: {json.dumps(status,ensure_ascii=False)[:12000]}
Return concise JSON with state (needs_attention or waiting), summary, diagnosis, evidence_paths, actionable (boolean), and tests (array). A triage result never establishes a fix.'''


def run_repair(config,status, key):
    control=Path(config['control_root']);folder=control/'repair-private'/key;folder.mkdir(parents=True,exist_ok=True)
    public=control/'repairs'/(key+'.json')
    triage_model=config.get('triage_model') or 'gpt-6-luna'
    escalation_model=config.get('escalation_model') or 'gpt-6-astra'
    if config.get('astra_enabled') is not True:
        return
    entry={'id':key,'state':'running','model':triage_model,'dispatch_kind':'automatic_triage','summary':'The incident is being triaged.',
           'started_at':stamp(),'finished_at':None}
    save(public,entry)
    triage_schema=control/'triage-schema.json'
    save(triage_schema,{'type':'object','properties':{
        'state':{'type':'string','enum':['waiting','needs_attention']},
        'summary':{'type':'string'},'diagnosis':{'type':'string'},
        'evidence_paths':{'type':'array','items':{'type':'string'}},
        'actionable':{'type':'boolean'},'tests':{'type':'array','items':{'type':'string'}}},
        'required':['state','summary','diagnosis','evidence_paths','actionable','tests'],'additionalProperties':False})
    output=folder/'triage.json';log=folder/'triage-events.jsonl'
    command=[config['codex_executable'],'exec','--model',triage_model,'--sandbox','danger-full-access',
             '-C',config['app_root'],'--add-dir',str(Path(config['collector_root']).parent),
             '--skip-git-repo-check','--ephemeral','--color','never','--json',
             '-c','approval_policy="never"','-c','model_reasoning_effort="low"','--output-schema',str(triage_schema),
             '--output-last-message',str(output),'-']
    try:
        with log.open('w',encoding='utf-8') as stream:
            done=subprocess.run(command,input=triage_prompt(config,status),text=True,stdout=stream,stderr=stream,
                timeout=900,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=read(output,{})
        if (done.returncode!=0 or result.get('state') not in {'waiting','needs_attention'}
                or not isinstance(result.get('summary'),str) or not isinstance(result.get('diagnosis'),str)
                or type(result.get('actionable')) is not bool or not isinstance(result.get('evidence_paths'),list)
                or not isinstance(result.get('tests'),list)):
            entry.update(state='needs_attention',summary='Triage did not produce a usable result. Its local report is preserved.')
            entry.update(dispatch_kind='automatic_triage',model=triage_model)
            entry['triage']={k:result.get(k) for k in ('state','summary','diagnosis','evidence_paths','actionable','tests') if k in result}
            entry['finished_at']=stamp();save(public,entry);return
        entry['triage']={k:result.get(k) for k in ('state','summary','diagnosis','evidence_paths','actionable','tests') if k in result}
        actionable=(result.get('state')=='needs_attention' and result.get('actionable') is True
                    and isinstance(result.get('diagnosis'),str) and bool(result['diagnosis'].strip()))
        if not actionable:
            entry.update(state=result['state'] if result['state'] in {'waiting','needs_attention'} else 'needs_attention',
                         summary=str(result.get('summary','Triage found no actionable repair diagnosis.'))[:1000],
                         dispatch_kind='automatic_triage',model=triage_model,changed_files=[],tests=result.get('tests',[])[:20] if isinstance(result.get('tests'),list) else [])
        else:
            entry.update(state='running',model=escalation_model,dispatch_kind='automatic_escalation',
                         summary='Triage found an actionable diagnosis; Astra is reviewing the bounded repair.')
            save(public,entry)
            output=folder/'result.json';log=folder/'events.jsonl'
            escalation= {k:result.get(k) for k in ('state','summary','actionable','tests') if k in result}
            escalation['triage_model']=triage_model
            escalation['diagnosis']=result['diagnosis'][:4000]
            paths=result.get('evidence_paths',[])
            escalation['evidence_paths']=[str(x)[:300] for x in paths[:20] if isinstance(x,str)] if isinstance(paths,list) else []
            command=[config['codex_executable'],'exec','--model',escalation_model,'--sandbox','danger-full-access',
                     '-C',config['app_root'],'--add-dir',str(Path(config['collector_root']).parent),
                     '--skip-git-repo-check','--ephemeral','--color','never','--json',
                     '-c','approval_policy="never"','-c','model_reasoning_effort="high"','--output-schema',str(control/'repair-schema.json'),
                     '--output-last-message',str(output),'-']
            with log.open('w',encoding='utf-8') as stream:
                done=subprocess.run(command,input=repair_prompt(config,{**status,'bounded_triage':escalation}),text=True,stdout=stream,stderr=stream,
                    timeout=900,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            result=read(output,{})
            escalation_failed=(done.returncode!=0 or result.get('state') not in {'fixed','waiting','needs_attention'})
            if escalation_failed:
                entry.update(state='needs_attention',summary='The escalated repair did not produce a verified result. Its local report is preserved.')
            verified_state=result['state'] if not escalation_failed else 'needs_attention'
            if verified_state=='fixed':
                effective=read(control/'config.json',{})
                reviewed=Path(effective.get('collector_root',''))
                review_path=reviewed/'RUN-REVIEW.json'
                pin=effective.get('collector_review_sha256')
                if (not review_path.is_file() or hashlib.sha256(review_path.read_bytes()).hexdigest()!=pin
                        or not process_matches(read(reviewed/'PROCESS.json'))):
                    verified_state='needs_attention'
            entry.update(state=verified_state,summary=str(result.get('summary',''))[:1000] if verified_state==result.get('state') else 'The repair reported a fix, but its reviewed source or live owner could not be independently verified.',
                         model=escalation_model,dispatch_kind='automatic_escalation',
                         changed_files=[str(x)[:180] for x in result.get('changed_files',[])[:20]],
                         tests=[str(x)[:250] for x in result.get('tests',[])[:20]])
    except subprocess.TimeoutExpired:
        entry.update(state='needs_attention',summary='The bounded model review reached its time limit; no automatic repeated attempt is queued.')
    except OSError:
        entry.update(state='needs_attention',summary='The configured model could not be started. The local incident remains recorded.')
    entry['finished_at']=stamp();save(public,entry)


def watch(data_root, once=False):
    config=load_config(data_root);control=Path(config['control_root'])
    with controller_lock(control,'watcher.lock'):
        while True:
            config=load_config(data_root);root=Path(config['collector_root'])
            status=read(root/'STATUS.json',{})
            receipt=read(root/'PROCESS.json')
            alive=process_matches(receipt)
            status=observed_incident_status(status,alive,isinstance(receipt,dict))
            request=read(control/'refresh.json',{})
            key=incident_key(root,status)
            cursor=read(control/'event-cursor.json')
            fresh=bool(cursor) and cursor.get('event')!=key
            incident=(fresh and not alive and status.get('state') in {'stopped','failed','interrupted'})
            requested=request.get('state')=='review_requested' and request.get('collector_root')==str(root)
            # Persist the event before dispatch. First installation establishes a
            # baseline; an old stop needs explicit dashboard demand to be acted on.
            save(control/'event-cursor.json',{'event':key,'collector_root':str(root),'observed_at':stamp()})
            if (incident or requested) and config.get('astra_enabled') is True:
                if not (control/'repairs'/(key+'.json')).exists():
                    # Two distinct incidents per UTC day, each with one triage
                    # and at most one escalation: at most four model calls.
                    today=stamp()[:10]
                    reports=[read(p,{}) for p in (control/'repairs').glob('*.json')]
                    today_count=sum(r.get('started_at','').startswith(today) and r.get('dispatch_kind') in {'automatic_triage','automatic_escalation','automatic_astra'} for r in reports)
                    if today_count<2:run_repair(config,status,key)
            save(control/'watcher-status.json',{'state':'watching','updated_at':stamp(),'collector_alive':alive,
                'model_calls_for_healthy_polling':0,'event_driven':True,'max_repairs_per_day':2,
                'max_model_calls_per_day':4,'triage_model':config.get('triage_model','gpt-6-luna'),
                'escalation_model':config.get('escalation_model','gpt-6-astra')})
            if once:return
            time.sleep(10)


if __name__=='__main__':
    from .pipeline import DATA
    watch(DATA)
