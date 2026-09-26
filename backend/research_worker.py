"""Restricted signal-policy candidate worker. No generated code enters the running engine."""
import ast
import json
import math
import re
import os
from pathlib import Path
import sqlite3
import shutil
import sys
import time
import tempfile

TARGET='backend/darwin/research_policy.py'
NAMES=('raw_signal','spread','flow','imbalance')

def safe_policy(code):
    if len(code)>4000:raise ValueError('Policy too large')
    tree=ast.parse(code)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):raise ValueError('One function required')
    fn=tree.body[0]
    if fn.name!='research_policy' or [a.arg for a in fn.args.args]!=list(NAMES) or fn.decorator_list or fn.args.defaults or fn.args.kwonlyargs or fn.args.posonlyargs or fn.args.kwarg or fn.args.vararg or fn.returns or any(a.annotation for a in fn.args.args):raise ValueError('Invalid signature')
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.If,ast.IfExp,ast.Compare,ast.Name,ast.Load,ast.Constant,ast.BinOp,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.UnaryOp,ast.USub,ast.UAdd,ast.Not,ast.BoolOp,ast.And,ast.Or,ast.Gt,ast.GtE,ast.Lt,ast.LtE,ast.Eq,ast.NotEq,ast.Call)
    for node in ast.walk(tree):
        if not isinstance(node,allowed):raise ValueError('Forbidden operation '+type(node).__name__)
        if isinstance(node,ast.Name) and node.id not in (*NAMES,'abs','min','max'):raise ValueError('Forbidden name')
        if isinstance(node,ast.Constant) and (type(node.value) not in (int,float,bool) or not math.isfinite(node.value) or abs(node.value)>100):raise ValueError('Invalid constant')
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in ('abs','min','max') or node.keywords or not 1<=len(node.args)<=4):raise ValueError('Invalid call')
    scope={};exec(compile(tree,'<restricted-policy>','exec'),{'__builtins__':{},'abs':abs,'min':min,'max':max},scope)
    return scope['research_policy']

def replay(code, ticks, genome, notional, fees):
    from darwin.paper import PaperAccount
    import darwin.paper as paper
    policy=safe_policy(code);control=PaperAccount(genome,notional,fees);variant=PaperAccount(genome,notional,fees)
    original=paper.raw_signal_for_genome
    def signal(features,strategy):
        raw=original(features,strategy)
        value=policy(raw,float(features.get('spread',0)),float(features.get('flow',0)),float(features.get('weighted_imbalance',0)))
        if type(value) not in (float,int) or not math.isfinite(value) or abs(value)>abs(raw)+1e-12 or value*raw<0:raise ValueError('Signal must only attenuate or filter the original direction')
        return value
    try:
        for tick in ticks:
            paper.raw_signal_for_genome=original;control.observe(tick)
            paper.raw_signal_for_genome=signal;variant.observe(tick)
        if ticks:
            control._close(ticks[-1],reason='replay_end');variant._close(ticks[-1],reason='replay_end')
    finally:paper.raw_signal_for_genome=original
    a,b=control.metrics(),variant.metrics()
    sufficient=min(a['sample_seconds'],b['sample_seconds'])>=300 and min(a['closed_trades'],b['closed_trades'])>=5
    return {'control':a,'candidate':b,'delta_net_usd':b['pnl']-a['pnl'],
        'verdict':'DESCRIPTIVE_COMPARISON' if sufficient else 'INSUFFICIENT_EVIDENCE',
        'interpretation':'Held-out tail of recorded Hyperliquid observations. Same books/fees; no future-live validation or profitability proof.'}

def execute_research(queue,job,root):
    from demo_worker import git,run,resolve_codex,redacted
    root=Path(root); artifacts=queue.root/job['id'];artifacts.mkdir(exist_ok=True)
    work=queue.root/'worktrees'/job['id'];work.parent.mkdir(exist_ok=True)
    checks=[]
    def update(state=None,**kw):return queue.update(job['id'],state,checks=checks,**kw)
    def check(name,cmd,timeout=240):
        result=run(cmd,work,timeout);result['name']=name;checks.append(result);update()
        if result['exit_code']:raise ValueError(name+' failed')
        return result
    try:
        if git(['status','--porcelain'],root):raise ValueError('Source checkout must be committed before proposal')
        base=git(['rev-parse','HEAD'],root)
        git(['worktree','add','--detach',str(work),base],root)
        if (work/'.env').exists():raise ValueError('Secret file in snapshot')
        pack=job['task_pack'];lab_path=Path(pack['lab_path']).resolve()
        if lab_path.parent!=(root/'data').resolve() or not lab_path.name.startswith('research-lab-'):raise ValueError('Invalid evidence store')
        with sqlite3.connect(lab_path) as db:
            ticks=[json.loads(r[0]) for r in db.execute('SELECT payload FROM ticks ORDER BY ts DESC LIMIT 3600')][::-1]
        if len(ticks)<60:raise ValueError('Need at least 60 captured observations')
        split=max(1,int(len(ticks)*.7));train=ticks[:split];holdout=ticks[split:]
        payload={'ticks':holdout,'genome':pack['genome'],'notional':pack['notional'],'fees':pack['fees']}
        (artifacts/'holdout.json').write_text(json.dumps(payload),encoding='utf-8')
        original=(work/TARGET).read_text(encoding='utf-8-sig')
        baseline=replay(original,train,pack['genome'],pack['notional'],pack['fees'])
        prompt=('Propose one conservative signal-policy code change addressing the supplied measured incident. '
            'Return JSON with hypothesis, path and full code. Do not use tools. Only function research_policy(raw_signal, spread, flow, imbalance), '
            'numeric constants <=100, arithmetic without power, comparisons, if/return and abs/min/max are allowed. '
            'Output must be finite within [-1,1]. No imports, loops, attributes, I/O or other calls. '
            'Keep the sign of a nonzero signal; filtering to zero or reducing magnitude is permitted. '
            'Do not claim improved performance. Independent held-out observations will be tested.\nSOURCE:\n'+original+
            '\nMEASURED INCIDENT:\n'+json.dumps({'code':pack['incident'].get('code'),'persistent':True})+'\nTRAINING SUMMARY:\n'+json.dumps(baseline))
        schema={'type':'object','additionalProperties':False,'properties':{'hypothesis':{'type':'string'},'path':{'type':'string','enum':[TARGET]},'code':{'type':'string'}},'required':['hypothesis','path','code']}
        (artifacts/'schema.json').write_text(json.dumps(schema),encoding='utf-8');response=artifacts/'response.json'
        (artifacts/'prompt.txt').write_text(prompt,encoding='utf-8')
        cli=resolve_codex()
        if not cli:raise ConnectionError('Codex CLI unavailable')
        auth=run([cli,'login','status'],root,30,codex=True)
        if auth['exit_code'] or 'ChatGPT' not in auth['output']:raise ConnectionError('Codex ChatGPT login required')
        model=os.getenv('CODEX_ENGINEER_MODEL','gpt-6-astra')
        cmd=[cli,'exec','--model',model,'--ignore-user-config','--ephemeral','--sandbox','read-only',
            '-c','sqlite_home='+json.dumps(str(artifacts/'codex-state')),'-c','log_dir='+json.dumps(str(artifacts/'codex-logs')),
            '-c','approval_policy="never"','-c','features.shell_tool=false','-c','features.unified_exec=false','-c','features.plugins=false','-c','web_search="disabled"',
            '--json','--output-schema',str(artifacts/'schema.json'),'-o',str(response),'-']
        update(base_sha=base,worktree=str(work),model=model,prompt=prompt)
        out=run(cmd,work,300,prompt,codex=True);update(codex=out)
        if out['exit_code'] or not response.exists():raise ConnectionError('Codex invocation unavailable; see recorded evidence')
        update('LLM_CONNECTED',real_call=True)
        proposal=json.loads(response.read_text(encoding='utf-8'))
        if proposal.get('path')!=TARGET:raise ValueError('Unexpected target')
        safe_policy(proposal['code'])
        if git(['status','--porcelain','--untracked-files=all'],work):raise ValueError('Unexpected provider write')
        (work/TARGET).write_text(proposal['code'],encoding='utf-8')
        if git(['diff','--name-only'],work).splitlines()!=[TARGET]:raise ValueError('Empty or unapproved diff')
        update('TESTING',hypothesis=proposal['hypothesis'],files=[TARGET],diff=git(['diff','--no-ext-diff'],work))
        check('restricted policy contracts',[sys.executable,str(root/'backend/research_worker.py'),'--contract',str(work/TARGET)])
        result=check('held-out recorded-market comparison',[sys.executable,str(root/'backend/research_worker.py'),'--replay',str(work/TARGET),str(artifacts/'holdout.json')])
        comparison=json.loads(result['stdout']);update(comparison=comparison)
        check('backend regression',[sys.executable,'-m','pytest','backend','-q','-p','no:cacheprovider','--basetemp',tempfile.mkdtemp(prefix='dr-',dir=root.parent)])
        modules=root/'frontend/node_modules'
        if not modules.exists():raise ValueError('Frontend dependencies unavailable')
        shutil.copytree(modules,work/'frontend/node_modules')
        node=os.getenv('DARWIN_NODE_BIN') or shutil.which('node')
        if not node:raise ValueError('Node unavailable')
        # Commands run in the isolated frontend via absolute paths and explicit cwd wrapper.
        for name,args in [('frontend TypeScript',['node_modules/typescript/bin/tsc']),('frontend build',['node_modules/vite/bin/vite.js','build','--configLoader','runner'])]:
            outcome=run([node,*args],work/'frontend',240);outcome['name']=name;checks.append(outcome);update()
            if outcome['exit_code']:raise ValueError(name+' failed')
        if git(['diff','--name-only'],work).splitlines()!=[TARGET]:raise ValueError('Validation changed protected files')
        git(['add',TARGET],work);git(['-c','user.name=Darwin Research','-c','user.email=research@localhost','commit','-m','Propose measured-incident signal policy; human review required'],work)
        candidate=git(['rev-parse','HEAD'],work)
        update('READY_FOR_REVIEW',candidate_sha=candidate,reason='Restricted contracts and regression passed. Review the held-out result before any integration; insufficient evidence is not a win.')
        if git(['rev-parse','HEAD'],root)!=base:raise ValueError('Source changed; candidate retained without publication')
        if os.getenv('DARWIN_RESEARCH_CREATE_DRAFT_PR','false').lower()=='true':
            branch='darwin/research-'+job['id'][:12]
            base_branch=git(['branch','--show-current'],root)
            if not base_branch:raise ValueError('No review base branch')
            # Publication is an explicit local setting. Credentials stay with Git/gh, never the model.
            push=run(['git','-c','safe.directory='+str(root),'-c','credential.helper=','-c','credential.helper=!gh auth git-credential','push','origin',candidate+':refs/heads/'+branch],root,120)
            if push['exit_code']:raise ConnectionError('Candidate tested; GitHub publication failed')
            body=artifacts/'pr.md'
            body.write_text('Measured incident: '+str(pack['incident'].get('code'))+'\n\n'+str(proposal['hypothesis'])+
                '\n\nOnly the isolated research signal policy changes. Not integrated into active trading. No invented defect.\n\nValidation: restricted contracts, backend regression, TypeScript and build passed. Held-out recorded-market comparison: '+
                comparison['verdict']+'; net delta '+str(comparison['delta_net_usd'])+' USD. No future-live validation or profitability proof. Human review required.\n\nCandidate '+candidate,encoding='utf-8')
            remote=git(['remote','get-url','origin'],root)
            match=re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?',remote)
            if not match:raise ValueError('Unsupported publication remote')
            out=run(['gh','pr','create','--repo',match.group(1),'--draft','--base',base_branch,'--head',branch,'--title','Research candidate: '+str(pack['incident'].get('code'))+' signal policy','--body-file',str(body)],root,60)
            if out['exit_code']:raise ConnectionError('Candidate branch published; draft PR creation failed')
            url=out['stdout'].strip().splitlines()[-1]
            if not url.startswith('https://github.com/'):raise ValueError('Unexpected PR response')
            update(pr_url=url,reason='Draft PR published for human review; no integration or deployment.')

    except Exception as exc:update('PROVIDER_UNAVAILABLE' if isinstance(exc,ConnectionError) else 'REJECTED',reason=redacted(str(exc))[:1000])

if __name__=='__main__':
    code=Path(sys.argv[2]).read_text(encoding='utf-8-sig')
    if sys.argv[1]=='--contract':
        fn=safe_policy(code)
        for raw in (-1,-.5,0,.5,1):
            for spread in (0,.1,2,20):
                for flow in (-1,0,1):
                    for imbalance in (-1,0,1):
                        v=fn(raw,spread,flow,imbalance)
                        assert type(v) in (int,float) and math.isfinite(v) and abs(v)<=abs(raw) and v*raw>=0
        print('180 restricted signal contract cases passed')
    else:
        p=json.loads(Path(sys.argv[3]).read_text());print(json.dumps(replay(code,p['ticks'],p['genome'],p['notional'],p['fees'])))
