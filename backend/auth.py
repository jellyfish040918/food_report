import hmac
import json
import re
import secrets
import smtplib
import ssl
import sqlite3
import time
from email.message import EmailMessage
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from .store import Problem,uid,digest,encode

HASHER=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=1)
DUMMY=HASHER.hash(secrets.token_urlsafe(32))
COOKIE='flavo_session'

def text(value,low=1,high=100):
    if not isinstance(value,str) or not low<=len(value.strip())<=high:raise Problem(422,'input','입력 내용과 길이를 확인해 주세요.','Check the required fields and their length.')
    return value.strip()
def email(value):
    value=text(value,3,254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise Problem(422,'email','올바른 이메일 주소를 입력해 주세요.','Enter a valid email address.')
    return value
def password(value):
    if not isinstance(value,str) or not 12<=len(value)<=128:raise Problem(422,'password','비밀번호는 12–128자로 입력해 주세요.','Use a password of 12–128 characters.')
    return value

class Identity:
    def __init__(self,store,settings):self.store,self.settings=store,settings
    def create(self,payload):
        name,company=text(payload.get('name')),text(payload.get('company'));address=email(payload.get('email'));hashed=HASHER.hash(password(payload.get('password')));user,wid,now=uid(),uid(),time.time()
        try:
            with self.store.tx() as db:
                db.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',(user,address,name,hashed,int(not self.settings.production),now))
                db.execute('INSERT INTO workspaces(id,name,created,trial_end) VALUES(?,?,?,?)',(wid,company,now,now+14*86400))
                db.execute('INSERT INTO members VALUES(?,?,?)',(wid,user,'owner'));self.store.audit(db,wid,user,'workspace.created')
        except sqlite3.IntegrityError:raise Problem(409,'account','계정이 이미 있으면 로그인하거나 비밀번호를 재설정해 주세요.','If an account exists, sign in or reset its password.')
        return {'user':user,'workspace':wid,'email':address}
    def login(self,address,secret):
        address=email(address);secret=password(secret);row=self.store.one('SELECT * FROM users WHERE email=?',(address,))
        try:valid=HASHER.verify(row['password'] if row else DUMMY,secret)
        except (VerificationError,InvalidHashError):valid=False
        if not row or not valid:raise Problem(401,'credentials','이메일 또는 비밀번호를 확인해 주세요.','Email or password is incorrect.')
        if not row['verified']:raise Problem(403,'verify_email','이메일 인증을 먼저 완료해 주세요.','Verify your email before signing in.')
        if HASHER.check_needs_rehash(row['password']):self.store.execute('UPDATE users SET password=? WHERE id=?',(HASHER.hash(secret),row['id']))
        membership=self.store.one('SELECT workspace FROM members WHERE user=? ORDER BY rowid LIMIT 1',(row['id'],))
        return {'user':row['id'],'workspace':membership['workspace']}
    def issue(self,identity,response):
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32);now=time.time()
        with self.store.tx() as db:
            db.execute('DELETE FROM sessions WHERE expires<? OR last_seen<?',(now,now-7200))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',(digest(token),identity['user'],identity['workspace'],csrf,now,now,now+86400))
            self.store.audit(db,identity['workspace'],identity['user'],'session.created')
        response.set_cookie(COOKIE,token,max_age=86400,httponly=True,secure=self.settings.production,samesite='strict',path='/')
    def resolve(self,request,required=True):
        token=request.cookies.get(COOKIE,'');row=self.store.one('SELECT s.*,m.role,u.name,u.email,u.verified,w.name workspace_name FROM sessions s JOIN users u ON u.id=s.user JOIN members m ON m.user=s.user AND m.workspace=s.workspace JOIN workspaces w ON w.id=s.workspace WHERE s.hash=?',(digest(token),)) if token else None
        now=time.time()
        if not row or row['expires']<now or row['last_seen']<now-7200 or not row['verified'] or (self.settings.production and row['email']=='demo@flavo.local'):
            if required:raise Problem(401,'auth','로그인이 필요합니다.','Please sign in.')
            return None
        if request.method not in ('GET','HEAD') and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),row['csrf']):raise Problem(403,'csrf','세션을 새로고침해 주세요.','Refresh your session and try again.')
        self.store.execute('UPDATE sessions SET last_seen=? WHERE hash=?',(now,row['hash']));return row
    @staticmethod
    def owner(identity):
        if identity['role']!='owner':raise Problem(403,'owner','워크스페이스 관리자만 사용할 수 있습니다.','Only the workspace owner can perform this action.')
    def token(self,purpose,data,seconds=3600):
        raw=secrets.token_urlsafe(32);self.store.execute('INSERT INTO tokens VALUES(?,?,?,?)',(digest(raw),purpose,encode(data),time.time()+seconds));return raw
    def consume(self,raw,purpose,operation):
        raw=text(raw,20,200)
        with self.store.tx() as db:
            row=db.execute('SELECT * FROM tokens WHERE hash=? AND purpose=? AND expires>?',(digest(raw),purpose,time.time())).fetchone()
            if not row:raise Problem(400,'token','링크가 만료되었거나 이미 사용되었습니다.','The link has expired or was already used.')
            result=operation(db,json.loads(row['data']));db.execute('DELETE FROM tokens WHERE hash=?',(digest(raw),));return result
    def mail(self,address,purpose,raw):
        if not self.settings.smtp_host:raise Problem(503,'email_unavailable','이메일 발송 설정이 필요합니다. 관리자에게 문의해 주세요.','Email delivery is not configured. Contact the administrator.')
        url=self.settings.origin+'/#'+purpose+'='+raw
        msg=EmailMessage();msg['From']=self.settings.mail_from;msg['To']=address;msg['Subject']='FLAVO · '+{'verify':'Verify your email / 이메일 인증','reset':'Reset your password / 비밀번호 재설정','invite':'Workspace invitation / 워크스페이스 초대'}[purpose]
        msg.set_content(f'FLAVO\n\nOpen this one-time link / 아래 일회용 링크를 열어주세요:\n{url}\n\nIf you did not request this, ignore this message. 요청하지 않았다면 무시해 주세요.\n')
        try:
            with smtplib.SMTP(self.settings.smtp_host,self.settings.smtp_port,timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if self.settings.smtp_user:smtp.login(self.settings.smtp_user,self.settings.smtp_password)
                smtp.send_message(msg)
        except (OSError,smtplib.SMTPException):raise Problem(503,'email_delivery','메일을 보내지 못했습니다. 잠시 후 다시 요청해 주세요.','Email delivery failed. Please retry shortly.')
    def demo(self):
        if self.settings.production:raise Problem(404,'not_found','지원하지 않는 요청입니다.','Not found.')
        row=self.store.one("SELECT id FROM users WHERE email='demo@flavo.local'")
        if not row:
            account=self.create({'name':'Local workspace','company':'FLAVO Studio','email':'demo@flavo.local','password':secrets.token_urlsafe(32)})
            self.store.execute("UPDATE workspaces SET plan='demo' WHERE id=?",(account['workspace'],));return account
        return {'user':row['id'],'workspace':self.store.one('SELECT workspace FROM members WHERE user=?',(row['id'],))['workspace']}
