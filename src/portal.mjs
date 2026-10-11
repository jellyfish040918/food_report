// Public links transfer users to the same-origin, authenticated service.
// Never send credentials or company briefs to a configurable cross-origin API.
import {esc} from './engine.mjs';
import {t,getLanguage} from './i18n.mjs';
import {icon} from './icons.mjs';

export const SERVICE_VIEWS=['ask','new-report','login','register','workspace'];
export function serviceOrigin(value){
  if(!value)return '';
  try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash||u.pathname!=='/'||!u.hostname.includes('.')||/^(localhost|127\.|0\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/i.test(u.hostname)||u.hostname.endsWith('.github.io'))return '';return u.origin;}catch{return '';}
}
export function serviceLink(origin,view,language=getLanguage()){
  const base=serviceOrigin(origin);
  if(!base||!SERVICE_VIEWS.includes(view))return '';
  const url=new URL(base);url.searchParams.set('start',view);url.searchParams.set('lang',language==='en'?'en':'ko');url.hash=['login','register'].includes(view)?view:view==='new-report'?'reports':view;return url.href;
}
export async function loadServiceConfig(){
  try{const response=await fetch(new URL('./generated/site-config.json',import.meta.url),{cache:'no-store'});if(!response.ok)return {appUrl:''};const data=await response.json();return {appUrl:serviceOrigin(data.appUrl)};}catch{return {appUrl:''};}
}
export function serviceEntry(view,config){
  const isReport=view==='new-report',isAccount=['login','register','workspace'].includes(view);
  const title=isReport?t('기업 맞춤 보고서 작성','Create a company strategy report'):isAccount?t('기업 워크스페이스','Your company workspace'):t('근거를 확인하는 AI 채팅','AI chat, grounded in evidence');
  const description=isReport?t('기업의 제품, 목표 시장과 사업 과제를 입력하면 시장 근거·현지화 가설·90일 실행 계획을 하나의 보고서로 정리합니다.','Turn your product, target market and business brief into evidence, localization hypotheses and a 90-day plan.'):isAccount?t('기업별로 분리된 공간에서 보고서, 질문 기록과 팀의 분석 사용량을 관리합니다.','Manage reports, research conversations and team usage in your company’s workspace.'):t('식품과 해외 시장에 대해 질문하고, 연결된 데이터의 수치·출처·해석 한계가 포함된 답변을 확인하세요.','Ask about food and overseas markets. Review answers with figures, sources and the limits of the evidence.');
  const url=serviceLink(config.appUrl,view);
  const steps=isReport?[t('기업·제품·시장 입력','Define your company, product and market'),t('데이터 근거 조회와 전략 초안 작성','Retrieve evidence and draft the strategy'),t('출처 검토 후 PDF·Markdown 내보내기','Review sources and export PDF or Markdown')]:isAccount?[t('이메일 인증으로 계정 생성','Create an account with email verification'),t('기업별 보고서와 분석 기록 보관','Keep research within your company'),t('팀원 초대와 구독 관리','Invite your team and manage your subscription')]:[t('제품과 시장을 선택하고 질문','Choose a product and market, then ask'),t('모델이 연결된 근거로 설명 작성','Receive an explanation grounded in connected data'),t('출처를 열어 확인하고 보고서로 연결','Inspect sources and continue to a report')];
  const localView=isAccount?'dashboard':view;
  const localUrl=`http://127.0.0.1:4175/?start=${localView}&lang=${getLanguage()}#${isReport?'reports':localView}`;
  return `<section class="service-entry"><div class="service-entry-copy"><a class="text-button" href="#dashboard">← ${t('서비스 소개','Overview')}</a><span class="eyebrow">FLAVO WORKSPACE / ${isReport?'REPORT BUILDER':isAccount?'TEAM WORKSPACE':'RESEARCH CHAT'}</span><h1>${title}</h1><p>${description}</p><ol class="service-entry-steps">${steps.map((s,i)=>`<li><span>0${i+1}</span>${s}</li>`).join('')}</ol><div class="entry-related"><a href="${isReport?'#ask':'#new-report'}">${isReport?t('AI 채팅 살펴보기','Explore AI chat'):t('보고서 작성 살펴보기','Explore report builder')} ${icon('arrow')}</a><a href="#reports">${t('샘플 보고서 확인','View a sample report')} ${icon('arrow')}</a></div></div><aside class="service-launch" aria-labelledby="launch-title"><span class="launch-symbol">${icon(isReport?'file':isAccount?'grid':'chat')}</span><span class="eyebrow">${url?'YOUR RESEARCH WORKSPACE':'CLOUD WORKSPACE'}</span><h2 id="launch-title">${url?t('워크스페이스에서 시작하세요.','Continue to your workspace.'):t('클라우드 서비스 연결 대기','Cloud service not connected yet')}</h2><p>${url?t('로그인 후 선택한 기능으로 이어집니다. 질문과 보고서는 기업 워크스페이스에 저장됩니다.','Sign in to continue to this feature. Your conversations and reports are stored in your company workspace.'):t('AI 채팅과 맞춤 보고서 기능은 구현되어 있습니다. 현재 공개 홈페이지에는 운영 서버가 연결되지 않아 여기서 AI 분석을 실행할 수 없습니다.','AI chat and custom reports are implemented. This public website does not yet have a connected production server, so AI analysis cannot run here.')}</p>${url?`<a class="button primary" href="${esc(url)}">${t('서비스 시작하기','Open workspace')}${icon('arrow')}</a>`:`<div class="launch-status">${icon('clock')}${t('운영 서버 설정 후 활성화','Available after production server setup')}</div><a class="button secondary" href="#reports">${t('샘플 보고서 먼저 보기','Explore a sample report')}</a><details class="local-launch"><summary>${t('현재 개발 PC에서 실제 AI 기능 사용','Use the actual AI service on this development PC')}</summary><p>${t('FLAVO 서버와 분석 모델을 실행 중인 PC에서만 동작합니다. 다른 방문자에게 제공되는 클라우드 서비스가 아닙니다.','Works only on the computer running the FLAVO server and model. This is not a cloud service available to other visitors.')}</p><a href="${localUrl}" class="text-button">${t('현재 PC의 서비스 열기','Open this computer’s service')} ↗</a></details>`}<div class="launch-boundary">${icon('database')}<span>${t('공개 사이트는 로그인 정보나 기업 과제를 수집하지 않습니다. 실제 분석은 연결된 서비스에서 진행합니다.','This public site does not collect credentials or company briefs. Analysis takes place in the connected service.')}</span></div></aside></section>`;
}
