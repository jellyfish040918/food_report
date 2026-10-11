"""Stream every canonical Food.com recipe and review; publish anonymous aggregates."""
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'kimchi': r'\b(kimchi|kimchee|kim chi)\b',
    'kimchi_stew': r'\b(kimchi|kimchee|kim chi)\b.*\b(stew|soup|jjigae|chigae)\b|\b(stew|soup|jjigae|chigae)\b.*\b(kimchi|kimchee|kim chi)\b',
    'tteokbokki': r'\b(tteokbokki|tteokboki|ddukbokki|dukbokki|duk bok ki|topokki|tokbokki)\b',
    'Bulgogi': r'\b(bulgogi|bulgoki|bul go gi)\b',
    'japchae': r'\b(japchae|chapchae|chap chae|jap chae|chap chae)\b',
    'rice_cake': r'\b(rice cakes?|tteok|dduk|mochi)\b',
    'seaweed': r'\b(seaweed|nori|wakame|kelp|kombu)\b',
    'korean_food': r'\b(korean|kimchi|bulgogi|japchae|tteokbokki|bibimbap)\b',
    'k-food': r'\b(korean|kimchi|bulgogi|japchae|tteokbokki|bibimbap)\b',
}
TERMS = {
    '매운맛': r'\b(spicy|spice|hot pepper|heat)\b',
    '단맛': r'\b(sweet|sugary|sugar)\b',
    '짠맛': r'\b(salty|salt|sodium)\b',
    '식감': r'\b(texture|crispy|crunchy|chewy|tender)\b',
    '조리 편의': r'\b(easy|simple|quick|convenient)\b',
    '재료 대체': r'\b(substitute|substituted|substitution|replace|replaced|instead)\b',
}

def numeric(value):
    try:
        n = float(value)
        return n if n == n and abs(n) != float('inf') else None
    except (ValueError, TypeError):
        return None

def identifier(value):
    n = numeric(value)
    return int(n) if n is not None and n.is_integer() else None

def bucket():
    return {'recipeCount': 0, 'reviewCount': 0, 'ratings': Counter(), 'mentions': Counter(),
            'ingredients': Counter(), 'reviewed': set(), 'examples': [], 'yearCounts': Counter()}

def add_review(group, row, recipe_id, patterns):
    group['reviewCount'] += 1
    rating = numeric(row.get('Rating'))
    # 0/NA are unrated, never interpreted as a negative opinion.
    if rating is not None and rating in (1, 2, 3, 4, 5):
        group['ratings'][int(rating)] += 1
    if recipe_id is not None:
        group['reviewed'].add(recipe_id)
    text = row.get('Review', '')
    for name, pattern in patterns.items():
        if pattern.search(text):
            group['mentions'][name] += 1
    date = row.get('DateSubmitted', '')
    if re.match(r'^\d{4}-\d{2}-\d{2}', date):
        group['yearCounts'][date[:4]] += 1

def finish(group):
    rated = sum(group['ratings'].values())
    return {
        'recipeCount': group['recipeCount'], 'reviewCount': group['reviewCount'],
        'ratedCount': rated, 'unratedCount': group['reviewCount'] - rated,
        'meanRating': round(sum(k*v for k, v in group['ratings'].items()) / rated, 2) if rated else None,
        'ratings': {str(k): group['ratings'][k] for k in range(1, 6)},
        'mentions': {k: group['mentions'][k] for k in TERMS},
        'reviewedRecipeCount': len(group['reviewed']),
        'ingredients': [{'name': k, 'count': v} for k, v in group['ingredients'].most_common(8)],
        'examples': sorted(group['examples'], key=lambda x: (-x['reviews'], x['id']))[:6],
        'yearCounts': dict(sorted(group['yearCounts'].items())),
    }

def aggregate(folder=None):
    folder = folder or ROOT / 'data' / 'Food.com - Recipes and Reviews'
    groups = {key: bucket() for key in PATTERNS}
    patterns = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
    terms = {k: re.compile(v, re.I) for k, v in TERMS.items()}
    membership, seen_reviews = {}, set()
    overall = bucket()
    categories = Counter()
    raw_recipes = raw_reviews = duplicate_recipes = duplicate_reviews = unmatched = 0
    for path in [folder / 'recipes.csv', folder / 'reviews.csv']:
        if not path.exists():
            raise FileNotFoundError(f'Food.com canonical file missing: {path}')
    with (folder / 'recipes.csv').open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            raw_recipes += 1
            recipe_id = identifier(row.get('RecipeId'))
            if recipe_id is None:
                raise ValueError('RecipeId must be a numeric identifier')
            if recipe_id in membership:
                duplicate_recipes += 1
                continue
            text = ' '.join(row.get(k, '') for k in ('Name', 'RecipeCategory', 'Keywords'))
            keys = tuple(k for k, pattern in patterns.items() if pattern.search(text))
            membership[recipe_id] = keys
            overall['recipeCount'] += 1
            categories[row.get('RecipeCategory') or 'Unknown'] += 1
            # Source ingredient lists are R-style quoted strings. Counts use unique ingredients per recipe.
            ingredients = {s.lower().strip() for s in re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', row.get('RecipeIngredientParts', '')) if s.strip()}
            for key in keys:
                group = groups[key]
                group['recipeCount'] += 1
                group['ingredients'].update(ingredients)
                group['examples'].append({'id': str(recipe_id), 'name': row['Name'], 'rating': numeric(row.get('AggregatedRating')), 'reviews': numeric(row.get('ReviewCount')) or 0, 'category': row.get('RecipeCategory', '')})
    print(f'Food.com recipes: {overall["recipeCount"]:,}; joining reviews...', flush=True)
    with (folder / 'reviews.csv').open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            raw_reviews += 1
            review_id = identifier(row.get('ReviewId'))
            if review_id is None:
                raise ValueError('ReviewId must be a numeric identifier')
            if review_id in seen_reviews:
                duplicate_reviews += 1
                continue
            seen_reviews.add(review_id)
            recipe_id = identifier(row.get('RecipeId'))
            linked = recipe_id in membership
            add_review(overall, row, recipe_id if linked else None, terms)
            if linked:
                for key in membership[recipe_id]:
                    add_review(groups[key], row, recipe_id, terms)
            else:
                unmatched += 1
    result = {
        'count': overall['reviewCount'], 'overall': finish(overall),
        'products': {key: finish(group) for key, group in groups.items()},
        'categories': dict(categories.most_common(10)),
        'quality': {'rawRecipeRows': raw_recipes, 'rawReviewRows': raw_reviews,
                    'duplicateRecipeIds': duplicate_recipes, 'duplicateReviewIds': duplicate_reviews,
                    'unmatchedReviewCount': unmatched, 'linkedReviewCount': overall['reviewCount'] - unmatched},
        'sources': {k: f'data/Food.com - Recipes and Reviews/{k}.csv' for k in ('recipes', 'reviews')},
        'matching': PATTERNS,
        'method': '전체 CSV를 읽고 RecipeId로 리뷰를 연결했습니다. 제품은 레시피 이름·분류·키워드의 영어 검색 규칙으로 선택하며 여러 제품군에 중복 포함될 수 있습니다. 떡은 mochi 등 다른 나라 쌀떡도 포함합니다.',
        'reviewMethod': '1–5점만 평균에 사용하며 0·결측 평점은 제외합니다. 리뷰당 영어 키워드별 1회 집계입니다. 단어 등장은 감성·선호 또는 구매 의향을 뜻하지 않습니다. 작성자 국가 정보가 없어 국가별 결과로 해석하지 않습니다.',
        'formats': {'canonical': ['recipes.csv', 'reviews.csv'], 'alternate': ['recipes.parquet', 'reviews.parquet'], 'note': 'CSV를 전체 집계합니다. Parquet는 같은 데이터의 대체 저장 형식으로 별도 표본에 더하지 않습니다.'},
    }
    print(f'Food.com reviews: {result["count"]:,}; linked: {result["quality"]["linkedReviewCount"]:,}', flush=True)
    return result

if __name__ == '__main__':
    csv.field_size_limit(10_000_000)
    print(json.dumps(aggregate(), ensure_ascii=False))
