"""Small independent fixtures catch joins, duplicates, multiline CSV and denominators."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from foodcom import aggregate

class FoodComTests(unittest.TestCase):
    def test_full_scan_join_duplicates_and_unrated_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with (folder / 'recipes.csv').open('w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['RecipeId','Name','RecipeCategory','Keywords','RecipeIngredientParts'])
                w.writerows([[10, 'Kimchi soup', 'Soup', 'korean', 'c("salt", "salt", "cabbage")'],
                             [10, 'Duplicate', '', '', ''], [20, 'Apple pie', 'Dessert', '', ''],
                             [30, 'Tteokbokki', '', '', '']])
            with (folder / 'reviews.csv').open('w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['ReviewId','RecipeId','Rating','Review','DateSubmitted'])
                w.writerows([[1,10,5,'easy, easy\nspicy','2020-01-01'], [1,10,1,'duplicate',''],
                             [2,10,0,'simple',''], [3,10,3,'instead of salt',''],
                             [4,20,1,'sweet',''], [5,999,4,'quick',''],
                             [6,10,'NA','not sweet',''], [7,20,6,'invalid rating','']])
            result = aggregate(folder)
        self.assertEqual(result['overall']['recipeCount'], 3)
        self.assertEqual(result['count'], 7)
        self.assertEqual(result['quality']['duplicateRecipeIds'], 1)
        self.assertEqual(result['quality']['duplicateReviewIds'], 1)
        self.assertEqual(result['quality']['unmatchedReviewCount'], 1)
        kimchi = result['products']['kimchi']
        self.assertEqual(kimchi['reviewCount'], 4)
        self.assertEqual(kimchi['ratedCount'], 2)
        self.assertEqual(kimchi['meanRating'], 4)
        self.assertEqual(kimchi['mentions']['조리 편의'], 2)
        self.assertEqual(kimchi['mentions']['단맛'], 1)  # negation is still a mention, never sentiment
        self.assertEqual(kimchi['ingredients'][0]['count'], 1)
        self.assertEqual(result['products']['kimchi_stew']['reviewCount'], 4)
        self.assertEqual(result['products']['tteokbokki']['reviewCount'], 0)
        self.assertIsNone(result['products']['tteokbokki']['meanRating'])

if __name__ == '__main__':
    unittest.main()
