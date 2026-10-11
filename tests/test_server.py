"""Contract tests with a local fake Ollama. No model download or GPU needed."""
import copy
import json
import sys
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

REPORT = {
    'summary': '제공된 근거에 기반한 실험 계획입니다.',
    'localization': [{'title': '맛', 'hypothesis': '기본맛을 비교합니다.', 'experiment': '블라인드 시식', 'evidenceIds': ['E1', 'E3']} for _ in range(3)],
    'plan': [{'period': p, 'title': '검증', 'action': '인터뷰를 진행합니다.', 'metric': '구매 의향'} for p in ['01–30일','31–60일','61–90일']],
    'risks': ['시장 규모는 없습니다.', '현지 소비자 검증이 필요합니다.']
}
CONTEXT = {'profile': {'company': '테스트식품', 'product': '김치', 'market': '일본', 'format': '냉장', 'channel': '마켓'}, 'evidence': [{'id': f'E{i}', 'text': '관측값'} for i in range(1, 9)]}

class ValidationTests(unittest.TestCase):
    def test_accepts_structured_report(self):
        self.assertEqual(server.validate_output(REPORT), REPORT)

    def test_rejects_missing_and_fabricated_evidence(self):
        for bad in ['E999', 42, None]:
            value = copy.deepcopy(REPORT)
            value['localization'][0]['evidenceIds'] = [bad]
            with self.assertRaises(ValueError):
                server.validate_output(value)
        value = copy.deepcopy(REPORT)
        value['plan'] = []
        with self.assertRaises(ValueError):
            server.validate_output(value)

    def test_rejects_missing_context(self):
        with self.assertRaises(ValueError):
            server.validate_context({'profile': {}})

    def test_report_language_is_explicit_and_validated(self):
        context = {**CONTEXT, 'language': 'en'}
        server.validate_context(context)
        payload = server.chat_options('qwen3.5:9b', {}, context)
        self.assertIn('Respond only in English', payload['messages'][0]['content'])
        self.assertNotIn('반드시 한국어로 답하세요.', payload['messages'][0]['content'])
        with self.assertRaises(ValueError):
            server.validate_context({**CONTEXT, 'language': 'unknown'})

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def setUp(self):
        server.model_details.cache_clear()
        preferred = patch.object(server, 'PREFERRED_MODEL', 'qwen3.5:9b')
        preferred.start()
        self.addCleanup(preferred.stop)

    def request(self, path, data=None, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type': 'application/json', **(headers or {})})
        return urllib.request.urlopen(req, timeout=5)

    def test_empty_model_state_is_explicit(self):
        with patch.object(server, 'ollama', return_value={'models': []}):
            with self.request('/api/status') as response:
                self.assertEqual(json.load(response)['status'], 'empty')

    def test_generation_calls_ollama_and_validates_response(self):
        def fake(path, payload=None, timeout=8):
            if path == '/api/tags':
                return {'models': [{'name': 'qwen3.5:9b', 'size': 1000}]}
            if path == '/api/show':
                return {'capabilities': ['completion'], 'thinking': {'values': [False, True]}}
            self.assertEqual(path, '/api/chat')
            self.assertIs(payload['think'], False)
            self.assertFalse(payload['stream'])
            self.assertEqual(payload['format'], server.SCHEMA)
            self.assertEqual(payload['model'], 'qwen3.5:9b')
            return {'message': {'content': json.dumps(REPORT)}, 'done_reason': 'stop'}
        with patch.object(server, 'ollama', side_effect=fake):
            with self.request('/api/report', {'context': CONTEXT}) as response:
                result = json.load(response)
                self.assertEqual(result['report'], REPORT)
                self.assertEqual(result['model'], 'qwen3.5:9b')

    def test_unknown_model_is_not_downloaded_or_called(self):
        with patch.object(server, 'ollama', return_value={'models': []}) as mock:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/report', {'model':'not-installed', 'context':CONTEXT})
            self.assertEqual(error.exception.code, 503)
            self.assertEqual(mock.call_count, 1)

    def test_invalid_model_output_is_not_reported_as_success(self):
        with patch.object(server, 'ollama', side_effect=[{'models':[{'name':'qwen3.5:9b'}]}, {'capabilities':['completion']}, {'message':{'content':'not json'}}]):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/report', {'model':'qwen3.5:9b', 'context':CONTEXT})
            self.assertEqual(error.exception.code, 502)

    def test_status_auto_selects_text_model_and_hides_model_details(self):
        def fake(path, payload=None, timeout=8):
            if path == '/api/tags':
                return {'models': [{'name':'embed:local','size':100}, {'name':'qwen3.5:9b','size':1000}, {'name':'remote','remote_host':'example.com'}]}
            return {'capabilities': ['embedding'] if payload['model']=='embed:local' else ['completion']}
        with patch.object(server, 'ollama', side_effect=fake):
            with self.request('/api/status') as response:
                value = json.load(response)
                self.assertEqual(value['status'], 'ready')
                self.assertNotIn('model', value)
                self.assertNotIn('Ollama', str(value))

    def test_requested_model_waits_for_install_without_switching_to_4b(self):
        with patch.object(server, 'ollama', return_value={'models':[{'name':'qwen3:4b'}]}) as mock:
            with self.request('/api/status') as response:
                self.assertEqual(json.load(response)['status'], 'empty')
            self.assertEqual(mock.call_count, 1)  # no inference or download
        with patch.object(server, 'ollama', side_effect=[
            {'models':[{'name':'qwen3:4b'}, {'name':'qwen3.5:9b'}]},
            {'capabilities':['completion']}]) as mock:
            with self.request('/api/status') as response:
                self.assertEqual(json.load(response)['status'], 'ready')
            self.assertEqual(mock.call_args.args, ('/api/show', {'model':'qwen3.5:9b'}))

    def test_cross_site_request_is_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/report', {}, {'Origin':'https://untrusted.example'})
        self.assertEqual(error.exception.code, 403)

    def test_public_server_token_required(self):
        with patch.object(server, 'API_TOKEN', 'test-token'):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/status')
            self.assertEqual(error.exception.code, 401)

    def test_loopback_server_rejects_foreign_host_header(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/status', headers={'Host':'untrusted.example'})
        self.assertEqual(error.exception.code, 403)

    def test_raw_dataset_is_not_served(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/data/FlavorSense.csv')
        self.assertEqual(error.exception.code, 404)

    def test_ask_without_model_answers_from_canonical_snapshot(self):
        with patch.object(server, 'ollama', return_value={'models': []}) as mock:
            with self.request('/api/ask', {'question':'김치 리뷰에서 매운맛은 얼마나 언급돼?', 'evidence':[{'text':'999999건'}]}) as response:
                answer = json.load(response)
                self.assertEqual(answer['mode'], 'data')
                self.assertIn('38건(19.5%)', str(answer['points']))
                self.assertNotIn('999999', str(answer))
                self.assertEqual(mock.call_args.args, ('/api/tags',))

    def test_ask_unsupported_question_does_not_invoke_model(self):
        with patch.object(server, 'ollama') as mock:
            with self.request('/api/ask', {'question':'김치 관세는 얼마야?'}) as response:
                answer = json.load(response)
                self.assertEqual(answer['mode'], 'data')
                self.assertEqual(answer['evidence'], [])
                self.assertEqual(answer['points'], [])
                mock.assert_not_called()

    def test_ask_ai_uses_server_evidence_and_pinned_model(self):
        def fake(path, payload=None, timeout=8):
            if path == '/api/tags':
                return {'models':[{'name':'qwen3.5:9b'}]}
            if path == '/api/show':
                return {'capabilities':['completion'], 'thinking':{'values':[False,True]}}
            self.assertEqual(path, '/api/chat')
            self.assertEqual(payload['model'], 'qwen3.5:9b')
            self.assertIs(payload['think'], False)
            context = json.loads(payload['messages'][1]['content'])
            self.assertIn('4.65/5', context['evidence'][0]['text'])
            self.assertEqual(context['previousQuestions'], ['김치에 대해 알려줘'])
            self.assertNotIn('made-up evidence', str(context))
            result = {'answer':'과거 리뷰에서 확인했습니다.', 'points':[{'text':context['evidence'][0]['text'], 'evidenceIds':['F1']}], 'limits':['최신 소비자 조사 결과가 아닙니다.']}
            return {'message':{'content':json.dumps(result)}, 'done_reason':'stop'}
        with patch.object(server, 'ollama', side_effect=fake):
            with self.request('/api/ask', {'question':'김치 평점은?', 'history':['김치에 대해 알려줘'], 'evidence':'made-up evidence'}) as response:
                answer = json.load(response)
                self.assertEqual(answer['mode'], 'ai')
                self.assertEqual(answer['points'][0]['evidenceIds'], ['F1'])
                self.assertIn('2000–2020년', str(answer['limits']))
                self.assertNotIn('model', answer)
                self.assertFalse(server.GENERATION_LOCK.locked())

    def test_ask_invalid_ai_citation_returns_explicit_data_answer(self):
        bad = {'answer':'설명', 'points':[{'text':'임의 주장', 'evidenceIds':['F999']}], 'limits':['한계']}
        with patch.object(server, 'ollama', side_effect=[{'models':[{'name':'qwen3.5:9b'}]}, {'capabilities':['completion']}, {'message':{'content':json.dumps(bad)}}]):
            with self.request('/api/ask', {'question':'김치 평점은?'}) as response:
                answer = json.load(response)
                self.assertEqual(answer['mode'], 'data')
                self.assertNotIn('임의 주장', str(answer))
                self.assertIn('검증에 실패', answer['notice'])
                self.assertFalse(server.GENERATION_LOCK.locked())

    def test_ask_validation_and_origin_guard(self):
        for payload, headers, expected in [({'question':' '}, {}, 400), ({'question':'김치'}, {'Origin':'https://untrusted.example'}, 403)]:
            with self.subTest(expected=expected), self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/ask', payload, headers)
            self.assertEqual(error.exception.code, expected)

    def test_english_ask_uses_english_source_facts_and_prompt(self):
        def fake(path, payload=None, timeout=8):
            if path == '/api/tags':
                return {'models':[{'name':'qwen3.5:9b'}]}
            if path == '/api/show':
                return {'capabilities':['completion']}
            self.assertIn('Respond concisely in English only.', payload['messages'][0]['content'])
            context = json.loads(payload['messages'][1]['content'])
            self.assertIn('Spiciness 38 (19.5%)', str(context['evidence']))
            result = {'answer':'Historical review sample.', 'points':[{'text':context['evidence'][0]['text'], 'evidenceIds':['F1']}], 'limits':['Reviewer countries are unavailable.']}
            return {'message':{'content':json.dumps(result)}, 'done_reason':'stop'}
        with patch.object(server, 'ollama', side_effect=fake):
            with self.request('/api/ask', {'question':'How often is spiciness mentioned in kimchi reviews?', 'language':'en'}) as response:
                value = json.load(response)
                self.assertEqual(value['mode'], 'ai')
                text = json.dumps({k:value[k] for k in ['answer','points','notice','limits','evidence']}, ensure_ascii=False)
                self.assertNotRegex(text, '[가-힣]')

if __name__ == '__main__':
    unittest.main()
