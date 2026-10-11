// Public snapshot explorer. No API, accounts, AI inference or company storage.
import {esc,MARKETS,createReport,reportMarkdown} from './engine.mjs';
import {t,getLanguage,setLanguage,registerCountries,productName,label} from './i18n.mjs';
import {worldFigure,marketTable} from './figures.mjs';
import {createViews} from './views.mjs';
import {icon} from './icons.mjs';
import {researchHero,researchUseCases} from './presentation.mjs';

const state={product:'kimchi',market:'일본',channel:'web',period:60,view:'dashboard',reports:[],report:null,tableExpanded:false};
let data,geography,views;
const options=(rows,value)=>rows.map(([key,text])=>`<option value="${esc(key)}" ${key===value?'selected':''}>${esc(text)}</option>`).join('');
const selected=()=>data.products.find(p=>p.id===state.product);
const titles=()=>({dashboard:t('시장 데이터','Market explorer'),reports:t('샘플 보고서','Sample report'),data:t('데이터 라이브러리','Data library')});
const scope=()=>`<div class="preview-scope"><label>${t('제품','Product')}<select data-preview-product>${options(data.products.map(p=>[p.id,productName(p)]),state.product)}</select></label><label>${t('목표 시장','Target market')}<select data-preview-market>${options([...new Set([...MARKETS.map(m=>m.name),state.market])].map(m=>[m,label(m)]),state.market)}</select></label><button class="button primary" data-action="sample-report">${icon('file')}${t('샘플 보고서 보기','View sample report')}</button></div>`;
const agent={render:()=>researchHero(data)+researchUseCases(),afterResearch:()=>scopePanel(),bind:()=>{}};
const scopePanel=()=>`<section class="preview-scope-panel" aria-label="${t('샘플 보고서 분석 범위','Sample report scope')}"><div><span class="eyebrow">BUILD YOUR SAMPLE</span><h2>${t('제품과 시장으로 시작하는 전략.','A strategy for your product and market.')}</h2><p>${t('제품과 목표 시장을 선택해 그래프와 실행 계획이 담긴 샘플 보고서를 확인하세요.','Choose a product and market to explore a sample with charts and an action plan.')}</p></div>${scope()}</section>`;

function sample(){
  state.report=createReport(data,{company:t('FLAVO 공개 샘플','FLAVO public sample'),product:state.product,market:state.market,format:'냉장 완제품',channel:'현지 아시안 마켓',goal:'',language:getLanguage()});
}
function render(){
  if(location.hash==='#main'){document.querySelector('#main')?.focus();return;}
  const view=location.hash.slice(1)||'dashboard';
  state.view=Object.hasOwn(titles(),view)?view:'dashboard';
  document.documentElement.lang=getLanguage();
  document.title=`${titles()[state.view]} · FLAVO ${t('공개 데모','Public demo')}`;
  document.querySelector('.skip-link').textContent=t('본문으로 이동','Skip to content');
  document.body.classList.add('public-site');
  document.querySelector('#app').innerHTML=`<header class="corporate-header"><div class="corporate-header-inner"><a class="corporate-brand" href="#dashboard" aria-label="FLAVO home"><img src="./src/9.png" width="80" height="64" alt="FLAVO"><span>FOOD MARKET<br>INTELLIGENCE</span></a><nav id="public-navigation" class="corporate-nav" aria-label="${t('주 메뉴','Main navigation')}">${[['dashboard',t('서비스 소개','Overview')],['market-evidence',t('시장 탐색','Market explorer')],['reports',t('샘플 보고서','Sample report')],['data',t('데이터 출처','Data sources')]].map(([id,title])=>`<a href="#${id}" ${id===(location.hash.slice(1)||'dashboard')?'aria-current="page"':''}>${title}</a>`).join('')}</nav><div class="corporate-header-actions"><div class="language-switch" role="group" aria-label="${t('언어 선택','Language')}"><button data-language="ko" aria-pressed="${getLanguage()==='ko'}">KO</button><button data-language="en" aria-pressed="${getLanguage()==='en'}">EN</button></div><a href="#reports" class="button primary header-cta">${t('보고서 살펴보기','Explore reports')}${icon('arrow')}</a><button class="icon-button public-menu" data-action="menu" aria-controls="public-navigation" aria-expanded="false" aria-label="${t('메뉴 열기','Open menu')}">${icon('menu')}</button></div></div></header><div class="public-announcement"><span>${t('공개 리서치 데모','PUBLIC RESEARCH DEMO')}</span><p>${t('집계 데이터로 시장을 탐색하고 샘플 보고서를 확인하세요.','Explore aggregate market data and sample strategy reports.')}</p><a href="#data">${t('수록 데이터 확인','View data coverage')} ↗</a></div><div class="public-content"><main id="main" tabindex="-1"></main></div><footer class="corporate-footer"><div class="corporate-footer-top"><div><b>FLAVO</b><p>${t('식품 기업의 다음 시장을 위한 리서치.','Research for your next food market.')}</p><span>LOCAL ROOTS. GLOBAL REACH.</span></div><nav aria-label="${t('하단 메뉴','Footer navigation')}"><a href="#market-evidence">${t('시장 탐색','Market explorer')}</a><a href="#reports">${t('샘플 보고서','Sample report')}</a><a href="#data">${t('데이터 출처와 범위','Data sources & coverage')}</a><a href="https://github.com/jellyfish040918/food_report">${t('프로젝트','Project')} ↗</a></nav></div><div class="corporate-footer-bottom"><p>${t('공개 데모의 샘플 보고서는 집계 데이터와 고정된 계획 틀로 구성됩니다. AI 분석·기업 계정·구독 기능은 서비스 서버 연결 후 제공됩니다.','Public sample reports use aggregate data and a fixed planning template. AI analysis, company accounts and subscriptions require the service server.')}</p><span>${t('데이터 기준','Snapshot')} ${data.snapshotDate}</span></div></footer>`;
  if(state.view==='reports')sample();
  views.render(state.view);
  if(state.view==='reports')document.querySelector('#main').insertAdjacentHTML('afterbegin',scopePanel());
  if(location.hash==='#market-evidence')document.querySelector('#market-evidence')?.scrollIntoView({block:'start'});else window.scrollTo({top:0});
}
function selectMap(market){
  state.market=market;
  document.querySelector('#map-view').innerHTML=worldFigure(selected(),state.channel,geography,market);
  document.querySelector('#market-table').innerHTML=marketTable(selected(),state.channel,market,{limit:state.tableExpanded?Infinity:8});
  document.querySelectorAll('[data-preview-market]').forEach(select=>{if(![...select.options].some(o=>o.value===market))select.add(new Option(label(market),market));select.value=market;});
}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.addEventListener('click',event=>{
  const el=event.target.closest('button,a,[data-map-market]');if(!el)return;
  if(el.matches('a[href^="#"]')){document.querySelector('#public-navigation')?.classList.remove('is-open');document.querySelector('.public-menu')?.setAttribute('aria-expanded','false');}
  if(el.dataset.language){setLanguage(el.dataset.language);render();return;}
  if(el.dataset.mapMarket){selectMap(el.dataset.mapMarket);return;}
  if(el.dataset.product){state.product=el.dataset.product;views.render('dashboard');document.querySelector('#market-evidence').scrollIntoView({block:'start'});return;}
  if(el.dataset.market){state.market=el.dataset.market;location.hash='reports';render();return;}
  if(el.dataset.evidence){document.getElementById(`evidence-${el.dataset.evidence}`)?.scrollIntoView({behavior:'smooth',block:'center'});return;}
  const action=el.dataset.action;
  if(['sample-report','new-report','regenerate-language'].includes(action)){location.hash='reports';render();}
  if(action==='back-reports'){location.hash='dashboard';}
  if(action==='menu'){const open=document.querySelector('#public-navigation').classList.toggle('is-open');el.setAttribute('aria-expanded',String(open));}
  if(action==='expand-markets'){state.tableExpanded=!state.tableExpanded;views.render('dashboard');document.querySelector('#market-table').scrollIntoView({block:'center'});}
  if(action==='print')window.print();
  if(action==='download-report')download(`FLAVO_sample_${getLanguage()}.md`,reportMarkdown(state.report),'text/markdown;charset=utf-8');
  if(action==='download-data')download('flavo-public-snapshot.json',JSON.stringify(data,null,2),'application/json');
});
document.addEventListener('change',event=>{if(event.target.matches('[data-preview-product]'))state.product=event.target.value;else if(event.target.matches('[data-preview-market]'))state.market=event.target.value;else return;render();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('#public-navigation.is-open')){document.querySelector('#public-navigation').classList.remove('is-open');const menu=document.querySelector('.public-menu');menu.setAttribute('aria-expanded','false');menu.focus();}if(event.target.matches('svg [data-map-market]')&&['Enter',' '].includes(event.key)){event.preventDefault();selectMap(event.target.dataset.mapMarket);document.querySelector(`svg [data-map-market="${CSS.escape(state.market)}"]`)?.focus();}});
window.addEventListener('hashchange',()=>{if(views)render();});
window.addEventListener('beforeprint',()=>document.querySelectorAll('.report-document details').forEach(d=>{d.dataset.printOpen=String(d.open);d.open=true;}));
window.addEventListener('afterprint',()=>document.querySelectorAll('.report-document details').forEach(d=>d.open=d.dataset.printOpen==='true'));
async function bootstrap(){
  try{
    const responses=await Promise.all([fetch(new URL('./generated/data.json',import.meta.url)),fetch(new URL('./geo/world.json',import.meta.url))]);
    if(responses.some(r=>!r.ok))throw new Error(t('집계 자료를 불러오지 못했습니다.','Could not load the snapshot.'));
    [data,geography]=await Promise.all(responses.map(r=>r.json()));registerCountries(geography.countries);
    views=createViews({data,geography,state,options,agent,publicPreview:true});render();
  }catch(error){document.querySelector('#app').innerHTML=`<div class="boot"><h1>${t('자료 연결을 확인해 주세요.','Check the data connection.')}</h1><p>${esc(error.message)}</p><a class="button primary" href="./">${t('다시 불러오기','Reload')}</a></div>`;}
}
bootstrap();
