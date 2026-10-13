import asyncio
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager,nullcontext
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import Settings,ROOT,PLANS
from .store import Store,Problem,digest,uid
from .auth import Identity,COOKIE,HASHER,email,password,text
from .billing import Billing
from .agent import Runner,validate_run
from .lease import WorkerLease

log=logging.getLogger('flavo.api')

async def raw_body(request,limit=60000):
    chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>limit:raise Problem(413,'body_limit','요청이 너무 큽니다.','Request body is too large.')
        chunks.append(chunk)
    return b''.join(chunks)
async def body(request):
    if request.headers.get('content-type','').split(';')[0]!='application/json':raise Problem(415,'json','JSON 요청이 필요합니다.','JSON content type is required.')
    try:
        value=json.loads(await raw_body(request),parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,UnicodeError):raise Problem(422,'json','요청 형식을 확인해 주세요.','Invalid JSON object.')

def create_app(settings=None):
    cfg=settings or Settings();cfg.validate();store=Store(cfg.database,operator_email=cfg.operator_email);auth=Identity(store,cfg);billing=Billing(store,cfg);runner=Runner(store,cfg)
    @asynccontextmanager
    async def lifespan(app):
        with WorkerLease(cfg.database) if cfg.run_worker else nullcontext():
            task=asyncio.create_task(runner.loop()) if cfg.run_worker else None
            app.state.worker_task=task
            try:yield
            finally:
                if task:task.cancel();await asyncio.gather(task,return_exceptions=True)
    app=FastAPI(title='FLAVO workspace API',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store,app.state.auth,app.state.billing,app.state.runner=store,auth,billing,runner

    @app.exception_handler(Problem)
    async def problem(request,error):return JSONResponse({'error':error.ko,'error_en':error.en,'code':error.code},status_code=error.status)
    @app.exception_handler(Exception)
    async def unknown(request,error):
        log.exception('Request failed: %s',request.state.request_id)
        return JSONResponse({'error':'요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.','error_en':'The request could not be completed. Please retry.','requestId':request.state.request_id},status_code=500)

    @app.middleware('http')
    async def boundary(request,call_next):
        request.state.request_id=uid();host=request.url.hostname
        allowed={urlparse(cfg.origin).hostname} if cfg.production else {'127.0.0.1','localhost','::1','testserver'}
        if cfg.production and cfg.railway and request.url.path == '/api/health' and request.method == 'GET':
            allowed.add('healthcheck.railway.app')
        if host not in allowed:return JSONResponse({'error':'허용되지 않은 호스트입니다.','error_en':'Host is not allowed.'},status_code=403)
        if request.url.path.startswith('/api/') and request.method not in ('GET','HEAD') and request.url.path!='/api/billing/webhook':
            origin=request.headers.get('origin','').rstrip('/');valid={cfg.origin} if cfg.production else {cfg.origin,str(request.base_url).rstrip('/')}
            if origin not in valid:return JSONResponse({'error':'허용되지 않은 요청 출처입니다.','error_en':'Origin is not allowed.'},status_code=403)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','X-Frame-Options':'DENY','X-Request-ID':request.state.request_id,'Permissions-Policy':'camera=(), microphone=(), geolocation=()','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"})
        if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        else:response.headers['Cache-Control']='no-cache'
        if cfg.production:response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        return response

    def clientkey(request,prefix):return prefix+':'+(request.client.host if request.client else 'unknown')
    def session_payload(identity):
        return {'authenticated':True,'user':{'id':identity['user'],'name':identity['name'],'email':identity['email']},'workspace':{'id':identity['workspace'],'name':identity['workspace_name'],'role':identity['role']},'csrf':identity['csrf'],'usage':store.entitlement(identity['workspace'],user=identity['user']),'billingEnabled':billing.enabled,'environment':'production' if cfg.production else 'development'}
    @app.get('/api/session')
    def session(request:Request):
        identity=auth.resolve(request,False)
        result=session_payload(identity) if identity else {'authenticated':False,'demoAvailable':not cfg.production}
        result['signupAvailable']=cfg.launch_mode == 'saas'
        result['launchMode']=cfg.launch_mode
        return result
    @app.post('/api/auth/demo')
    async def demo(request:Request):
        await body(request);store.throttle(clientkey(request,'demo'),20);identity=auth.demo();response=JSONResponse({'ok':True});auth.issue(identity,response);return response
    @app.post('/api/auth/register')
    async def register(request:Request):
        if cfg.launch_mode == 'private-pilot':raise Problem(403,'signup_closed','비공개 테스트 운영 중입니다. 발급받은 계정으로 로그인해 주세요.','Registration is closed during the private pilot. Sign in with your provisioned account.')
        store.throttle(clientkey(request,'signup'),5,3600);payload=await body(request);account=await asyncio.to_thread(auth.create,payload)
        if cfg.production:
            token=auth.token('verify',account,86400);await asyncio.to_thread(auth.mail,account['email'],'verify',token)
            return {'verificationRequired':True}
        response=JSONResponse({'ok':True});auth.issue(account,response);return response
    @app.post('/api/auth/login')
    async def login(request:Request):
        payload=await body(request);store.throttle(clientkey(request,'login'),20);store.throttle('login-email:'+str(payload.get('email','')).lower(),10)
        account=await asyncio.to_thread(auth.login,payload.get('email'),payload.get('password'));response=JSONResponse({'ok':True});auth.issue(account,response);return response
    @app.post('/api/auth/logout')
    async def logout(request:Request):
        auth.resolve(request);store.execute('DELETE FROM sessions WHERE hash=?',(digest(request.cookies.get(COOKIE,'')),));response=JSONResponse({'ok':True});response.delete_cookie(COOKIE,path='/');return response
    @app.post('/api/auth/verify')
    async def verify(request:Request):
        store.throttle(clientkey(request,'verify'),20);payload=await body(request)
        def operation(db,data):db.execute('UPDATE users SET verified=1 WHERE id=?',(data['user'],));return data
        account=auth.consume(payload.get('token'),'verify',operation);response=JSONResponse({'ok':True});auth.issue(account,response);return response
    @app.post('/api/auth/email')
    async def send_link(request:Request):
        if cfg.launch_mode == 'private-pilot':raise Problem(503,'email_unavailable','비공개 테스트 계정 복구는 운영자에게 문의해 주세요.','Contact the operator to recover your private pilot account.')
        store.throttle(clientkey(request,'email'),5,3600);payload=await body(request);address=email(payload.get('email'));purpose=payload.get('purpose')
        if purpose not in ('verify','reset'):raise Problem(422,'purpose','요청을 확인해 주세요.','Invalid request.')
        store.throttle('email:'+address,3,3600);row=store.one('SELECT id,verified FROM users WHERE email=?',(address,))
        if row and (purpose=='reset' or not row['verified']):
            membership=store.one('SELECT workspace FROM members WHERE user=?',(row['id'],));token=auth.token(purpose,{'user':row['id'],'workspace':membership['workspace']},3600)
            try:await asyncio.to_thread(auth.mail,address,purpose,token)
            except Problem:log.warning('Email delivery unavailable; request=%s',request.state.request_id)
        return {'ok':True}
    @app.post('/api/auth/reset')
    async def reset(request:Request):
        store.throttle(clientkey(request,'reset'),10);payload=await body(request);hashed=await asyncio.to_thread(HASHER.hash,password(payload.get('password')))
        def operation(db,data):
            db.execute('UPDATE users SET password=?,verified=1 WHERE id=?',(hashed,data['user']));db.execute('DELETE FROM sessions WHERE user=?',(data['user'],));db.execute("DELETE FROM tokens WHERE purpose='reset' AND json_extract(data,'$.user')=?",(data['user'],))
        auth.consume(payload.get('token'),'reset',operation);return {'ok':True}

    @app.get('/api/status')
    async def status(request:Request):
        auth.resolve(request)
        try:await runner.model.details();return {'status':'ready'}
        except Exception:return {'status':'offline'}
    @app.post('/api/jobs')
    async def create_job(request:Request):
        identity=auth.resolve(request);store.throttle('run:'+identity['workspace'],20,60)
        try:kind,payload=validate_run(await body(request))
        except (ValueError,TypeError,KeyError):raise Problem(422,'run_input','제품·시장·요청 내용을 확인해 주세요.','Check your product, market and request.')
        key=text(request.headers.get('Idempotency-Key'),16,100);return JSONResponse(store.enqueue(identity,kind,payload,key),status_code=202)
    @app.get('/api/jobs')
    def jobs(request:Request):return {'jobs':store.jobs(auth.resolve(request)['workspace'])}
    @app.get('/api/jobs/{id}')
    def job(id:str,request:Request):return store.job(auth.resolve(request)['workspace'],id)
    @app.post('/api/jobs/{id}/cancel')
    def cancel(id:str,request:Request):
        identity=auth.resolve(request);store.cancel(identity,id);return store.job(identity['workspace'],id)
    @app.post('/api/jobs/{id}/retry')
    def retry(id:str,request:Request):
        identity=auth.resolve(request);store.throttle('run:'+identity['workspace'],20,60);old=store.one('SELECT * FROM jobs WHERE workspace=? AND id=?',(identity['workspace'],id))
        if not old:raise Problem(404,'not_found','작업을 찾을 수 없습니다.','Run not found.')
        if old['status'] not in ('failed','cancelled'):raise Problem(409,'status','실패·취소된 작업만 재시도할 수 있습니다.','Only failed or cancelled runs can be retried.')
        return store.enqueue(identity,old['kind'],json.loads(old['payload']),text(request.headers.get('Idempotency-Key'),16,100))
    @app.get('/api/reports')
    def reports(request:Request):return {'reports':store.reports(auth.resolve(request)['workspace'])}
    @app.post('/api/reports/{id}/review')
    def review(id:str,request:Request):
        identity=auth.resolve(request)
        with store.tx() as db:
            exists=db.execute('SELECT id FROM reports WHERE id=? AND workspace=?',(id,identity['workspace'])).fetchone()
            if not exists:raise Problem(404,'not_found','보고서를 찾을 수 없습니다.','Report not found.')
            updated=db.execute('UPDATE reports SET reviewed_by=?,reviewed_at=? WHERE id=? AND workspace=? AND reviewed_at IS NULL',(identity['user'],time.time(),id,identity['workspace'])).rowcount
            if updated:store.audit(db,identity['workspace'],identity['user'],'report.reviewed',id)
        return {'ok':True}
    @app.get('/api/questions')
    def questions(request:Request):
        identity=auth.resolve(request);rows=store.all("SELECT payload,result,created FROM jobs WHERE workspace=? AND kind='ask' AND status='completed' ORDER BY created DESC LIMIT 30",(identity['workspace'],))
        return {'turns':[{'question':json.loads(r['payload'])['question'],'response':json.loads(r['result']),'createdAt':r['created']} for r in reversed(rows)]}
    @app.get('/api/workspace')
    def workspace(request:Request):
        identity=auth.resolve(request);wid=identity['workspace']
        return {'name':identity['workspace_name'],'role':identity['role'],'usage':store.entitlement(wid,user=identity['user']),'billingEnabled':billing.enabled,'emailEnabled':bool(cfg.smtp_host and cfg.mail_from),'members':store.all('SELECT u.name,u.email,m.role FROM members m JOIN users u ON u.id=m.user WHERE m.workspace=? ORDER BY m.role DESC',(wid,)),'audit':store.all('SELECT action,target,created FROM audit WHERE workspace=? ORDER BY id DESC LIMIT 25',(wid,)) if identity['role']=='owner' else [],'plans':[{'id':p,**limits,'configured':bool(cfg.prices.get(p))} for p,limits in PLANS.items() if p in ('starter','team')]}
    @app.post('/api/workspace/invite')
    async def invite(request:Request):
        identity=auth.resolve(request);auth.owner(identity);store.throttle('invite:'+identity['workspace'],5,3600);payload=await body(request);address=email(payload.get('email'));access=store.entitlement(identity['workspace'])
        if not access['active']:raise Problem(402,'plan','이용 기간을 확인해 주세요.','Your plan is inactive.')
        if store.one('SELECT count(*) n FROM members WHERE workspace=?',(identity['workspace'],))['n']>=access['seats']:raise Problem(402,'seats','요금제의 좌석 한도에 도달했습니다.','Your workspace seat allowance is full.')
        raw=auth.token('invite',{'workspace':identity['workspace'],'email':address},86400);await asyncio.to_thread(auth.mail,address,'invite',raw);return {'ok':True}
    @app.post('/api/workspace/accept')
    async def accept(request:Request):
        identity=auth.resolve(request);payload=await body(request)
        def operation(db,data):
            if identity['email']!=data['email']:raise Problem(403,'invite_email','초대받은 이메일 계정으로 로그인해 주세요.','Sign in with the invited email address.')
            access=store.entitlement(data['workspace'],db);count=db.execute('SELECT count(*) FROM members WHERE workspace=?',(data['workspace'],)).fetchone()[0]
            if not access['active'] or count>=access['seats']:raise Problem(402,'seats','좌석이나 이용 기간을 확인해 주세요.','No active seat is available.')
            db.execute("INSERT OR IGNORE INTO members VALUES(?,?,'member')",(data['workspace'],identity['user']));db.execute('UPDATE sessions SET workspace=? WHERE hash=?',(data['workspace'],identity['hash']));store.audit(db,data['workspace'],identity['user'],'member.joined')
        auth.consume(payload.get('token'),'invite',operation);return {'ok':True}
    @app.post('/api/workspace/remove-member')
    async def remove_member(request:Request):
        identity=auth.resolve(request);auth.owner(identity);payload=await body(request);address=email(payload.get('email'))
        with store.tx() as db:
            member=db.execute('SELECT m.user,m.role FROM members m JOIN users u ON u.id=m.user WHERE workspace=? AND u.email=?',(identity['workspace'],address)).fetchone()
            if not member or member['role']=='owner':raise Problem(409,'member','변경 가능한 멤버를 선택해 주세요.','Choose an existing non-owner member.')
            db.execute('DELETE FROM members WHERE workspace=? AND user=?',(identity['workspace'],member['user']))
            db.execute('DELETE FROM sessions WHERE workspace=? AND user=?',(identity['workspace'],member['user']))
            store.audit(db,identity['workspace'],identity['user'],'member.removed')
        return {'ok':True}
    @app.get('/api/workspaces')
    def workspaces(request:Request):return {'workspaces':store.all('SELECT w.id,w.name,m.role FROM workspaces w JOIN members m ON m.workspace=w.id WHERE m.user=?',(auth.resolve(request)['user'],))}
    @app.post('/api/workspaces/switch')
    async def switch(request:Request):
        identity=auth.resolve(request);payload=await body(request);wid=payload.get('workspace')
        if not isinstance(wid,str) or not store.one('SELECT 1 FROM members WHERE workspace=? AND user=?',(wid,identity['user'])):raise Problem(404,'not_found','워크스페이스를 찾을 수 없습니다.','Workspace not found.')
        store.execute('DELETE FROM sessions WHERE hash=?',(identity['hash'],));response=JSONResponse({'ok':True});auth.issue({'user':identity['user'],'workspace':wid},response);return response
    @app.post('/api/billing/checkout')
    async def checkout(request:Request):
        identity=auth.resolve(request);auth.owner(identity);store.throttle('billing:'+identity['workspace'],5,60);payload=await body(request)
        if store.entitlement(identity['workspace'])['plan']=='demo':raise Problem(409,'demo','데모에서는 결제를 실행하지 않습니다.','Checkout is disabled in the demo workspace.')
        return await asyncio.to_thread(billing.checkout,identity,payload.get('plan'))
    @app.post('/api/billing/portal')
    async def portal(request:Request):
        identity=auth.resolve(request);auth.owner(identity);store.throttle('billing:'+identity['workspace'],5,60);return await asyncio.to_thread(billing.portal,identity)
    @app.post('/api/billing/webhook')
    async def webhook(request:Request):return await asyncio.to_thread(billing.webhook,await raw_body(request,262144),request.headers.get('stripe-signature',''))
    @app.get('/api/health')
    def health():
        store.one('SELECT version FROM schema_version')
        task=getattr(app.state,'worker_task',None)
        if cfg.run_worker and (task is None or task.done()):raise Problem(503,'worker_unavailable','분석 작업 서비스 확인이 필요합니다.','Research worker is unavailable.')
        return {'status':'ok','service':'flavo'}
    @app.api_route('/api/{path:path}',methods=['GET','POST','PUT','DELETE','PATCH'])
    def not_found(path:str):raise Problem(404,'not_found','지원하지 않는 API입니다.','API endpoint not found.')
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='web')
    return app

app=create_app()
