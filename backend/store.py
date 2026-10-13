"""Single-node SQLite persistence. All customer reads require a workspace scope."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .config import PLANS

def uid(): return str(uuid.uuid4())
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def encode(value): return json.dumps(value,ensure_ascii=False,separators=(',',':'))

class Problem(Exception):
    def __init__(self,status,code,ko,en):
        self.status,self.code,self.ko,self.en=status,code,ko,en

class Store:
    def __init__(self,path,operator_email=''):
        self.operator_email=operator_email.strip().lower()
        self.path=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.tx() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,plan TEXT NOT NULL DEFAULT 'trial',created REAL NOT NULL,trial_end REAL NOT NULL,customer TEXT UNIQUE,subscription TEXT UNIQUE,billing_status TEXT NOT NULL DEFAULT 'trial',period_start REAL,period_end REAL,cancel_at_end INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS members(workspace TEXT NOT NULL REFERENCES workspaces(id),user TEXT NOT NULL REFERENCES users(id),role TEXT NOT NULL CHECK(role IN ('owner','member')),PRIMARY KEY(workspace,user));
            CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,user TEXT NOT NULL REFERENCES users(id),workspace TEXT NOT NULL REFERENCES workspaces(id),csrf TEXT NOT NULL,created REAL NOT NULL,last_seen REAL NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY,purpose TEXT NOT NULL,data TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,workspace TEXT NOT NULL REFERENCES workspaces(id),user TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,started REAL,finished REAL,result TEXT,error TEXT,idempotency TEXT NOT NULL,request_hash TEXT NOT NULL,cycle TEXT NOT NULL,charged INTEGER NOT NULL DEFAULT 0,UNIQUE(workspace,idempotency));
            CREATE INDEX IF NOT EXISTS jobs_scope ON jobs(workspace,created);
            CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,job TEXT NOT NULL REFERENCES jobs(id),stage TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,workspace TEXT NOT NULL REFERENCES workspaces(id),job TEXT UNIQUE NOT NULL REFERENCES jobs(id),document TEXT NOT NULL,reviewed_by TEXT REFERENCES users(id),reviewed_at REAL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,workspace TEXT,user TEXT,action TEXT NOT NULL,target TEXT,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY,start REAL NOT NULL,count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS stripe_events(id TEXT PRIMARY KEY,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS checkout_sessions(workspace TEXT PRIMARY KEY REFERENCES workspaces(id),id TEXT NOT NULL,url TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS checkout_intents(workspace TEXT PRIMARY KEY REFERENCES workspaces(id),plan TEXT NOT NULL,idempotency TEXT NOT NULL,expires REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS events_job ON events(job,id);
            CREATE INDEX IF NOT EXISTS reports_scope ON reports(workspace,created);
            CREATE INDEX IF NOT EXISTS audit_scope ON audit(workspace,id);
            ''')

    @contextmanager
    def tx(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=10000')
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def one(self,sql,args=()):
        with self.tx() as db:
            row=db.execute(sql,args).fetchone();return dict(row) if row else None
    def all(self,sql,args=()):
        with self.tx() as db:return [dict(r) for r in db.execute(sql,args)]
    def execute(self,sql,args=()):
        with self.tx() as db:return db.execute(sql,args).rowcount
    def audit(self,db,workspace,user,action,target=None):
        db.execute('INSERT INTO audit(workspace,user,action,target,created) VALUES(?,?,?,?,?)',(workspace,user,action,target,time.time()))
    def throttle(self,key,limit=10,window=600):
        key=digest(key);now=time.time()
        with self.tx() as db:
            row=db.execute('SELECT * FROM rate_limits WHERE key=?',(key,)).fetchone()
            count=1 if not row or row['start']<now-window else row['count']+1
            if count>limit:raise Problem(429,'rate_limit','요청이 많습니다. 잠시 후 다시 시도해 주세요.','Too many requests. Please try again later.')
            db.execute('INSERT OR REPLACE INTO rate_limits VALUES(?,?,?)',(key,now if count==1 else row['start'],count))

    def entitlement(self,workspace,db=None,*,user=None):
        w=dict(db.execute('SELECT * FROM workspaces WHERE id=?',(workspace,)).fetchone()) if db else self.one('SELECT * FROM workspaces WHERE id=?',(workspace,))
        now=time.time();plan=w['plan'];active=False
        if plan=='demo':active=True
        elif plan=='trial':active=w['trial_end']>now
        else:active=w['billing_status'] in ('active','trialing') and (w['period_end'] or 0)>now
        cap=PLANS.get(plan,PLANS['trial']);cycle='trial' if plan=='trial' else datetime.now(timezone.utc).strftime('%Y-%m')
        seat_sql='SELECT count(*) n FROM members WHERE workspace=?'
        seats_used=db.execute(seat_sql,(workspace,)).fetchone()['n'] if db else self.one(seat_sql,(workspace,))['n']
        over_seats=seats_used>cap['seats'];active=active and not over_seats
        # Only a server-designated, verified operator in a workspace they own.
        # A customer's owner role or client-supplied email grants no exemption.
        unlimited=False
        if self.operator_email and user:
            operator_sql="SELECT 1 FROM users u JOIN members m ON m.user=u.id WHERE u.id=? AND u.email=? AND u.verified=1 AND m.workspace=? AND m.role='owner'"
            args=(user,self.operator_email,workspace)
            unlimited=bool(db.execute(operator_sql,args).fetchone() if db else self.one(operator_sql,args))
        sql="SELECT count(*) n FROM jobs WHERE workspace=? AND cycle=? AND (charged=1 OR status IN ('queued','running','cancelling'))"
        args=(workspace,cycle)
        if unlimited:
            active=not over_seats;cycle='operator'
            # Operator runs remain auditable without consuming teammates' quota.
            sql="SELECT count(*) n FROM jobs WHERE workspace=? AND user=? AND (charged=1 OR status IN ('queued','running','cancelling'))"
            args=(workspace,user)
        used=db.execute(sql,args).fetchone()['n'] if db else self.one(sql,args)['n']
        return {'plan':plan,'active':active,'unlimited':unlimited,'limit':None if unlimited else cap['runs'],'used':used,'remaining':None if unlimited else max(0,cap['runs']-used),'seats':cap['seats'],'seatsUsed':seats_used,'overSeatLimit':over_seats,'cycle':cycle,'trialEnd':None if unlimited else w['trial_end'],'periodEnd':w['period_end'],'billingStatus':w['billing_status'],'cancelAtEnd':bool(w['cancel_at_end'])}

    def enqueue(self,identity,kind,payload,key):
        wid,user=identity['workspace'],identity['user'];now=time.time();body=encode(payload);fingerprint=digest(kind+body)
        with self.tx() as db:
            existing=db.execute('SELECT * FROM jobs WHERE workspace=? AND idempotency=?',(wid,key)).fetchone()
            if existing:
                if existing['request_hash']!=fingerprint:raise Problem(409,'idempotency_conflict','중복 요청 키의 내용이 다릅니다.','Idempotency key already used with different content.')
                return self.job_dict(existing)
            access=self.entitlement(wid,db,user=user)
            if not access['active'] or (not access['unlimited'] and access['remaining']<=0):raise Problem(402,'quota','이용 기간이나 분석 한도를 확인해 주세요.','Your plan has expired or the run allowance is exhausted.')
            if db.execute("SELECT count(*) FROM jobs WHERE workspace=? AND status IN ('queued','running','cancelling')",(wid,)).fetchone()[0]>=3:raise Problem(429,'queue_limit','워크스페이스에서 최대 3개 작업까지 대기할 수 있습니다.','Up to three active or queued runs per workspace.')
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','cancelling')").fetchone()[0]>=50:raise Problem(503,'queue_full','분석 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요.','The analysis queue is full. Try again shortly.')
            id=uid();db.execute('INSERT INTO jobs(id,workspace,user,kind,payload,status,stage,created,updated,idempotency,request_hash,cycle) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(id,wid,user,kind,body,'queued','queued',now,now,key,fingerprint,access['cycle']))
            db.execute('INSERT INTO events(job,stage,created) VALUES(?,?,?)',(id,'queued',now));self.audit(db,wid,user,'run.created',id)
            return self.job_dict(db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())

    @staticmethod
    def job_dict(row,detail=False):
        r=dict(row);out={k:r[k] for k in ['id','kind','status','stage','created','updated','started','finished','error']};p=json.loads(r['payload']);out['label']=p.get('profile',{}).get('company') or p.get('question','');out['language']=p.get('language') or p.get('profile',{}).get('language','ko')
        out['mode']=p.get('mode','ai')
        if detail:out['result']=json.loads(r['result']) if r['result'] else None
        return out
    def job(self,workspace,id,detail=True):
        r=self.one('SELECT * FROM jobs WHERE workspace=? AND id=?',(workspace,id))
        if not r:raise Problem(404,'not_found','작업을 찾을 수 없습니다.','Run not found.')
        out=self.job_dict(r,detail);out['events']=self.all('SELECT stage,created FROM events WHERE job=? ORDER BY id',(id,));return out
    def jobs(self,workspace):
        jobs=[self.job_dict(r) for r in self.all('SELECT * FROM jobs WHERE workspace=? ORDER BY created DESC LIMIT 100',(workspace,))]
        if jobs:
            ids=[job['id'] for job in jobs];events=self.all('SELECT job,stage,created FROM events WHERE job IN ('+','.join('?' for _ in ids)+') ORDER BY id',ids)
            for job in jobs:job['events']=[{'stage':e['stage'],'created':e['created']} for e in events if e['job']==job['id']]
        return jobs
    def cancel(self,identity,id):
        with self.tx() as db:
            r=db.execute('SELECT * FROM jobs WHERE id=? AND workspace=?',(id,identity['workspace'])).fetchone()
            if not r:raise Problem(404,'not_found','작업을 찾을 수 없습니다.','Run not found.')
            if r['status'] in ('queued','running'):
                status='cancelled' if r['status']=='queued' else 'cancelling';now=time.time()
                db.execute('UPDATE jobs SET status=?,stage=?,updated=?,finished=? WHERE id=?',(status,status,now,now if status=='cancelled' else None,id));db.execute('INSERT INTO events(job,stage,created) VALUES(?,?,?)',(id,status,now));self.audit(db,identity['workspace'],identity['user'],'run.cancelled',id)
    def claim(self):
        with self.tx() as db:
            r=db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not r:return None
            now=time.time();db.execute("UPDATE jobs SET status='running',stage='planning',started=?,updated=? WHERE id=?",(now,now,r['id']));db.execute('INSERT INTO events(job,stage,created) VALUES(?,?,?)',(r['id'],'planning',now));return dict(r)
    def stage(self,id,stage):
        with self.tx() as db:
            changed=db.execute("UPDATE jobs SET stage=?,updated=? WHERE id=? AND status='running'",(stage,time.time(),id)).rowcount
            if changed:db.execute('INSERT INTO events(job,stage,created) VALUES(?,?,?)',(id,stage,time.time()))
    def finish(self,job,result=None,error=None):
        now=time.time()
        with self.tx() as db:
            row=db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()
            status='cancelled' if row['status'] in ('cancelling','cancelled') else 'failed' if error else 'completed'
            charged=int(status=='completed' and (job['kind']=='report' or result.get('mode')=='ai'))
            saved=encode(result) if status=='completed' else None
            db.execute('UPDATE jobs SET status=?,stage=?,result=?,error=?,charged=?,updated=?,finished=? WHERE id=?',(status,status,saved,error if status=='failed' else None,charged,now,now,job['id']))
            db.execute('INSERT INTO events(job,stage,created) VALUES(?,?,?)',(job['id'],status,now))
            if status=='completed' and job['kind']=='report':
                result['id']=job['id'];db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?)',(job['id'],job['workspace'],job['id'],encode(result),None,None,now))
                db.execute('UPDATE jobs SET result=? WHERE id=?',(encode(result),job['id']))
            self.audit(db,job['workspace'],job['user'],'run.'+status,job['id'])
    def recover(self):
        with self.tx() as db:
            rows=db.execute("SELECT id,status FROM jobs WHERE status IN ('running','cancelling')").fetchall()
            for r in rows:
                status='cancelled' if r['status']=='cancelling' else 'failed'
                db.execute('UPDATE jobs SET status=?,stage=?,error=?,finished=?,updated=? WHERE id=?',(status,status,'worker_restarted',time.time(),time.time(),r['id']));db.execute('INSERT INTO events(job,stage,created) VALUES(?,?,?)',(r['id'],status,time.time()))
    def cleanup(self):
        now=time.time()
        with self.tx() as db:
            db.execute('DELETE FROM tokens WHERE expires<?',(now,))
            db.execute('DELETE FROM sessions WHERE expires<? OR last_seen<?',(now,now-7200))
            db.execute('DELETE FROM rate_limits WHERE start<?',(now-86400,))
            db.execute('DELETE FROM checkout_sessions WHERE expires<?',(now,))
            db.execute('DELETE FROM checkout_intents WHERE expires<?',(now,))
    def reports(self,workspace):
        return [{**json.loads(r['document']),'reviewedAt':r['reviewed_at'],'reviewedBy':r['reviewer']} for r in self.all('SELECT reports.document,reports.reviewed_at,users.name AS reviewer FROM reports LEFT JOIN users ON users.id=reports.reviewed_by WHERE reports.workspace=? ORDER BY reports.created DESC',(workspace,))]
