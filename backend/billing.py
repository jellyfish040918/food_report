"""Stripe hosted Checkout/Portal. Entitlements only come from verified webhooks."""
import hashlib
import hmac
import json
import threading
import time
import httpx
from .store import Problem

class Billing:
    def __init__(self,store,settings):self.store,self.settings,self.lock=store,settings,threading.Lock()
    @property
    def enabled(self):return bool(self.settings.stripe_key and self.settings.stripe_webhook and all(self.settings.prices.values()))
    def request(self,method,path,data=None,key=None):
        headers={'Authorization':'Bearer '+self.settings.stripe_key,'Stripe-Version':'2025-06-30.basil'}
        if key:headers['Idempotency-Key']=key
        try:
            response=httpx.request(method,'https://api.stripe.com/v1/'+path,headers=headers,**({'params':data} if method=='GET' else {'data':data}),timeout=20)
            response.raise_for_status();return response.json()
        except (httpx.HTTPError,ValueError):raise Problem(503,'billing_unavailable','결제 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.','Billing is temporarily unavailable. Try again shortly.')
    def checkout(self,identity,plan):
        if not self.enabled:raise Problem(503,'billing_not_configured','운영자의 결제 설정이 아직 완료되지 않았습니다.','Subscription checkout is not configured yet.')
        if not isinstance(plan,str) or plan not in self.settings.prices:raise Problem(422,'plan','지원하는 요금제를 선택해 주세요.','Choose a supported plan.')
        with self.lock:
            wid=identity['workspace'];w=self.store.one('SELECT * FROM workspaces WHERE id=?',(wid,))
            if w['subscription'] and w['billing_status'] not in ('canceled','incomplete_expired'):
                raise Problem(409,'existing_subscription','이미 연결된 구독이 있습니다. 구독 관리에서 변경해 주세요.','Manage your existing subscription in the billing portal.')
            intent=self.store.one('SELECT * FROM checkout_intents WHERE workspace=? AND expires>?',(wid,time.time()))
            if intent and intent['plan']!=plan:
                raise Problem(409,'checkout_pending','진행 중인 결제의 요금제를 먼저 완료하거나 결제 링크 만료 후 다시 선택해 주세요.','An existing checkout is pending. Complete that plan or wait for its link to expire before choosing another.')
            pending=self.store.one('SELECT * FROM checkout_sessions WHERE workspace=? AND expires>?',(wid,time.time()))
            if pending:return {'url':pending['url']}
            customer=w['customer']
            if not customer:
                customer=self.request('POST','customers',{'email':identity['email'],'name':w['name'],'metadata[workspace]':wid},'customer-'+wid)['id']
                self.store.execute('UPDATE workspaces SET customer=? WHERE id=?',(customer,wid))
            if not intent:
                # A paid checkout can precede its webhook. Do not create another
                # subscription just because the local entitlement has not caught up.
                subscriptions=self.request('GET','subscriptions',{'customer':customer,'status':'all','limit':'100'})
                if subscriptions.get('has_more'):
                    raise Problem(409,'billing_history','구독 관리에서 결제 상태를 확인해 주세요.','Check your subscriptions in the billing portal.')
                if any(s.get('status') not in ('canceled','incomplete_expired') for s in subscriptions.get('data',[])):
                    raise Problem(409,'existing_subscription','이미 연결된 구독이 있습니다. 결제 반영을 기다리거나 구독 관리에서 확인해 주세요.','A subscription already exists. Wait for synchronization or open the billing portal.')
                bucket=int(time.time()//1800)
                intent={'idempotency':'checkout-'+wid+'-'+plan+'-'+str(bucket),'expires':(bucket+2)*1800}
                self.store.execute('INSERT OR REPLACE INTO checkout_intents VALUES(?,?,?,?)',(wid,plan,intent['idempotency'],intent['expires']))
            result=self.request('POST','checkout/sessions',{'mode':'subscription','customer':customer,'client_reference_id':wid,'line_items[0][price]':self.settings.prices[plan],'line_items[0][quantity]':'1','subscription_data[metadata][workspace]':wid,'metadata[workspace]':wid,'success_url':self.settings.origin+'/#workspace','cancel_url':self.settings.origin+'/#workspace','expires_at':str(int(intent['expires']))},intent['idempotency'])
            self.store.execute('INSERT OR REPLACE INTO checkout_sessions VALUES(?,?,?,?)',(wid,result['id'],result['url'],result['expires_at']))
            return {'url':result['url']}
    def portal(self,identity):
        if not self.enabled:raise Problem(503,'billing_not_configured','결제 설정이 필요합니다.','Billing is not configured.')
        row=self.store.one('SELECT customer FROM workspaces WHERE id=?',(identity['workspace'],))
        if not row['customer']:raise Problem(409,'no_customer','연결된 구독이 없습니다.','No billing customer is linked yet.')
        return {'url':self.request('POST','billing_portal/sessions',{'customer':row['customer'],'return_url':self.settings.origin+'/#workspace'})['url']}
    def verify(self,body,header):
        if not self.settings.stripe_webhook:raise Problem(503,'webhook_not_configured','결제 이벤트 수신이 설정되지 않았습니다.','Webhook not configured.')
        try:
            pairs=[v.split('=',1) for v in header.split(',')];timestamp=next(int(v) for k,v in pairs if k=='t');signatures=[v for k,v in pairs if k=='v1']
            expected=hmac.new(self.settings.stripe_webhook.encode(),str(timestamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
            if abs(time.time()-timestamp)>300 or not any(hmac.compare_digest(expected,s) for s in signatures):raise ValueError()
            event=json.loads(body)
            if not isinstance(event,dict) or not isinstance(event.get('id'),str) or not isinstance(event.get('type'),str):raise ValueError()
            return event
        except (ValueError,StopIteration,TypeError):raise Problem(400,'signature','결제 이벤트 서명을 확인할 수 없습니다.','Invalid or expired webhook signature.')
    def webhook(self,body,header):
        event=self.verify(body,header)
        with self.lock:
            if self.store.one('SELECT id FROM stripe_events WHERE id=?',(event['id'],)):return {'received':True}
            obj=event.get('data',{}).get('object',{});kind=event['type'];subscription=None
            if kind in ('customer.subscription.created','customer.subscription.updated','customer.subscription.deleted'):subscription=obj.get('id')
            elif kind=='checkout.session.completed':subscription=obj.get('subscription')
            if subscription:
                if not isinstance(subscription,str) or not subscription.startswith('sub_'):raise Problem(400,'subscription','구독 식별자가 올바르지 않습니다.','Invalid subscription.')
                # Fetch current state, so delayed/out-of-order deliveries cannot restore stale access.
                current=self.request('GET','subscriptions/'+subscription);wid=current.get('metadata',{}).get('workspace');customer=current.get('customer')
                row=self.store.one('SELECT * FROM workspaces WHERE id=? AND customer=?',(wid,customer))
                if row:
                    items=current.get('items',{}).get('data',[]);item=items[0] if len(items)==1 else {};price=item.get('price',{}).get('id');plan=next((p for p,id in self.settings.prices.items() if id and id==price),None)
                    status=current.get('status','unknown');period_start=item.get('current_period_start',current.get('current_period_start',0));period_end=item.get('current_period_end',current.get('current_period_end',0))
                    if not plan or item.get('quantity')!=1:status='unsupported';plan='starter'
                    if row['subscription'] in (None,subscription) or row['billing_status'] in ('canceled','incomplete_expired'):
                        with self.store.tx() as db:
                            db.execute('UPDATE workspaces SET subscription=?,plan=?,billing_status=?,period_start=?,period_end=?,cancel_at_end=? WHERE id=?',(subscription,plan,status,period_start,period_end,int(bool(current.get('cancel_at_period_end'))),wid))
                            db.execute('DELETE FROM checkout_sessions WHERE workspace=?',(wid,));db.execute('DELETE FROM checkout_intents WHERE workspace=?',(wid,));self.store.audit(db,wid,None,'billing.synchronized',event['id'])
            self.store.execute('INSERT OR IGNORE INTO stripe_events VALUES(?,?)',(event['id'],time.time()))
        return {'received':True}
