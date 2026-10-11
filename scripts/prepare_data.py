"""Compile the supplied local datasets into a small, traceable public snapshot.

Only aggregate statistics are published. Raw reviews, authors and archive files
never enter the website build. Uses the Python standard library only.
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from foodcom import aggregate as foodcom

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'src' / 'generated' / 'data.json'
csv.field_size_limit(10_000_000)
LABELS = {'kimchi': '김치', 'kimchi_stew': '김치찌개', 'tteokbokki': '떡볶이', 'Bulgogi': '불고기', 'japchae': '잡채', 'rice_cake': '떡', 'seaweed': '김·해조류', 'korean_food': '한식', 'k-food': 'K-food'}
ASSETS = {'kimchi': '1.png', 'kimchi_stew': '2.png', 'tteokbokki': '3.png', 'Bulgogi': '6.png', 'japchae': '6.png', 'rice_cake': '3.png', 'seaweed': '6.png', 'korean_food': '6.png', 'k-food': '6.png'}

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.reader(f))

def number(value):
    value = value.replace(',', '').replace('%', '').strip()
    if value == '<1':
        return 0.5
    try:
        return float(value)
    except ValueError:
        return None

def relative(path):
    return path.relative_to(ROOT).as_posix()

def trends():
    products = []
    all_files = list((DATA / 'google_trend').rglob('*.csv'))
    for key, label in LABELS.items():
        channels = {}
        for folder in sorted((DATA / 'google_trend' / key).iterdir()):
            if not folder.is_dir():
                continue
            item = {'series': [], 'regions': [], 'rising': [], 'top': [], 'sources': {}}
            for prefix, field in [('time_series', 'series'), ('by_region', 'regions'), ('searched_with_rising', 'rising'), ('searched_with_top', 'top')]:
                files = sorted(folder.glob(prefix + '*.csv'))
                if not files:
                    continue
                path = files[-1]  # latest timestamp; avoids duplicate exports
                rows = read_csv(path)
                item['sources'][field] = relative(path)
                if len(rows[0]) > 1 and field == 'series':
                    item['query'] = rows[0][1]
                for row in rows[1:]:
                    if len(row) < 2:
                        continue
                    value = number(row[1])
                    if field == 'series':
                        if value is not None:
                            item[field].append({'date': row[0], 'value': value, 'partial': row[0] >= '2026-10-01'})
                    elif field == 'regions':
                        if value is not None:
                            item[field].append({'name': row[0], 'value': value})
                    else:
                        item[field].append({'query': row[0], 'value': value, 'growth': row[2] if len(row) > 2 else None, 'noise': bool(re.search(r'makeup|powder|cosmetic|sephora', row[0], re.I))})
            channels[folder.name] = item
        warnings = []
        if key == 'tteokbokki':
            warnings.append('원본 검색어가 tteokbboki로 표기되어 있습니다. 표준 검색어로 재수집하기 전 시장 수요 판단에 사용하지 마세요.')
        web = channels.get('web', {})
        complete = [x for x in web.get('series', []) if not x['partial']]
        if complete and sum(x['value'] > 0 for x in complete) / len(complete) < 0.5:
            warnings.append('0인 관측값이 많습니다. 0은 수요가 없다는 뜻이 아니라 검색량 부족일 수 있습니다.')
        if len(web.get('regions', [])) < 5:
            warnings.append('지역 데이터 표본이 적어 국가 비교가 제한됩니다.')
        if key == 'seaweed':
            warnings.append('seaweed는 식용 김 외의 해조류 용례도 포함합니다.')
        if any(x.get('noise') for x in web.get('rising', [])):
            warnings.append('화장품 등 음식과 무관한 연관 검색어를 분석에서 제외했습니다.')
        products.append({'id': key, 'name': label, 'image': ASSETS[key], 'channels': channels, 'warnings': warnings, 'eligible': key != 'tteokbokki'})
    return products, len(all_files)

def ingredients():
    path = DATA / 'Recipe Ingredients Dataset' / 'train.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    cuisines, totals = defaultdict(Counter), Counter()
    for row in rows:
        totals[row['cuisine']] += 1
        cuisines[row['cuisine']].update(set(row['ingredients']))
    return {'count': len(rows), 'source': relative(path), 'cuisines': {key: {'count': totals[key], 'ingredients': [{'name': k, 'count': v, 'percent': round(v / totals[key] * 100, 1)} for k, v in counts.most_common(12)]} for key, counts in cuisines.items()}}

def flavors():
    path = DATA / 'FlavorSense.csv'
    count, valid, missing = 0, Counter(), 0
    exposure = defaultdict(Counter)
    for row in csv.DictReader(path.open(encoding='utf-8-sig', newline='')):
        count += 1
        taste = row.get('preferred_taste', '').strip()
        if taste:
            valid[taste] += 1
            exposure[row.get('historical_cuisine_exposure', '') or 'Unknown'][taste] += 1
        else:
            missing += 1
    return {'count': count, 'valid': sum(valid.values()), 'missing': missing, 'tastes': dict(valid), 'exposure': dict(exposure), 'source': relative(path), 'limitation': '수집 시점·지역·표본 설계 미상. 국가별 선호나 시장 대표값으로 해석하지 않습니다.'}

def reviews():
    path = DATA / 'restaurant-reviews' / 'train.csv'
    count, ratings, mentions = 0, Counter(), Counter()
    terms = {'매운맛': r'\b(spicy|spice|hot pepper)\b', '단맛': r'\b(sweet|sugary)\b', '식감': r'\b(texture|crispy|crunchy|chewy)\b', '가격': r'\b(price|expensive|cheap|affordable)\b', '신선함': r'\b(fresh|freshness)\b'}
    patterns = {k: re.compile(v, re.I) for k, v in terms.items()}
    with path.open(encoding='utf-8-sig') as f:
        for line in f:
            pieces = line.rstrip('\n').split('\t', 1)
            if len(pieces) != 2 or not pieces[0].isdigit():
                continue
            count += 1
            ratings[pieces[0]] += 1
            for key, pattern in patterns.items():
                if pattern.search(pieces[1]):
                    mentions[key] += 1
    return {'count': count, 'ratings': dict(ratings), 'mentions': dict(mentions), 'source': relative(path), 'method': 'train.csv만 집계해 중복 사본 제외. 영어 키워드가 1회 이상 등장한 리뷰 수이며 긍정·부정 감성 또는 국가별 비율이 아닙니다.'}

def main():
    products, files = trends()
    result = {'schemaVersion': 2, 'snapshotDate': '2026-10-09', 'completeThrough': '2026-09-30', 'trendFileCount': files, 'products': products}
    for key, fn in [('ingredients', ingredients), ('flavors', flavors), ('foodcom', foodcom), ('reviews', reviews)]:
        result[key] = fn()
        print(f'{key}: {result[key]["count"]:,} rows')
    food = result['foodcom']
    korean = food['products']['korean_food']
    result['recipes'] = {'count': food['overall']['recipeCount'], 'koreanCount': korean['recipeCount'], 'examples': korean['examples'], 'source': food['sources']['recipes'], 'method': food['method']}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Written {OUT} ({OUT.stat().st_size:,} bytes), {files} trend files')

if __name__ == '__main__':
    main()
