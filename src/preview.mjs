// Public snapshot explorer. No API, accounts, AI inference or company storage.
import {esc,MARKETS,createReport,reportMarkdown} from './engine.mjs';
import {t,getLanguage,setLanguage,registerCountries,productName,label} from './i18n.mjs';
import {worldFigure,marketTable} from './figures.mjs';
import {createViews} from './views.mjs';
import {icon} from './icons.mjs';

const state={product:'kimchi',market:'일본',channel:'web',period:60,view:'dashboard',reports:[],report:null,tableExpanded:false};
let data,geography,views;
const options=(rows,value)=>rows.map(([key,text])=>`<option value="${esc(key)}" ${key===value?'selected':''}>${esc(text)}</option>`).join('');
const selected=()=>data.products.find(p=>p.id===state.product);
const titles=()=>({dashboard:t('시장 데이터','Market explorer'),reports:t('샘플 보고서','Sample report'),data:t('데이터 라이브러리','Data library')});
const scope=()=>`<div class="preview-scope"><label>${t('제품','Product')}<select data-preview-product>${options(data.products.map(p=>[p.id,productName(p)]),state.product)}</select></label><label>${t('목표 시장','Target market')}<select data-preview-market>${options([...new Set([...MARKETS.map(m=>m.name),state.market])].map(m=>[m,label(m)]),state.market)}</select></label><button class="button primary" data-action="sample-report">${icon('file')}${t('샘플 보고서 보기','View sample report')}</button></div>`;
const agent={
  render:()=>`<section class="agent-workspace"><div class="agent-intro"><div class="agent-identity"><span class="agent-orb">${icon('spark')}</span><div><span class="eyebrow">FLAVO / OPEN RESEARCH</span><span>${t('우리 음식의 다음 가능성을 찾다.','Local flavors. New possibilities.')}</span></div></div><span class="badge">${data.snapshotDate}</span></div><div class="agent-masthead"><img src="./src/shutterstock_1867661479.jpg" alt="${t('다양한 사람들이 함께 나누는 한식 식탁','A colorful Korean table shared together')}"><span class="agent-image-note">LOCAL FLAVORS. SHARED POSSIBILITIES.</span></div><div class="agent-desk"><div class="agent-greeting"><span class="eyebrow">EXPLORE THE EVIDENCE</span><h1>${t('우리의 맛, 세계의 가능성.','A world of possibilities for your food.')}</h1><p>${t('데이터 속 근거를 만나고, 다음 시장을 그려보세요.','Find the evidence. Imagine your next market.')}</p></div>${scope()}<p class="preview-note">${t('실제 집계 데이터로 구성한 공개 데모입니다. 샘플 보고서는 AI 없이 브라우저에서 계산하며 기업 정보를 수집·저장하지 않습니다.','A public demo using real aggregate data. Sample reports are computed in your browser without AI or collection of company information.')}</p></div></section>`,
  bind:()=>{}
};

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
  document.querySelector('#app').innerHTML=`<aside class="sidebar" aria-label="${t('주 메뉴','Main navigation')}"><a class="brand" href="#dashboard" aria-label="FLAVO home"><img src="./src/9.png" alt="FLAVO"></a><div class="nav-label">PUBLIC RESEARCH</div><nav>${Object.entries(titles()).map(([id,title])=>`<a href="#${id}" ${id===state.view?'class="active" aria-current="page"':''}>${icon({dashboard:'globe',reports:'file',data:'database'}[id])}<span>${title}</span></a>`).join('')}</nav><div class="sidebar-bottom"><div class="agent-note"><span class="eyebrow">GROUNDED IN EVIDENCE</span><h3>${t('근거부터, 한 걸음씩.','One grounded step at a time.')}</h3><p>${t('사실과 가설을 구분하고<br>자료의 한계를 함께 읽습니다.','Separate facts from hypotheses.<br>Know the limits of each source.')}</p><a class="text-button" href="https://github.com/jellyfish040918/food_report">${t('프로젝트 보기','View project')} ↗</a></div></div></aside><div class="app-body"><header class="topbar"><div class="breadcrumbs"><button class="icon-button mobile-menu" data-action="menu" aria-label="${t('메뉴 열기','Open menu')}">${icon('menu')}</button><b>${titles()[state.view]}</b></div><div class="topbar-right"><span class="badge">PUBLIC DEMO</span><div class="language-switch" role="group" aria-label="${t('언어 선택','Language')}"><button data-language="ko" aria-pressed="${getLanguage()==='ko'}">한국어</button><button data-language="en" aria-pressed="${getLanguage()==='en'}">EN</button></div></div></header><div class="preview-banner" role="note"><b>${t('공개 데이터 데모','Public data demo')}</b><span>${t('시장 탐색과 샘플 보고서를 이용할 수 있습니다. AI Q&A·로그인·구독은 서비스 서버 연결 후 제공됩니다.','Explore market data and sample reports. AI Q&A, accounts and subscriptions require the service server.')}</span></div><main id="main" tabindex="-1"></main><footer class="footer"><span>FLAVO — Local roots. Global reach.</span><span>${t('데이터 스냅샷','Data snapshot')} ${data.snapshotDate}</span></footer></div>`;
  if(state.view==='reports')sample();
  views.render(state.view);
  if(state.view==='reports')document.querySelector('#main').insertAdjacentHTML('afterbegin',scope());
  window.scrollTo({top:0});
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
  if(el.dataset.language){setLanguage(el.dataset.language);render();return;}
  if(el.dataset.mapMarket){selectMap(el.dataset.mapMarket);return;}
  if(el.dataset.product){state.product=el.dataset.product;views.render('dashboard');document.querySelector('#market-evidence').scrollIntoView({block:'start'});return;}
  if(el.dataset.market){state.market=el.dataset.market;location.hash='reports';render();return;}
  if(el.dataset.evidence){document.getElementById(`evidence-${el.dataset.evidence}`)?.scrollIntoView({behavior:'smooth',block:'center'});return;}
  const action=el.dataset.action;
  if(['sample-report','new-report','regenerate-language'].includes(action)){location.hash='reports';render();}
  if(action==='back-reports'){location.hash='dashboard';}
  if(action==='menu')document.querySelector('.sidebar').classList.toggle('mobile-open');
  if(action==='expand-markets'){state.tableExpanded=!state.tableExpanded;views.render('dashboard');document.querySelector('#market-table').scrollIntoView({block:'center'});}
  if(action==='print')window.print();
  if(action==='download-report')download(`FLAVO_sample_${getLanguage()}.md`,reportMarkdown(state.report),'text/markdown;charset=utf-8');
  if(action==='download-data')download('flavo-public-snapshot.json',JSON.stringify(data,null,2),'application/json');
});
document.addEventListener('change',event=>{if(event.target.matches('[data-preview-product]'))state.product=event.target.value;else if(event.target.matches('[data-preview-market]'))state.market=event.target.value;else return;render();});
document.addEventListener('keydown',event=>{if(event.target.matches('svg [data-map-market]')&&['Enter',' '].includes(event.key)){event.preventDefault();selectMap(event.target.dataset.mapMarket);document.querySelector(`svg [data-map-market="${CSS.escape(state.market)}"]`)?.focus();}});
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
