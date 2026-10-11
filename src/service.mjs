import {t} from './i18n.mjs';
export const stageLabel=stage=>({queued:t('대기 중','Queued'),planning:t('요청 확인','Planning'),retrieving:t('자료 조회','Retrieving evidence'),evidence_ready:t('근거 연결 완료','Evidence connected'),drafting:t('AI 전략 작성','AI drafting'),validating:t('응답·출처 검사','Validating references'),composing:t('보고서 구성','Composing report'),completed:t('완료','Completed'),failed:t('실패','Failed'),cancelled:t('취소됨','Cancelled'),cancelling:t('취소 중','Cancelling')})[stage]||stage;
export const errorLabel=code=>({generation_failed:t('분석 엔진 또는 응답 검증에 문제가 생겼습니다. 다시 시도해 주세요.','The analysis engine or response validation failed. Please retry.'),timeout:t('분석 시간이 초과되었습니다.','The run exceeded its time limit.'),worker_restarted:t('서버가 재시작되어 중단됐습니다. 다시 시도할 수 있습니다.','The server restarted. You can retry this run.')})[code]||t('작업을 완료하지 못했습니다.','The run could not be completed.');
export class WorkspaceService{
  session=null;
  async api(path,{method='GET',body,key,signal}={}){
    const response=await fetch(path,{method,credentials:'same-origin',signal,headers:{...(body!==undefined?{'Content-Type':'application/json'}:{}),...(this.session?.csrf?{'X-CSRF-Token':this.session.csrf}:{}),...(key?{'Idempotency-Key':key}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})});
    let data;try{data=await response.json();}catch{throw new Error(t('FLAVO 서버를 시작하거나 연결을 확인해 주세요.','Start the FLAVO server or check your connection.'));}
    if(!response.ok){const error=new Error(t(data.error,data.error_en)||t('요청을 처리하지 못했습니다.','Request failed.'));error.code=data.code;error.status=response.status;if(response.status===401&&this.session){this.session=null;window.dispatchEvent(new Event('flavo-session-expired'));}throw error;}return data;
  }
  async init(){this.session=await this.api('/api/session');if(!this.session.authenticated&&this.session.demoAvailable&&!/^#(login|register|verify=|reset=|invite=)/.test(location.hash)){await this.api('/api/auth/demo',{method:'POST',body:{}});this.session=await this.api('/api/session');}return this.session.authenticated;}
  async refresh(){this.session=await this.api('/api/session');if(!this.session.authenticated){this.session=null;window.dispatchEvent(new Event('flavo-session-expired'));throw new Error(t('다시 로그인해 주세요.','Please sign in again.'));}return this.session;}
  create(kind,input,key=crypto.randomUUID()){return this.api('/api/jobs',{method:'POST',body:{kind,input},key});}
  cancel(id){return this.api(`/api/jobs/${encodeURIComponent(id)}/cancel`,{method:'POST',body:{}});}
  async watch(id,onProgress=()=>{},signal){
    while(true){if(signal?.aborted)throw new DOMException('Aborted','AbortError');const job=await this.api(`/api/jobs/${encodeURIComponent(id)}`,{signal});onProgress(job);if(job.status==='completed')return job;if(['failed','cancelled'].includes(job.status)){const error=new Error(job.status==='cancelled'?t('작업을 취소했습니다.','Run cancelled.'):errorLabel(job.error));error.code=job.status;throw error;}await new Promise(resolve=>setTimeout(resolve,1500));}
  }
  async ask(payload,signal,progress){let id;const abort=()=>{if(id)this.cancel(id).catch(()=>{});};signal?.addEventListener('abort',abort,{once:true});try{if(signal?.aborted)throw new DOMException('Aborted','AbortError');const job=await this.create('ask',payload);id=job.id;if(signal?.aborted){abort();throw new DOMException('Aborted','AbortError');}return (await this.watch(id,progress,signal)).result;}finally{signal?.removeEventListener('abort',abort);}}
}
