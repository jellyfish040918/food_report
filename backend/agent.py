"""Deterministic evidence tools + bounded model drafting + durable state transitions."""
import asyncio
import json
import logging
import shutil
import time
import httpx
import qa
import server as legacy
from .config import ROOT
from .store import Problem
from .auth import text
from .provenance import receipt

log=logging.getLogger('flavo.agent')

def validate_run(payload):
    if not isinstance(payload,dict):raise ValueError('Request must be an object.')
    kind=payload.get('kind');data=qa.snapshot()
    if kind=='ask':return kind,qa.validate_question(payload.get('input'),data)
    if kind!='report':raise ValueError('Unknown run kind.')
    raw=payload.get('input',{})
    if not isinstance(raw,dict):raise ValueError('Invalid report input.')
    p=raw.get('profile',{})
    if not isinstance(p,dict):raise ValueError('Invalid profile.')
    profile={k:text(p.get(k),1,100) for k in ['company','product','market','format','channel']};profile['goal']=p.get('goal','');profile['language']=p.get('language','ko')
    if not isinstance(profile['goal'],str) or len(profile['goal'])>1000 or profile['language'] not in ('ko','en'):raise ValueError('Invalid goal or language.')
    if profile['product'] not in {p['id'] for p in data['products']}:raise ValueError('Unknown product.')
    mode=raw.get('mode','ai')
    if mode not in ('ai','evidence'):raise ValueError('Unknown generation mode.')
    return kind,{'profile':profile,'mode':mode}

async def canonical(action,profile,ai=None):
    node=shutil.which('node')
    if not node:raise RuntimeError('node_unavailable')
    process=await asyncio.create_subprocess_exec(node,str(ROOT/'scripts/report_worker.mjs'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=ROOT)
    try:
        output,errors=await asyncio.wait_for(process.communicate(json.dumps({'action':action,'profile':profile,'ai':ai},ensure_ascii=False).encode()),15)
        if process.returncode or len(output)>1000000:raise RuntimeError('evidence_tool_failed')
        return json.loads(output)
    except BaseException:
        if process.returncode is None:process.kill();await process.wait()
        raise

class Model:
    def __init__(self,settings):self.settings=settings
    async def details(self):
        async with httpx.AsyncClient(timeout=8,trust_env=False) as client:
            result=await client.get(self.settings.ollama+'/api/tags');result.raise_for_status()
            match=next((m for m in result.json().get('models',[]) if m.get('name')==self.settings.model and not m.get('remote_host') and not m.get('remote_model')),None)
            if not match:raise RuntimeError('model_unavailable')
            result=await client.post(self.settings.ollama+'/api/show',json={'model':self.settings.model});result.raise_for_status();details=result.json()
            if 'completion' not in details.get('capabilities',[]) or details.get('remote_host'):raise RuntimeError('model_unavailable')
            return details
    async def generate(self,context,kind='report'):
        details=await self.details();payload=legacy.chat_options(self.settings.model,details,context)
        payload['keep_alive']=self.settings.model_keep_alive
        payload['options']['num_ctx']=self.settings.model_context
        if kind=='ask':
            payload['format']=qa.answer_schema(context);payload['options']['num_predict']=3500
            system=qa.QA_SYSTEM.replace('한국어로 간결하게 답하세요.','Respond concisely in English only.') if context.get('language')=='en' else qa.QA_SYSTEM
            payload['messages']=[{'role':'system','content':system},{'role':'user','content':json.dumps(context,ensure_ascii=False)}]
        async with httpx.AsyncClient(timeout=httpx.Timeout(300,connect=10),trust_env=False) as client:
            response=await client.post(self.settings.ollama+'/api/chat',json=payload);response.raise_for_status();result=response.json()
        if result.get('done_reason')=='length':raise RuntimeError('output_truncated')
        return json.loads(result['message']['content'])

class Runner:
    def __init__(self,store,settings,model=None):self.store,self.settings,self.model=store,settings,model or Model(settings)
    async def process(self,job):
        payload=json.loads(job['payload']);id=job['id'];self.store.stage(id,'retrieving')
        if job['kind']=='report':
            profile=payload['profile'];context=await canonical('context',profile);self.store.stage(id,'evidence_ready')
            ai=None
            if payload['mode']=='ai':
                self.store.stage(id,'drafting');ai=await self.model.generate(context);self.store.stage(id,'validating');legacy.validate_output(ai)
            self.store.stage(id,'composing');report=await canonical('report',profile,ai)
            report['provenance']=receipt(context,report,id,'report',ai is not None)
            return report
        context=qa.retrieve(qa.snapshot(),payload);self.store.stage(id,'evidence_ready')
        if not context['evidence']:
            answer=qa.data_answer(context)
            answer['provenance']=receipt(context,answer,id,'ask',False)
            return answer
        try:
            self.store.stage(id,'drafting');answer=await self.model.generate({**context,'previousQuestions':payload['history']},'ask');self.store.stage(id,'validating');answer=qa.validate_answer(answer,context)
            result={**context,**answer,'mode':'ai','limits':list(dict.fromkeys(context['limits']+answer['limits'])),'notice':'Source-grounded AI explanation. Review the evidence and limitations.' if payload['language']=='en' else '근거를 바탕으로 작성한 AI 설명입니다. 출처와 해석 한계를 검토해 주세요.'}
            result['provenance']=receipt(context,result,id,'ask',True)
            return result
        except (httpx.HTTPError,RuntimeError,ValueError,KeyError,TypeError):
            answer=qa.data_answer(context,'AI 설명 생성 또는 출처 번호 검증에 실패하여 집계된 사실을 직접 표시합니다.')
            answer['provenance']=receipt(context,answer,id,'ask',False)
            return answer
    async def run_one(self,job):
        task=asyncio.create_task(self.process(job));start=time.monotonic()
        try:
            while not task.done():
                await asyncio.wait([task],timeout=.5)
                row=self.store.one('SELECT status FROM jobs WHERE id=?',(job['id'],))
                if row['status']=='cancelling':task.cancel();await asyncio.gather(task,return_exceptions=True);self.store.finish(job,error='cancelled');return
                if time.monotonic()-start>330:task.cancel();await asyncio.gather(task,return_exceptions=True);self.store.finish(job,error='timeout');return
            result=task.result();self.store.finish(job,result=result)
        except asyncio.CancelledError:
            task.cancel();await asyncio.gather(task,return_exceptions=True);self.store.finish(job,error='worker_restarted');raise
        except Exception:
            log.exception('Agent run failed: %s',job['id']);self.store.finish(job,error='generation_failed')
    async def loop(self):
        self.store.recover();last_cleanup=0
        while True:
            if time.monotonic()-last_cleanup>3600:self.store.cleanup();last_cleanup=time.monotonic()
            job=self.store.claim()
            if job:await self.run_one(job)
            else:await asyncio.sleep(.5)
