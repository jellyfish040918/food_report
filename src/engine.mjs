import {englishEvidence,englishReport,englishMarkdown} from './report-en.mjs';
import {englishLabel,productsEn} from './i18n.mjs';
export const fmt = (n, digits = 0) => new Intl.NumberFormat('ko-KR', { maximumFractionDigits: digits }).format(n);
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const mean = rows => rows.length ? rows.reduce((sum, x) => sum + x.value, 0) / rows.length : null;

export function trendStats(product, channel = 'web') {
  const rows = (product.channels[channel]?.series || []).filter(x => !x.partial).sort((a, b) => a.date.localeCompare(b.date));
  const recent = rows.slice(-12), previous = rows.slice(-24, -12);
  const current = mean(recent), prior = mean(previous);
  const sparse = rows.length > 0 && rows.filter(x => x.value > 0).length / rows.length < .5;
  const valid = product.eligible && !sparse && recent.length === 12 && previous.length === 12 && prior > 0;
  return { rows, current, prior, growth: valid ? (current - prior) / prior * 100 : null, sparse, valid, start: recent[0]?.date, end: recent.at(-1)?.date };
}

export const MARKETS = [
  { name: '미국', code: 'US', cuisine: 'southern_us', cuisineLabel: '미국 남부 요리', flag: '🇺🇸' },
  { name: '일본', code: 'JP', cuisine: 'japanese', cuisineLabel: '일본 요리', flag: '🇯🇵' },
  { name: '싱가포르', code: 'SG', cuisine: null, flag: '🇸🇬' },
  { name: '베트남', code: 'VN', cuisine: 'vietnamese', cuisineLabel: '베트남 요리', flag: '🇻🇳' },
  { name: '영국', code: 'GB', cuisine: 'british', cuisineLabel: '영국 요리', flag: '🇬🇧' },
  { name: '오스트레일리아', code: 'AU', cuisine: null, flag: '🇦🇺' },
  { name: '캐나다', code: 'CA', cuisine: null, flag: '🇨🇦' },
  { name: '필리핀', code: 'PH', cuisine: 'filipino', cuisineLabel: '필리핀 요리', flag: '🇵🇭' },
  { name: '태국', code: 'TH', cuisine: 'thai', cuisineLabel: '태국 요리', flag: '🇹🇭' },
  { name: '독일', code: 'DE', cuisine: null, flag: '🇩🇪' },
  { name: '말레이시아', code: 'MY', cuisine: null, flag: '🇲🇾' },
];
export const marketInfo = name => MARKETS.find(x => x.name === name) || { name, code: 'GLOBAL', flag: '🌐', cuisine: null };

export function evidenceFor(data, profile) {
  const product = data.products.find(x => x.id === profile.product);
  if (!product) throw new Error('지원하는 제품을 선택해 주세요.');
  const stats = trendStats(product);
  const regions = (product.channels.web?.regions || []).filter(x => x.name !== '대한민국').sort((a, b) => b.value - a.value);
  const region = regions.find(x => x.name === profile.market);
  const market = marketInfo(profile.market);
  const cuisine = market.cuisine ? data.ingredients.cuisines[market.cuisine] : null;
  const food = data.foodcom.products[profile.product];
  const mentions = Object.entries(food.mentions).filter(([,count]) => count > 0).sort((a,b) => b[1]-a[1]);
  const facts = [
    { id: 'E1', title: '글로벌 검색 관심도', text: stats.current === null ? '해당 검색어의 시계열이 없습니다.' : `${product.name} 검색어의 최근 12개월 평균 지수는 ${fmt(stats.current, 1)}입니다.${stats.growth === null ? '유효한 전년 비교 성장률을 산출할 수 없습니다.' : ` 직전 12개월 대비 ${stats.growth >= 0 ? '+' : ''}${fmt(stats.growth, 1)}%입니다.`}`, source: product.channels.web?.sources.series, caution: '전 세계 검색 상대지수입니다. 특정 국가 성장률이나 시장 규모가 아닙니다.' },
    { id: 'E2', title: `${profile.market}의 검색 관심도`, text: region ? `${profile.market}의 지역 상대지수는 ${region.value}/100입니다. 같은 검색어의 수록 해외 지역 ${regions.length}곳 중 공동 ${1 + regions.filter(r => r.value > region.value).length}위입니다.` : `${profile.market}의 해당 검색어 지역 관측값이 없습니다. 수요가 없다는 의미는 아닙니다.`, source: product.channels.web?.sources.regions, caution: '각 지역의 전체 검색 대비 비중을 정규화한 값입니다. 국가 간 절대 검색량 비교가 아닙니다.' },
    { id: 'E3', title: '요리 재료의 현지 접점', text: cuisine ? `${market.cuisineLabel} 레시피 ${fmt(cuisine.count)}건에서 ${cuisine.ingredients.slice(0, 3).map(x => `${x.name}(${x.percent}%)`).join(', ')}가 나타납니다.` : `${profile.market}와 직접 대응하는 요리 재료 표본은 없습니다. 현지 인터뷰와 메뉴 조사가 필요합니다.`, source: data.ingredients.source, caution: '레시피 등장 빈도이며 소비자 선호 조사 결과가 아닙니다. 미국 표본은 남부 요리에 한정됩니다.' },
    { id: 'E4', title: '리뷰에서 확인할 구매 경험', text: `음식점 리뷰 ${fmt(data.reviews.count)}건 중 가격 키워드가 ${fmt(data.reviews.mentions['가격'] || 0)}건, 식감 키워드가 ${fmt(data.reviews.mentions['식감'] || 0)}건 등장합니다.`, source: data.reviews.source, caution: '전체 리뷰의 영어 단어 등장 수입니다. 감성 분석 또는 목표 국가 소비자 결과가 아닙니다.' },
    { id: 'E5', title: `${product.name} 레시피의 사용 맥락`, text: `Food.com 전체 레시피 ${fmt(data.recipes.count)}건 중 ${product.name} 검색 규칙에 해당하는 레시피는 ${fmt(food.recipeCount)}건입니다.${food.ingredients.length ? ` 자주 등장한 재료는 ${food.ingredients.slice(0,3).map(x=>`${x.name}(${fmt(x.count)}건)`).join(', ')}입니다.` : '관련 재료 표본이 없습니다.'}`, source: data.foodcom.sources.recipes, caution: data.foodcom.method },
    { id: 'E6', title: `${product.name} 레시피와 연결된 리뷰`, text: `Food.com의 ${Object.keys(data.foodcom.overall.yearCounts)[0]}–${Object.keys(data.foodcom.overall.yearCounts).at(-1)}년 작성 리뷰 ${fmt(data.foodcom.count)}건을 읽고 RecipeId로 연결했습니다. ${product.name} 표본의 리뷰는 ${fmt(food.reviewCount)}건이며, 리뷰가 있는 레시피는 ${fmt(food.reviewedRecipeCount)}건입니다. ${food.meanRating === null ? '1–5점 범위의 유효 평점이 없습니다.' : `유효 평점 ${fmt(food.ratedCount)}건의 평균은 ${fmt(food.meanRating,2)}/5점입니다.`}`, source: data.foodcom.sources.reviews, caution: `${data.foodcom.reviewMethod} 리뷰와 레시피별 집계 평점의 작성 시점은 다를 수 있습니다.` },
    { id: 'E7', title: `${product.name} 리뷰의 현지화 실험 단서`, text: mentions.length ? `${product.name} 관련 리뷰 ${fmt(food.reviewCount)}건 중 ${mentions.slice(0,4).map(([name,count])=>`${name} 키워드가 ${fmt(count)}건(${fmt(count/food.reviewCount*100,1)}%)`).join(', ')} 등장합니다. 여러 키워드가 한 리뷰에 함께 등장할 수 있습니다.` : `${product.name} 표본에 해당 영어 키워드를 포함한 리뷰가 없습니다. 제품 표본을 확대하거나 직접 인터뷰해야 합니다.`, source: data.foodcom.sources.reviews, caution: data.foodcom.reviewMethod },
    { id: 'E8', title: '전체 취향 표본의 탐색적 분포', text: `FlavorSense 유효 취향 ${fmt(data.flavors.valid)}건 중 단맛 ${fmt(data.flavors.tastes.Sweet || 0)}건, 매운맛 ${fmt(data.flavors.tastes.Spicy || 0)}건입니다. 시식 설계에서 비교할 맛의 범주를 탐색하는 보조 자료입니다.`, source: data.flavors.source, caution: data.flavors.limitation },
  ];
  const result = { product, stats, regions, region, market, cuisine, food, facts };
  if(profile.language==='en')result.facts=englishEvidence(data,profile,result);
  return result;
}

export function createReport(data, profile, ai = null, model = null) {
  const e = evidenceFor(data, profile);
  const plan = [
    { period: '01–30일', title: '현지 가설 검증', action: `${profile.market} 타깃 고객을 대상으로 ${e.product.name} 맛·용량·조리 편의성 인터뷰와 시식 평가를 진행합니다.`, metric: '시식 반응, 거부 이유, 구매 의향을 같은 질문으로 기록' },
    { period: '31–60일', title: '제품과 채널 테스트', action: `${profile.channel}에서 테스트할 소규모 제품안과 상세페이지를 준비합니다. 원가·물류·포장을 포함한 가격별 손익표를 만듭니다.`, metric: '클릭 대비 구매 전환, 단위당 공헌이익, 재구매 의향 비교' },
    { period: '61–90일', title: '확장 여부 결정', action: '테스트 판매와 고객 의견을 검토해 우선 제품을 좁힙니다. 목표에 미달하면 맛 또는 채널을 수정한 뒤 다시 검증합니다.', metric: '사전에 정한 손익 기준과 고객 평가를 함께 검토' },
  ];
  const localization = [
    { title: '맛과 식감', evidenceIds: ['E3', 'E7'], hypothesis: e.cuisine ? `${e.market.cuisineLabel}의 자주 쓰이는 재료와 제품 리뷰의 키워드를 현지 셰프 인터뷰의 출발점으로 사용하세요. 기존 맛과 조정한 맛을 함께 비교합니다.` : '확인된 현지 맛 선호 데이터가 없습니다. 제품 리뷰의 키워드는 질문 설계에 활용하고 기본맛과 변형맛을 소규모 블라인드 시식으로 비교하세요.', experiment: '기본 제품과 맛을 조정한 제품을 비교하고 구매 의향과 거부 이유를 기록합니다.' },
    { title: '패키지와 사용 장면', evidenceIds: ['E5', 'E6', 'E7'], hypothesis: `${profile.format} 형태에 맞춰 현지 언어의 조리법과 1회 사용 장면을 테스트하세요.`, experiment: '조리 영상이 있는 제품 설명과 일반 설명의 이해도·구매 반응을 비교합니다.' },
    { title: '첫 유통 채널', evidenceIds: ['E2'], hypothesis: `우선 시험 채널은 ${profile.channel}입니다. ${profile.market}의 잠재 파트너와 최소 주문량·보관 조건을 확인하세요.`, experiment: '동일 제품의 채널별 도달 비용과 테스트 판매 수익성을 기록합니다.' },
  ];
  const productSnapshot = {...e.product, channels: {web: e.product.channels.web}};
  const report = { id: globalThis.crypto?.randomUUID?.() || `report-${Date.now()}`, createdAt: new Date().toISOString(), profile: { ...profile }, title: `${e.product.name}, ${profile.market} 시장 진출 전략`, analysis: {product: productSnapshot, stats: {current:e.stats.current,growth:e.stats.growth}, region:e.region, food:e.food}, evidence: e.facts, summary: ai?.summary || `${profile.company}의 ${e.product.name} 제품을 위한 검증 중심 진출 계획입니다. 검색 관심도와 레시피·리뷰의 관측 사실을 먼저 확인하고, 현지화 제안은 테스트할 가설로 구분합니다.`, localization: ai?.localization || localization, plan: ai?.plan || plan, risks: [...new Set([...(ai?.risks || ['시장 규모·실제 판매량·경쟁사 가격은 제공 데이터에 없습니다.', '수입 요건·표시 규정·인증은 현지 담당자와 최신 공식 자료로 별도 확인해야 합니다.']), ...e.product.warnings])], mode: ai ? 'ollama' : 'evidence', model, snapshotDate: data.snapshotDate };
  return profile.language==='en'?englishReport(report,e,ai):{...report,language:'ko'};
}

export function ollamaContext(data, profile) {
  const e = evidenceFor(data, profile);
  return { language: profile.language || 'ko', profile: {...profile, product: profile.language==='en'?productsEn[e.product.id]:e.product.name, market:profile.language==='en'?englishLabel(profile.market):profile.market}, evidence: e.facts, foodRecipeReviews: {product: e.food, method: data.foodcom.reviewMethod}, dataWarnings: e.product.warnings, snapshotDate: data.snapshotDate, limits: ['검색 관심도는 매출이 아닙니다.', '국가별 소비자 조사·경쟁사 매출·수입 규정 데이터 없음.', '모든 현지화 제안은 실험 가설입니다.'], relatedSearches: (e.product.channels.web?.rising || []).filter(x => !x.noise).slice(0, 6) };
}

export function reportMarkdown(report) {
  if(report.language==='en')return englishMarkdown(report);
  return `# ${report.title}\n\n${report.profile.company} · ${report.profile.market} · ${report.snapshotDate} 데이터 기준\n\n생성: ${report.mode === 'ollama' ? 'FLAVO AI' : '데이터 요약 (AI 미사용)'}\n\n## 핵심 요약\n${report.summary}\n\n## 확인된 사실\n${report.evidence.map(e => `### [${e.id}] ${e.title}\n${e.text}\n\n출처: ${e.source || '미제공'}\n해석 한계: ${e.caution}`).join('\n\n')}\n\n## 현지화 전략 — 검증할 가설\n${report.localization.map(x => `### ${x.title}\n${x.hypothesis}\n\n실험: ${x.experiment}\n참조: ${x.evidenceIds.join(', ')}`).join('\n\n')}\n\n## 90일 실행 계획\n${report.plan.map(x => `### ${x.period} · ${x.title}\n${x.action}\n\n확인지표: ${x.metric}`).join('\n\n')}\n\n## 확인이 필요한 사항\n${report.risks.map(x => `- ${x}`).join('\n')}\n\n※ AI 제안은 담당자 검토가 필요합니다. 출처 연결은 사실의 자동 검증을 뜻하지 않습니다.\n`;
}
