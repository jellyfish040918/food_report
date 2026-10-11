"""English presentation of the same canonical Q&A aggregates (no model translation)."""
import json
from functools import lru_cache
from pathlib import Path

PRODUCTS={'kimchi':'Kimchi','kimchi_stew':'Kimchi stew','tteokbokki':'Tteokbokki','Bulgogi':'Bulgogi','japchae':'Japchae','rice_cake':'Rice cakes','seaweed':'Seaweed','korean_food':'Korean food','k-food':'K-food'}
TERMS={'매운맛':'Spiciness','단맛':'Sweetness','짠맛':'Saltiness','식감':'Texture','조리 편의':'Ease of cooking','재료 대체':'Substitutions','가격':'Price','신선함':'Freshness'}
CHANNELS={'web':'Web search','youtube':'YouTube','shopping':'Shopping','news':'News','image':'Images'}
REVIEW_LIMIT='Food.com reviews date from 2000–2020. Reviewer countries are unavailable. Keyword presence is not sentiment or preference; categories may overlap.'
RECIPE_LIMIT='Product groups match recipe names, categories and keywords; groups may overlap. Rice cakes include mochi and other countries’ recipes.'
INGREDIENT_LIMIT='Ingredient occurrence is a recipe-sample property, not a national consumer preference. US cuisine data covers Southern US recipes only.'
REGION_LIMIT='Relative to all searches within each region, not absolute search volumes or market-size rankings.'
TREND_LIMIT='Worldwide relative search index, not sales or country growth. Independently collected product indices cannot be compared as absolute demand.'

@lru_cache(maxsize=1)
def country_names():
    path=Path(__file__).resolve().parent/'src/geo/world.json'
    names={c['ko']:c['en'] for c in json.loads(path.read_text(encoding='utf-8'))['countries']}
    names.update({'전체 해외':'All overseas markets','오스트레일리아':'Australia','체코':'Czechia','튀르키예':'Türkiye','남아프리카':'South Africa','한국':'South Korea','대한민국':'South Korea','미국':'United States','영국':'United Kingdom'})
    names.update({'대만':'Taiwan','중국':'China','홍콩':'Hong Kong','세인트헬레나':'Saint Helena','괌':'Guam','모리셔스':'Mauritius','중앙 아프리카 공화국':'Central African Republic','콩고-킨샤사':'Democratic Republic of the Congo','콩고-브라자빌':'Republic of the Congo'})
    return names

def num(value,digits=0):
    return f'{value:,.{digits}f}'.rstrip('0').rstrip('.') if digits else f'{value:,.0f}'

def data_notice(notice):
    if not notice:return 'Additional source data is needed for this question.'
    if '검증에 실패' in notice:return 'AI generation or citation validation failed. Showing computed source facts instead.'
    if '다른 분석' in notice:return 'AI is working on another request. Showing computed source facts now.'
    if '연결하지 못해' in notice:return 'AI could not be reached. Showing computed source facts instead.'
    return 'Showing computed source facts. AI explanations become available when the engine is ready.'

def translate_context(data,request,context):
    from qa import MARKETS
    names=country_names(); country=lambda name:names.get(name,name)
    channel=context['scope']['channel']; translated=[]
    for original in context['evidence']:
        title=original['title']; p=next((p for p in data['products'] if title.startswith(p['name']+' · ')),None)
        e={**original}; food=data['foodcom']['products'][p['id']] if p else None
        name=PRODUCTS[p['id']] if p else ''
        if p and title.endswith('지역 관심도'):
            market=title[len(p['name'])+3:-len(' 지역 관심도')]
            rows=sorted((r for r in p['channels'][channel]['regions'] if r['name']!='대한민국'),key=lambda r:-r['value'])
            region=next((r for r in rows if r['name']==market),None)
            e['title']=f'{name} · {country(market)} regional interest'
            if market=='전체 해외':e['text']=f'Top observed overseas regions for {name} ({CHANNELS[channel]}, {len(rows)} regions): '+', '.join(f'{country(r["name"])} {r["value"]}/100' for r in rows[:5])+'.'
            elif region:e['text']=f'{name} in {country(market)}: {region["value"]}/100; rank {1+sum(r["value"]>region["value"] for r in rows)} of {len(rows)} observed overseas regions (ties share ranks).'
            else:e['text']=f'No {CHANNELS[channel]} observation for {name} in {country(market)}. This does not mean no demand.'
            e['caution']=REGION_LIMIT
        elif p and title.endswith('관심도'):
            rows=sorted((r for r in p['channels'][channel]['series'] if not r['partial']),key=lambda r:r['date'])
            recent,prior=rows[-12:],rows[-24:-12]; current=sum(r['value'] for r in recent)/len(recent) if recent else None;before=sum(r['value'] for r in prior)/len(prior) if prior else 0
            valid=p['eligible'] and len(recent)==len(prior)==12 and before>0 and sum(r['value']>0 for r in rows)/len(rows)>=.5
            e['title']=f'{name} · {CHANNELS[channel]} interest'
            e['text']=f'Worldwide {CHANNELS[channel]} mean for {name}, {recent[0]["date"][:7]}–{recent[-1]["date"][:7]}: {num(current,2)}/100. '+(f'Previous 12-month mean: {num(before,2)}; change: {(current/before-1)*100:+.1f}%.' if valid else 'No valid growth estimate due to a misspelled query, sparse observations or insufficient comparison data.') if recent else 'No complete time series.'
            e['caution']=TREND_LIMIT
        elif p and title.endswith('관련 레시피'):
            e.update(title=f'{name} · Recipes',text=f'{num(food["recipeCount"])} of {num(data["recipes"]["count"])} Food.com recipes match {name}; {num(food["reviewedRecipeCount"])} have linked reviews.',caution=RECIPE_LIMIT)
        elif p and title.endswith('리뷰와 평점'):
            text=f'{name} has {num(food["reviewCount"])} linked reviews. '
            text+=f'Mean rating: {num(food["meanRating"],2)}/5 from {num(food["ratedCount"])} valid ratings. {num(food["unratedCount"])} zero / missing ratings are excluded.' if food['ratedCount'] else 'There are no valid 1–5 ratings, so a mean cannot be calculated.'
            e.update(title=f'{name} · Reviews and ratings',text=text,caution=REVIEW_LIMIT)
        elif p and title.endswith('리뷰의 경험 키워드'):
            # The canonical retrieval determines the included keywords. Keep the same numerator set.
            pairs=[(k,v) for k,v in food['mentions'].items() if k+' ' in original['text']]
            e.update(title=f'{name} · Review keywords',text=f'Of {num(food["reviewCount"])} {name} reviews: '+', '.join(f'{TERMS[k]} {num(v)} ({num(v/food["reviewCount"]*100,1)}%)' for k,v in pairs)+'. Each keyword counts at most once per review.',caution=REVIEW_LIMIT)
        elif p and title.endswith('레시피 재료'):
            e.update(title=f'{name} · Recipe ingredients',text=f'Ingredient occurrence across {num(food["recipeCount"])} {name} recipes: '+', '.join(f'{i["name"]} {num(i["count"])}' for i in food['ingredients'][:5])+'.',caution=INGREDIENT_LIMIT)
        elif title.endswith(' · 요리 재료'):
            market=title[:-len(' · 요리 재료')]; cuisine_id=MARKETS.get(market,(None,'',[]))[0];cuisine=data['ingredients']['cuisines'].get(cuisine_id)
            text=f'{num(cuisine["count"])} {"Southern US" if market=="미국" else country(market)} cuisine recipes: '+', '.join(f'{i["name"]} {i["percent"]}%' for i in cuisine['ingredients'][:5])+'.' if cuisine else f'No directly matching cuisine sample for {country(market)}. Local research is needed.'
            e.update(title=f'{country(market)} · Cuisine ingredients',text=text,caution=INGREDIENT_LIMIT)
        elif title=='음식점 리뷰 · 전체 표본':
            e.update(title='Restaurant reviews · Whole sample',text=f'Keyword occurrences across {num(data["reviews"]["count"])} reviews: '+', '.join(f'{TERMS.get(k,k)} {num(v)}' for k,v in data['reviews']['mentions'].items())+'.',caution='English keyword presence, not sentiment. This whole sample does not represent a specific product or country.')
        elif title=='취향 · 전체 표본':
            e.update(title='Taste · Whole sample',text=f'Of {num(data["flavors"]["valid"])} valid FlavorSense records: '+', '.join(f'{k} {num(v)}' for k,v in data['flavors']['tastes'].items())+'.',caution='Geography, collection period and sampling design are unknown. Do not infer national taste preferences.')
        elif title=='연결된 자료의 범위':
            e.update(title='Connected source coverage',text=f'Snapshot {data["snapshotDate"]}: {data["trendFileCount"]} Trends files, {num(data["recipes"]["count"])} Food.com recipes, {num(data["foodcom"]["count"])} Food.com reviews, {num(data["ingredients"]["count"])} cuisine recipes, {num(data["reviews"]["count"])} restaurant reviews and {num(data["flavors"]["count"])} taste records.',caution='Incomplete October 2026 observations are excluded from trends. Sources have different collection periods and populations.')
        else:raise ValueError('Unsupported evidence translation.')
        translated.append(e)
    limits=list(dict.fromkeys(e['caution'] for e in translated))
    if context['partial']:limits.insert(0,'The full requested scope cannot be verified. Tariffs, current regulations, sales, market size, national consumer surveys and live information are not provided. Specified periods are not separately re-aggregated.')
    if not translated:limits.append('No directly supporting evidence was found. Ask about product search trends, regional interest, recipes, review ratings / keywords or cuisine ingredients.')
    if any(not p['eligible'] for p in data['products'] if p['id'] in context['scope']['products']):limits.append('The source query “tteokbboki” is misspelled. Do not use it for growth decisions.')
    if len(context['scope']['products'])==3 or len(context['scope']['markets'])==3:limits.append('Comparison is limited to three products and three markets per question.')
    return {**context,'evidence':translated,'limits':limits}
