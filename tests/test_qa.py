"""Factual retrieval against the same aggregate shipped to the browser."""
import copy
import json
from pathlib import Path
import unittest

import qa

DATA = json.loads((Path(__file__).resolve().parents[1] / 'src/generated/data.json').read_text(encoding='utf-8'))


class RetrievalTests(unittest.TestCase):
    def ask(self, question, **kwargs):
        return qa.retrieve(DATA, qa.validate_question({'question': question, **kwargs}, DATA))

    def test_review_uses_linked_product_and_correct_denominators(self):
        result = self.ask('김치 리뷰에서 매운맛은 얼마나 언급돼?')
        text = ' '.join(e['text'] for e in result['evidence'])
        for fact in ['195건', '184건', '4.65/5', '11건', '38건(19.5%)']:
            self.assertIn(fact, text)
        self.assertIn('2000–2020년', ' '.join(result['limits']))
        self.assertIn('국가별', ' '.join(result['limits']))
        self.assertTrue(all(e['source'].endswith('reviews.csv') for e in result['evidence']))
        answer = qa.data_answer(result)
        self.assertEqual(answer['mode'], 'data')
        self.assertEqual(answer['points'][1]['evidenceIds'], ['F2'])

    def test_followup_reuses_topic_and_overrides_product(self):
        result = self.ask('그럼 불고기는?', history=['김치 리뷰에서 매운맛은 얼마나 언급돼?'])
        self.assertEqual(result['scope']['product'], 'Bulgogi')
        self.assertIn('26건(12.6%)', str(result['evidence']))
        self.assertNotIn('195건', str(result['evidence']))

    def test_country_followup_retrieves_correct_cuisine(self):
        result = self.ask('그럼 일본은?', market='미국', history=['미국 요리에 자주 쓰이는 재료는?'])
        self.assertEqual(result['scope']['market'], '일본')
        self.assertIn('일본 요리 레시피 1,423건', str(result['evidence']))
        self.assertIn('soy sauce 39.4%', str(result['evidence']))

    def test_specific_names_do_not_accidentally_select_parent_product(self):
        self.assertEqual(qa.mentioned_products('김치찌개 레시피'), ['kimchi_stew'])
        self.assertEqual(qa.mentioned_products('떡볶이 리뷰'), ['tteokbokki'])

    def test_reviews_are_not_presented_as_country_specific(self):
        result = self.ask('일본 김치 리뷰의 평점은?')
        self.assertTrue(result['partial'])
        self.assertIn('범위 전체를 확인할 수는 없습니다', qa.data_answer(result)['answer'])

    def test_no_reviews_are_not_replaced_with_overall_reviews(self):
        result = self.ask('떡볶이 평점과 매운맛 리뷰는?')
        self.assertEqual(len(result['evidence']), 1)
        self.assertIn('연결 리뷰는 0건', result['evidence'][0]['text'])
        self.assertNotIn('4.65', str(result['evidence']))

    def test_trend_excludes_partial_month_and_preserves_validity(self):
        kimchi = self.ask('김치 검색 추이는?')
        self.assertIn('2025-10–2026-09', str(kimchi['evidence']))
        self.assertIn('+9.1%', str(kimchi['evidence']))
        typo = self.ask('떡볶이 검색 성장률은?')
        self.assertIn('유효한 변화율을 계산하지 않습니다', str(typo['evidence']))
        self.assertIn('tteokbboki', str(typo['limits']))

    def test_out_of_scope_question_has_no_fabricated_evidence(self):
        result = self.ask('김치 수출 관세는 얼마야?')
        self.assertEqual(result['evidence'], [])
        self.assertTrue(result['partial'])
        self.assertIn('확인할 수 없습니다', qa.data_answer(result)['answer'])
        self.assertIn('관세', str(result['limits']))

    def test_sales_ranking_cannot_masquerade_as_search_ranking(self):
        result = self.ask('김치 판매량 국가별 순위는?')
        self.assertTrue(result['partial'])
        self.assertIn('절대 검색량', str(result['limits']))
        self.assertIn('범위 전체를 확인할 수는 없습니다', qa.data_answer(result)['answer'])

    def test_requested_period_is_not_silently_ignored(self):
        result = self.ask('2026년 김치 리뷰 평점은?')
        self.assertTrue(result['partial'])
        self.assertIn('다시 필터링한 결과는 아닙니다', str(result['limits']))

    def test_missing_country_cuisine_is_explicit(self):
        result = self.ask('독일 요리에 자주 쓰이는 재료는?')
        self.assertIn('직접 대응하는 요리 재료 표본이 없습니다', str(result['evidence']))

    def test_question_validation_rejects_bad_types_and_unbounded_history(self):
        for change in [{'question':' '}, {'question':'a'*1501}, {'product':[]}, {'channel':{}}, {'market':True}, {'history':['a']*7}, {'history':[{}]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                qa.validate_question({'question':'김치 리뷰', **change}, DATA)

    def test_ai_answer_requires_existing_citations_and_limits(self):
        context = self.ask('김치 리뷰 평점은?')
        answer = {'answer':'김치 관련 과거 리뷰를 확인했습니다.', 'points':[{'text':context['evidence'][0]['text'], 'evidenceIds':['F1']}], 'limits':['국가별 표본이 아닙니다.']}
        self.assertEqual(qa.validate_answer(answer, context), answer)
        for refs in [[], ['F999'], [None]]:
            bad = copy.deepcopy(answer)
            bad['points'][0]['evidenceIds'] = refs
            with self.assertRaises(ValueError):
                qa.validate_answer(bad, context)

        for bad in [{**answer, 'limits':[]}, {**answer, 'extra':'instructions'}, {**answer, 'answer':''}]:
            with self.assertRaises(ValueError):
                qa.validate_answer(bad, context)

    def test_english_questions_use_same_facts_and_english_source_explanations(self):
        for question in ['How often is spiciness mentioned in kimchi reviews?', 'Which countries show interest in bulgogi?', 'What ingredients are common in Japanese cuisine?', 'Kimchi search trend', 'Kimchi recipe ingredients', 'Restaurant review keywords', 'FlavorSense taste distribution', 'What data sources are connected?']:
            with self.subTest(question=question):
                result=self.ask(question,language='en')
                self.assertTrue(result['evidence'])
                for e in result['evidence']:
                    self.assertNotRegex(e['title']+e['text']+e['caution'], '[가-힣]')
                self.assertNotRegex(qa.data_answer(result)['answer'], '[가-힣]')
        spice=self.ask('How often is spiciness mentioned in kimchi reviews?',language='en')
        self.assertIn('38 (19.5%)',str(spice['evidence']))
        cuisine=self.ask('What ingredients are common in Japanese cuisine?',language='en')
        self.assertEqual(cuisine['scope']['market'],'일본')
        self.assertIn('soy sauce 39.4%',str(cuisine['evidence']))
        missing=self.ask('What are the export tariffs for kimchi?',language='en')
        self.assertFalse(missing['evidence'])
        self.assertIn('cannot verify',qa.data_answer(missing)['answer'])


if __name__ == '__main__':
    unittest.main()
