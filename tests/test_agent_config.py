"""Verify container limits reach the model request, without a real model call."""
import json
import unittest
from unittest.mock import patch
import httpx
from backend.agent import Model
from backend.config import Settings


class ModelResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_request_obeys_cpu_context_timeout_and_local_model(self):
        cfg=Settings(model_threads=8,model_context=8192,model_timeout=600,model_keep_alive='0')
        requests=[]
        def respond(request):
            if request.url.path=='/api/tags':
                return httpx.Response(200,json={'models':[{'name':cfg.model}]})
            if request.url.path=='/api/show':
                return httpx.Response(200,json={'capabilities':['completion'],'thinking':{'values':[False,True]}})
            requests.append(request)
            return httpx.Response(200,json={'message':{'content':'{}'},'done_reason':'stop'})
        original=httpx.AsyncClient
        def client(**kwargs):
            return original(transport=httpx.MockTransport(respond),**kwargs)
        with patch('backend.agent.httpx.AsyncClient',side_effect=client):
            self.assertEqual(await Model(cfg).generate({'language':'ko'}),{})
        payload=json.loads(requests[0].content)
        self.assertEqual(payload['model'],'qwen3.5:9b')
        self.assertEqual(payload['options']['num_thread'],8)
        self.assertEqual(payload['options']['num_ctx'],8192)
        self.assertEqual(payload['keep_alive'],'0')
        self.assertIs(payload['think'],False)
        self.assertEqual(requests[0].extensions['timeout']['read'],600)

    def test_resource_limits_are_bounded(self):
        for name,value in [('model_threads',-1),('model_threads',65),('model_timeout',0),('model_timeout',901)]:
            with self.subTest(name=name,value=value),self.assertRaises(RuntimeError):
                Settings(production=False,**{name:value}).validate()
