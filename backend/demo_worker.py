"""One isolated code proposal; never called as a shell command by the API."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from agents.demo_queue import DemoQueue

ROOT=Path(__file__).resolve().parents[1]
TARGET='backend/darwin/demo_report.py'
SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'hypothesis':{'type':'string'},'path':{'type':'string','enum':[TARGET]},'code':{'type':'string'}},
    'required':['hypothesis','path','code']}
CHECKS="""import importlib.util, sys
s=importlib.util.spec_from_file_location('candidate',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
cases=[(0,0,'NO_CHECKS'),(1,0,'PASSED'),(0,1,'FAILED'),(8,2,'FAILED'),(100,0,'PASSED')]
for p,f,expected in cases:
    actual=m.validation_label(p,f)
    assert actual==expected, (p,f,expected,actual)
for p,f in [(-1,0),(0,-1)]:
    try:m.validation_label(p,f)
    except ValueError:pass
    else:raise AssertionError('negative counts accepted')
print('7 independent contract checks passed')
"""


def redacted(text):
    text=re.sub(r'(?i)(Bearer\s+)[^\s"\']+',r'\1[REDACTED]',text)
    return re.sub(r'\b(?:sk-[\w-]+|gh[pousr]_[\w]+)\b','[REDACTED]',text)


def safe_code(code):
    """Tiny display helper DSL: no imports, attributes, loops, I/O or arbitrary calls."""
    if len(code.encode())>8000: raise ValueError('candidate too large')
    tree=ast.parse(code)
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.If,ast.Compare,
             ast.Name,ast.Load,ast.Constant,ast.Expr,ast.Raise,ast.Call,ast.BoolOp,ast.And,ast.Or,
             ast.Gt,ast.GtE,ast.Lt,ast.LtE,ast.Eq,ast.NotEq,ast.UnaryOp,ast.Not,ast.USub,ast.Pass)
    functions=[x for x in tree.body if isinstance(x,ast.FunctionDef)]
    if len(functions)!=1 or functions[0].name!='validation_label':raise ValueError('unexpected function')
    fn=functions[0]
    if [a.arg for a in fn.args.args]!=['passed','failed'] or fn.decorator_list or fn.args.defaults or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg:
        raise ValueError('unexpected function signature')
    if any(not isinstance(x,(ast.FunctionDef,ast.Expr)) or isinstance(x,ast.Expr) and not isinstance(x.value,ast.Constant) for x in tree.body):
        raise ValueError('module side effect')
    for node in ast.walk(tree):
        if not isinstance(node,allowed):raise ValueError('unsupported code operation: '+type(node).__name__)
        if isinstance(node,ast.Name) and node.id not in ('passed','failed','int','str','ValueError'):
            raise ValueError('unapproved name')
        if isinstance(node,ast.Call) and not (isinstance(node.func,ast.Name) and node.func.id=='ValueError' and len(node.args)<=1 and not node.keywords):
            raise ValueError('unapproved function call')
    return code


def clean_env(codex=False):
    allowed=('PATH','SystemRoot','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','LOCALAPPDATA')
    env={k:v for k,v in os.environ.items() if k.upper() in {x.upper() for x in allowed}}
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',HYPERLIQUID_ENABLED='false',DARWIN_LLM_ENABLED='false',DARWIN_RESEARCH_PROVIDER='deterministic',GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
    env['USERPROFILE']=str(Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex'))).parent)
    if codex:
        home=os.getenv('CODEX_HOME') or str(Path(os.environ.get('USERPROFILE',str(Path.home()))) / '.codex')
        env['CODEX_HOME']=home # reuse auth in place; never copy it to a worktree
    return env


def run(command,cwd,timeout=180,input_text=None,codex=False):
    start=time.time()
    try:
        r=subprocess.run(command,cwd=cwd,env=clean_env(codex),input=input_text,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=timeout)
        return {'command':command,'exit_code':r.returncode,'seconds':round(time.time()-start,2),'output':redacted((r.stdout+'\n'+r.stderr)[-24000:])}
    except subprocess.TimeoutExpired:
        return {'command':command,'exit_code':124,'seconds':round(time.time()-start,2),'output':'Timeout; no candidate accepted'}


def git(args,cwd):
    r=run(['git','-c','safe.directory='+str(cwd),'-c','core.autocrlf=true',*args],cwd)
    if r['exit_code']:raise RuntimeError('Git operation failed: '+r['output'][:300])
    return r['output'].strip()


def execute(queue,job,root=ROOT,proposer=None,regression=None):
    root=Path(root).resolve(); identity=job['id']; artifacts=queue.root/identity
    artifacts.mkdir(exist_ok=True); work=queue.root/'worktrees'/identity; work.parent.mkdir(exist_ok=True)
    checks=[]
    def update(state=None,**kwargs):return queue.update(identity,state,checks=checks,**kwargs)
    def check(name,cmd,cwd,timeout=180):
        outcome=run(cmd,cwd,timeout);outcome['name']=name;checks.append(outcome);update()
        return outcome['exit_code']==0
    try:
        if git(['status','--porcelain'],root): raise ValueError('Commit implementation before running the isolated demo')
        pristine=git(['rev-parse','HEAD'],root)
        git(['worktree','add','--detach',str(work),pristine],root)
        # Only tracked files exist here; no .env, data, credentials or dependency hooks copied.
        if (work/'.env').exists():raise ValueError('Secret file present in snapshot')
        target=work/TARGET; original=target.read_text(encoding='utf-8')
        safe_code(original)
        test_path=artifacts/'independent_checks.py';test_path.write_text(CHECKS,encoding='utf-8')
        if not check('pristine contract',[sys.executable,'-I','-B',str(test_path),str(target)],work):raise ValueError('Reference baseline failed')
        broken=original.replace("return 'NO_CHECKS'","return 'PASSED'")
        if broken==original:raise ValueError('Known controlled defect injection unavailable')
        target.write_text(broken,encoding='utf-8')
        git(['add',TARGET],work)
        git(['-c','user.name=Darwin Demo','-c','user.email=demo@localhost','commit','-m','Controlled display-only defect in isolated demo'],work)
        base=git(['rev-parse','HEAD'],work)
        if check('defect reproduction',[sys.executable,'-I','-B',str(test_path),str(target)],work):raise ValueError('Defect did not reproduce')
        update(pristine_sha=pristine,base_sha=base,worktree=str(work))
        prompt=('Fix the display-only helper below. Return JSON with hypothesis, path and full corrected code. '
                'Do not run any tools or commands. No imports, I/O, loops, decorators, new functions, or calls except ValueError. '
                'Contract: zero checks => NO_CHECKS; any failed => FAILED; positive passed and zero failed => PASSED; negative counts raise ValueError. '
                'Only path '+TARGET+' is allowed. Tests are independent and immutable.\nSOURCE:\n'+broken)
        (artifacts/'prompt.txt').write_text(prompt,encoding='utf-8')
        update(prompt=prompt,provider=job['provider'])
        if proposer:
            proposal=proposer(broken);update('PROPOSED',real_call=False,model='fixture',provider='mock')
        elif job['provider']=='mock':
            proposal={'path':TARGET,'hypothesis':'Mock fixture restores the no-checks branch; no model was contacted.','code':original}
            update('PROPOSED',real_call=False,model='fixture')
        else:
            cli=os.getenv('DARWIN_CODEX_BIN') or shutil.which('codex')
            if not cli:raise ConnectionError('Codex CLI missing; run codex login in your Windows terminal')
            auth=run([cli,'login','status'],root,30,codex=True)
            if auth['exit_code'] or 'ChatGPT' not in auth['output']:
                raise ConnectionError('Codex ChatGPT login unavailable; run codex login in your Windows terminal')
            schema_path=artifacts/'schema.json';schema_path.write_text(json.dumps(SCHEMA),encoding='utf-8')
            response_path=artifacts/'response.json'
            # No shell, external tools, write permissions or user-defined MCP servers.
            model=os.getenv('CODEX_ENGINEER_MODEL','gpt-6-astra')
            cmd=[cli,'exec','--model',model,'--ignore-user-config','--ephemeral','--sandbox','read-only',
                 '-c','sqlite_home='+json.dumps(str(artifacts/'codex-state')),'-c','log_dir='+json.dumps(str(artifacts/'codex-logs')),'-c','approval_policy="never"','-c','features.shell_tool=false','-c','features.unified_exec=false',
                 '-c','features.plugins=false','-c','web_search="disabled"',
                 '--json','--output-schema',str(schema_path),'-o',str(response_path),'-']
            update(model=model)
            outcome=run(cmd,work,300,prompt,codex=True)
            (artifacts/'codex-log.txt').write_text(outcome['output'],encoding='utf-8')
            update(codex=outcome)
            if outcome['exit_code'] or not response_path.exists():
                quota=any(x in outcome['output'].lower() for x in ('usage limit','quota','rate limit'))
                denied='Access is denied' in outcome['output']
                raise ConnectionError('Codex quota atteint' if quota else 'Accès Windows refusé au CLI Codex. Lancer Demarrer-Darwin-Demo.cmd depuis la session Windows habituelle, puis choisir Codex CLI.' if denied else 'Codex invocation failed; inspect local CLI evidence')
            proposal=json.loads(response_path.read_text(encoding='utf-8'))
            update('LLM_CONNECTED',real_call=True)
            update('PROPOSED',real_call=True)
        if set(proposal)!=set(SCHEMA['required']) or proposal['path']!=TARGET:raise ValueError('Diff outside allowlist')
        code=safe_code(proposal['code'])
        # Reject any unexpected write by Codex before materializing its structured proposal.
        if git(['status','--porcelain','--untracked-files=all'],work):raise ValueError('Unexpected worktree writes by provider')
        target.write_text(code,encoding='utf-8')
        changed=git(['diff','--name-only'],work).splitlines()
        if changed!=[TARGET]:raise ValueError('Empty diff or files outside allowlist')
        diff=git(['diff','--no-ext-diff','--no-color'],work)
        if len(diff.encode())>16000:raise ValueError('Diff too large')
        (artifacts/'proposal.diff').write_text(diff,encoding='utf-8')
        update('TESTING',diff=diff,files=changed,hypothesis=proposal['hypothesis'][:3000])
        if not check('independent candidate contract',[sys.executable,'-I','-B',str(test_path),str(target)],work):raise ValueError('Independent tests failed')
        if not check('Python syntax',[sys.executable,'-m','compileall','-q',str(target)],work):raise ValueError('Syntax validation failed')
        if regression:
            if not regression(work):raise ValueError('Regression failed')
        else:
            validation_dir=Path(tempfile.mkdtemp(prefix='dv3-',dir=root.parent))
            if not check('backend regression',[sys.executable,'-m','pytest','backend','-q','-p','no:cacheprovider','--basetemp',str(validation_dir)],work,240):raise ValueError('Backend regression failed')
            modules=root/'frontend/node_modules'
            if not modules.exists():raise ValueError('Run frontend npm ci before the demo')
            shutil.copytree(modules,work/'frontend/node_modules')
            node=os.getenv('DARWIN_NODE_BIN') or shutil.which('node')
            if not node:raise ValueError('Node unavailable to local worker')
            if not check('frontend TypeScript',[node,'node_modules/typescript/bin/tsc'],work/'frontend'):raise ValueError('TypeScript failed')
            if not check('frontend build',[node,'node_modules/vite/bin/vite.js','build','--configLoader','runner'],work/'frontend'):raise ValueError('Frontend build failed')
        if git(['diff','--name-only'],work).splitlines()!=[TARGET]:raise ValueError('Validation changed protected files')
        git(['add',TARGET],work)
        git(['-c','user.name=Darwin Demo','-c','user.email=demo@localhost','commit','-m','Candidate: correct display validation label (human review required)'],work)
        candidate=git(['rev-parse','HEAD'],work)
        if git(['rev-parse','HEAD'],root)!=pristine:raise ValueError('Source branch changed during validation; candidate not integrated')
        update('READY_FOR_REVIEW',candidate_sha=candidate,reason='Independent checks passed. No integration, push or deployment performed.')
    except Exception as exc:
        update('PROVIDER_UNAVAILABLE' if isinstance(exc,ConnectionError) else 'REJECTED',reason=redacted(str(exc))[:1000])
        # This exact disposable target must remain under our registered worktree root.
        if work.exists() and work.resolve().parent==(queue.root/'worktrees').resolve():
            try:git(['worktree','remove','--force',str(work)],root)
            except Exception:pass
    job=next(j for j in queue.state()['jobs'] if j['id']==identity)
    (artifacts/'report.json').write_text(json.dumps(job,indent=2),encoding='utf-8')
    return job


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--mock',action='store_true');args=parser.parse_args()
    queue=DemoQueue(ROOT/'data/autocorrection')
    # OS-owned lock releases on crash; a second worker never claims a second job.
    lock=open(queue.root/'worker.lock','a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        print('Demo worker already running');return
    queue.recover()
    stop=threading.Event()
    def heartbeat():
        while not stop.is_set():queue.heartbeat();stop.wait(5)
    threading.Thread(target=heartbeat,daemon=True).start()
    try:
        if args.mock:queue.enqueue({'objective':'Explicit mock pipeline verification'},'mock')
        while True:
            job=queue.claim()
            if job:execute(queue,job)
            if args.once:break
            time.sleep(2)
    finally:stop.set();lock.close()


if __name__=='__main__':main()
