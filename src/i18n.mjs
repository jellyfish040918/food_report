let language = 'ko';
try { if(globalThis.localStorage?.getItem('flavo.language') === 'en') language='en'; } catch {}
export const getLanguage = () => language;
export function setLanguage(value) { language=value==='en'?'en':'ko'; try{globalThis.localStorage?.setItem('flavo.language',language);}catch{} }
export const t = (ko,en) => language==='en'?en:ko;
export const locale = () => language==='en'?'en-US':'ko-KR';
export const number = (value,digits=0) => value==null?'—':new Intl.NumberFormat(locale(),{maximumFractionDigits:digits}).format(value);
export const productsEn = {kimchi:'Kimchi',kimchi_stew:'Kimchi stew',tteokbokki:'Tteokbokki',Bulgogi:'Bulgogi',japchae:'Japchae',rice_cake:'Rice cakes',seaweed:'Seaweed',korean_food:'Korean food','k-food':'K-food'};
export const productName = p => language==='en'?(productsEn[p.id]||p.name):p.name;
const words = {'전체 해외':'All overseas markets','미국':'United States','일본':'Japan','영국':'United Kingdom','베트남':'Vietnam','태국':'Thailand','필리핀':'Philippines','중국':'China','한국':'South Korea','대한민국':'South Korea','이탈리아':'Italy','프랑스':'France','싱가포르':'Singapore','캐나다':'Canada','오스트레일리아':'Australia','독일':'Germany','말레이시아':'Malaysia','상온 간편식':'Shelf-stable meals','냉동 간편식':'Frozen meals','냉장 완제품':'Chilled ready-to-eat','소스·조미료':'Sauces & seasonings','스낵·간식':'Snacks','외식 메뉴':'Foodservice menu','온라인 직접 판매':'Online direct-to-consumer','현지 아시안 마켓':'Asian grocery stores','현지 대형 유통':'Mainstream retail','외식·식자재 B2B':'Foodservice / B2B','매운맛':'Spiciness','단맛':'Sweetness','짠맛':'Saltiness','식감':'Texture','조리 편의':'Ease of cooking','재료 대체':'Substitutions','가격':'Price','신선함':'Freshness','신맛':'Sourness'};
export function registerCountries(countries) { for(const c of countries) if(!words[c.ko])words[c.ko]=c.en; }
Object.assign(words,{'대만':'Taiwan','중국':'China','홍콩':'Hong Kong','남아프리카':'South Africa','튀르키예':'Türkiye','세인트헬레나':'Saint Helena','괌':'Guam','모리셔스':'Mauritius','중앙 아프리카 공화국':'Central African Republic','콩고-킨샤사':'Democratic Republic of the Congo','콩고-브라자빌':'Republic of the Congo'});
export const englishLabel = value => words[value] || value;
export const label = value => language==='en'?englishLabel(value):value;
export const channelName = key => ({web:t('웹 검색','Web search'),youtube:'YouTube',shopping:t('쇼핑','Shopping'),news:t('뉴스','News'),image:t('이미지','Images')})[key]||key;
const warningsEn = {
  '화장품 등 음식과 무관한 연관 검색어를 분석에서 제외했습니다.':'Non-food related queries, including cosmetics, have been excluded from analysis.',
  '원본 검색어가 tteokbboki로 표기되어 있습니다. 표준 검색어로 재수집하기 전 시장 수요 판단에 사용하지 마세요.':'The source query is misspelled “tteokbboki”. Recollect using the standard spelling before assessing market demand.',
  '0인 관측값이 많습니다. 0은 수요가 없다는 뜻이 아니라 검색량 부족일 수 있습니다.':'Many observations are zero, which may reflect insufficient search volume rather than no demand.',
  '지역 데이터 표본이 적어 국가 비교가 제한됩니다.':'The regional sample is small, limiting country comparisons.',
  'seaweed는 식용 김 외의 해조류 용례도 포함합니다.':'The query “seaweed” includes uses beyond edible gim.'
};
export const warningText = product => product.warnings.map(w=>language==='en'?(warningsEn[w]||'Review the source data limitations before drawing conclusions.'):w).join(' ');
export const reportTitle = (report,product) => t(`${product.name}, ${report.profile.market} 시장 진출 전략`,`${productsEn[product.id]||product.name} · ${englishLabel(report.profile.market)} market entry`);
