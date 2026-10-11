import {esc} from './engine.mjs';
import {t,number as n} from './i18n.mjs';
import {icon} from './icons.mjs';

// Shared presentation for the public site and authenticated research workspace.
// Figures describe dataset coverage, never customers, market size or sales.
export function researchHero(data,{workspace=false}={}){
  return `<section class="research-hero ${workspace?'research-hero-compact':''}" aria-labelledby="research-heading">
    <div class="research-copy"><span class="eyebrow">FOOD MARKET INTELLIGENCE</span>
      <h1 id="research-heading">${t('해외 시장을 묻고,<br><span>다음 전략을 만드세요.</span>','Ask about your market.<br><span>Build your next move.</span>')}</h1>
      <p>${t('AI 채팅으로 근거 있는 답변을 찾고, 기업 맞춤 보고서로 정리하세요. <br>식품 기업의 시장 탐색부터 현지화 실행 계획까지.','Find answers with evidence. Turn them into a report for your business. <br>Food market research, from your first question to a localization plan.')}</p>
      <div class="research-actions"><a class="button primary" href="#ask">${t('AI 채팅 시작','Start AI chat')}${icon('arrow')}</a><button class="button secondary" data-action="new-report">${t('맞춤 보고서 작성','Create a custom report')}</button></div>
      <span class="research-caption">${t('검색 트렌드 · 레시피 · 소비자 리뷰','Search trends · Recipes · Consumer reviews')}</span>
    </div>
    <figure class="research-visual"><img src="./src/shutterstock_1867661479.jpg" width="2048" height="1093" fetchpriority="high" alt="${t('다양한 한식을 함께 나누는 식탁 일러스트','An illustrated table of Korean food shared together')}">
      <figcaption><span class="eyebrow">LOCAL ROOTS. GLOBAL REACH.</span><strong>${t('우리의 맛, 더 넓은 세상으로.','Local flavors. Wider possibilities.')}</strong><span class="brand-handnote">${t('가능성을 발견하는 새로운 시선','A fresh perspective on possibility')}</span></figcaption>
    </figure>
  </section>
  <section class="research-coverage" aria-label="${t('수록 데이터 범위','Dataset coverage')}"><div class="coverage-intro"><span class="eyebrow">THE RESEARCH FOUNDATION</span><p>${t('다양한 근거를<br>하나의 관점으로.','Different sources.<br>A connected perspective.')}</p></div>${[
    ['6',t('데이터 소스','Data sources'),t('검색 · 레시피 · 리뷰 외','Search, recipes, reviews & more')],
    [String(data.products.length),t('식품 키워드','Food keywords'),t('한식 중심 분석 범위','A Korean food research focus')],
    [n(data.trendFileCount),t('검색 데이터 파일','Search data files'),'Google Trends · CSV'],
    [n(data.foodcom.count),t('Food.com 리뷰','Food.com reviews'),'2000–2020']
  ].map(([value,title,note])=>`<div><strong>${esc(value)}</strong><b>${title}</b><small>${note}</small></div>`).join('')}</section>`;
}

export function researchUseCases(){
  return `<section class="research-use-cases" aria-label="${t('리서치 활용 분야','Research applications')}">${[
    ['01',t('진출 시장 탐색','Market discovery'),t('국가별 검색 관심도와 시간에 따른 변화를 비교합니다.','Compare regional search interest and how it changes over time.')],
    ['02',t('현지화 방향 검토','Localization research'),t('레시피와 리뷰에서 제품 실험에 필요한 단서를 찾습니다.','Find signals in recipes and reviews to inform product experiments.')],
    ['03',t('실행 계획 수립','Strategy planning'),t('관측 사실과 가설을 구분해 90일 실행 계획으로 정리합니다.','Separate facts from hypotheses in a 90-day action plan.')]
  ].map(([i,title,body])=>`<article><span>${i}</span><div><h2>${title}</h2><p>${body}</p></div></article>`).join('')}</section>`;
}
